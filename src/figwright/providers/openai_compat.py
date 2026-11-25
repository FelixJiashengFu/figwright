"""OpenAI-compatible providers (chat/completions, images, models).

One client covers OpenAI itself and the many services that copied its wire
format: DeepSeek, DashScope, Moonshot, Zhipu, SiliconFlow, OpenRouter, Tencent
TokenHub, Baidu Qianfan, xAI, Mistral, Groq, Ollama, LM Studio and friends.

"Compatible" is a loose promise, so the client starts with a small request and
adapts when a server objects: it drops ``response_format``, renames
``max_tokens`` or turns streaming off, then tries again.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import ChatResult, Provider, ProviderError, data_url, scrub, sniff_image_type

MAX_IMAGE_BYTES = 40 * 1024 * 1024
_RETRY_STATUS = (408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529)


def _error_message(text: str) -> str:
    try:
        data = json.loads(text)
    except ValueError:
        return text.strip()[:400]
    if isinstance(data, dict):
        err = data.get("error", data)
        if isinstance(err, dict):
            msg = err.get("message") or err.get("msg") or err.get("detail") or err.get("code")
            if msg:
                return str(msg)[:400]
        if isinstance(err, str):
            return err[:400]
    return text.strip()[:400]


class OpenAICompatProvider(Provider):
    def __init__(self, settings: dict, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(settings)
        headers = {"Accept": "application/json, text/event-stream", "User-Agent": "figwright"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        self._client = httpx.Client(headers=headers, timeout=httpx.Timeout(connect=20.0, read=300.0, write=120.0, pool=20.0), transport=transport)
        self.max_retries = 2
        self.retry_wait = 1.5

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ errors
    def _fail(self, status: int, text: str) -> ProviderError:
        msg = scrub(_error_message(text), self._key) or f"HTTP {status}"
        if status == 401:
            return ProviderError("auth", f"The provider rejected the API key ({msg}).", status)
        if status == 403:
            return ProviderError("permission", f"The key is not allowed to do this ({msg}).", status)
        if status == 404:
            return ProviderError("not_found", f"Model or endpoint not found ({msg}). Check the model name and the API address.", status)
        if status == 429:
            return ProviderError("rate_limit", f"Rate limit or quota reached ({msg}).", status)
        if status in (400, 422):
            return ProviderError("bad_request", f"The provider rejected the request ({msg}).", status)
        return ProviderError("server", f"The provider had a problem (HTTP {status}: {msg}).", status)

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """A non-streaming request with retries for transient failures."""
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self._client.request(method, self.base_url + path, **kwargs)
            except httpx.HTTPError as exc:
                last = ProviderError("network", scrub(f"Could not reach {urlparse(self.base_url).netloc}: {type(exc).__name__}: {exc}", self._key))
            else:
                if r.status_code < 400:
                    return r
                last = self._fail(r.status_code, r.text)
                if r.status_code not in _RETRY_STATUS:
                    raise last
            if attempt < self.max_retries:
                time.sleep(self.retry_wait * (attempt + 1))
        assert last is not None
        raise last

    # -------------------------------------------------------------------- chat
    def chat(self, system: str, user: str, images: list[bytes] | None = None, json_mode: bool = True, max_tokens: int = 8000) -> ChatResult:
        content: Any = user
        if images:
            content = [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": data_url(img)}} for img in images]
        body: dict[str, Any] = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}], "max_tokens": max_tokens, "stream": True}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        notes: list[str] = []
        transient = 0
        for _ in range(8):
            try:
                result = self._chat_once(body)
                result.notes = notes + result.notes
                return result
            except ProviderError as exc:
                if exc.code == "bad_request" and self._adapt(body, str(exc).lower(), notes):
                    continue
                if (exc.code in ("network", "rate_limit") or (exc.status or 0) in _RETRY_STATUS) and transient < self.max_retries:
                    transient += 1
                    time.sleep(self.retry_wait * transient)
                    continue
                raise
        raise ProviderError("bad_request", "The provider kept rejecting the request.")

    @staticmethod
    def _adapt(body: dict, message: str, notes: list[str]) -> bool:
        """Change the request after a 400 so that the next attempt may pass. Returns False when out of ideas."""
        if "max_completion_tokens" in message and "max_tokens" in body:
            body["max_completion_tokens"] = body.pop("max_tokens")
            return True
        if "stream" in message and body.get("stream"):
            body["stream"] = False
            return True
        if "response_format" in body:
            del body["response_format"]
            notes.append("the provider does not support JSON mode; asked for JSON in the prompt instead")
            return True
        if "max_tokens" in message and "max_tokens" in body:
            # Usually "max_tokens is too large": fall back to the server's own default.
            del body["max_tokens"]
            return True
        return False

    def _chat_once(self, body: dict) -> ChatResult:
        url = self.base_url + "/chat/completions"
        try:
            with self._client.stream("POST", url, json=body) as r:
                if r.status_code >= 400:
                    raise self._fail(r.status_code, r.read().decode("utf-8", "replace"))
                if "text/event-stream" not in r.headers.get("content-type", ""):
                    return self._from_json(json.loads(r.read().decode("utf-8", "replace")))
                return self._from_stream(r)
        except httpx.HTTPError as exc:
            raise ProviderError("network", scrub(f"Connection to {urlparse(self.base_url).netloc} failed: {type(exc).__name__}: {exc}", self._key)) from exc
        except ValueError as exc:
            raise ProviderError("server", f"The provider sent a reply that is not valid JSON ({exc}).") from exc

    @staticmethod
    def _piece(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in ("text", "output_text"))
        return ""

    def _finish(self, text: str, finish: str | None, model: str, usage: dict) -> ChatResult:
        if finish == "content_filter" and not text.strip():
            raise ProviderError("refusal", "The provider's content filter blocked this request.")
        if not text.strip():
            raise ProviderError("empty", "The model returned no text. If this is a reasoning model, raise its output limit or pick another model.")
        # One spelling of usage whatever the dialect called it.
        counted = {
            "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        }
        return ChatResult(text=text, model=model or self.model, usage=counted if any(counted.values()) else {}, truncated=finish == "length")

    def _from_json(self, data: dict) -> ChatResult:
        if isinstance(data.get("error"), (dict, str)):
            raise ProviderError("server", scrub(_error_message(json.dumps(data)), self._key))
        choice = (data.get("choices") or [{}])[0]
        text = self._piece((choice.get("message") or {}).get("content"))
        return self._finish(text, choice.get("finish_reason"), data.get("model", ""), data.get("usage") or {})

    def _from_stream(self, r: httpx.Response) -> ChatResult:
        parts: list[str] = []
        finish: str | None = None
        model = ""
        usage: dict = {}
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                evt = json.loads(payload)
            except ValueError:
                continue
            if not isinstance(evt, dict):
                continue
            if evt.get("error"):
                raise ProviderError("server", scrub(_error_message(json.dumps(evt)), self._key))
            model = evt.get("model") or model
            if isinstance(evt.get("usage"), dict):
                usage = evt["usage"]
            for choice in evt.get("choices") or []:
                delta = choice.get("delta") or choice.get("message") or {}
                parts.append(self._piece(delta.get("content")))
                finish = choice.get("finish_reason") or finish
        return self._finish("".join(parts), finish, model, usage)

    # ------------------------------------------------------------------ images
    def generate_image(self, prompt: str, size: str = "1024x1024", reference: bytes | None = None) -> bytes:
        fields = {"model": self.model, "prompt": prompt, "n": 1, "size": size}
        for attempt in range(2):
            try:
                if reference:
                    files = {"image": ("reference.png", reference, sniff_image_type(reference))}
                    r = self._send("POST", "/images/edits", data={k: str(v) for k, v in fields.items()}, files=files)
                else:
                    r = self._send("POST", "/images/generations", json=fields)
                break
            except ProviderError as exc:
                if exc.code == "bad_request" and "size" in str(exc).lower() and "size" in fields and attempt == 0:
                    del fields["size"]
                    continue
                if exc.code == "not_found" and reference:
                    raise ProviderError("unsupported", "This provider has no image-editing endpoint; generation from text still works.") from exc
                raise
        try:
            item = r.json()["data"][0]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("server", "The provider returned no image.") from exc
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            return fetch_image(item["url"])
        raise ProviderError("server", "The provider returned no image.")

    # ------------------------------------------------------------------ models
    def list_models(self) -> list[str]:
        data = self._send("GET", "/models").json()
        items = data.get("data") if isinstance(data, dict) else data
        ids = sorted({str(m.get("id") or m.get("name")) for m in items or [] if isinstance(m, dict) and (m.get("id") or m.get("name"))})
        return ids


def fetch_image(url: str) -> bytes:
    """Download a generated image. No credentials are sent: the link may point at a CDN."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ProviderError("server", "The provider returned an image link that is not https; refusing to download it.")
    try:
        with httpx.stream("GET", url, timeout=120.0, follow_redirects=True, headers={"User-Agent": "figwright"}) as r:
            if r.status_code >= 400:
                raise ProviderError("server", f"Downloading the generated image failed (HTTP {r.status_code}).")
            chunks: list[bytes] = []
            size = 0
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ProviderError("server", "The generated image is unreasonably large.")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ProviderError("network", f"Downloading the generated image failed: {type(exc).__name__}.") from exc
    return b"".join(chunks)
