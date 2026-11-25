"""Google Gemini through its native REST API (generateContent)."""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from .base import ChatResult, Provider, ProviderError, scrub, sniff_image_type
from .openai_compat import _RETRY_STATUS, _error_message

_BLOCKED = ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY")


class GeminiProvider(Provider):
    def __init__(self, settings: dict, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(settings)
        if not self.base_url:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        # The key goes in a header, never in the URL, so it cannot leak into logs or error messages.
        self._client = httpx.Client(headers={"x-goog-api-key": self._key, "User-Agent": "figwright"}, timeout=httpx.Timeout(connect=20.0, read=300.0, write=120.0, pool=20.0), transport=transport)
        self.max_retries = 2
        self.retry_wait = 1.5

    def close(self) -> None:
        self._client.close()

    def _fail(self, status: int, text: str) -> ProviderError:
        msg = scrub(_error_message(text), self._key) or f"HTTP {status}"
        if status in (401, 403):
            return ProviderError("auth", f"Google rejected the API key or its permissions ({msg}).", status)
        if status == 404:
            return ProviderError("not_found", f"Model not found ({msg}). Check the model name in Settings.", status)
        if status == 429:
            return ProviderError("rate_limit", f"Rate limit or quota reached ({msg}).", status)
        if status == 400:
            return ProviderError("bad_request", f"Google rejected the request ({msg}).", status)
        return ProviderError("server", f"Google had a problem (HTTP {status}: {msg}).", status)

    def _send(self, method: str, path: str, body: dict | None = None) -> dict:
        last: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self._client.request(method, self.base_url + path, json=body)
            except httpx.HTTPError as exc:
                last = ProviderError("network", scrub(f"Could not reach Google: {type(exc).__name__}: {exc}", self._key))
            else:
                if r.status_code < 400:
                    try:
                        return r.json()
                    except ValueError as exc:
                        raise ProviderError("server", "Google sent a reply that is not valid JSON.") from exc
                last = self._fail(r.status_code, r.text)
                if r.status_code not in _RETRY_STATUS:
                    raise last
            if attempt < self.max_retries:
                time.sleep(self.retry_wait * (attempt + 1))
        assert last is not None
        raise last

    def _generate(self, body: dict) -> tuple[list[dict], str, dict, str]:
        model = self.model.removeprefix("models/")
        data = self._send("POST", f"/models/{model}:generateContent", body)
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise ProviderError("refusal", f"Google blocked this request ({feedback['blockReason']}).")
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        return parts, str(cand.get("finishReason") or ""), data.get("usageMetadata") or {}, data.get("modelVersion") or self.model

    def chat(self, system: str, user: str, images: list[bytes] | None = None, json_mode: bool = True, max_tokens: int = 8000) -> ChatResult:
        parts: list[dict[str, Any]] = [{"inlineData": {"mimeType": sniff_image_type(img), "data": base64.b64encode(img).decode("ascii")}} for img in images or []]
        parts.append({"text": user})
        config: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if json_mode:
            config["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}], "generationConfig": config}
        notes: list[str] = []
        try:
            out, finish, usage, model = self._generate(body)
        except ProviderError as exc:
            if exc.code != "bad_request" or "responseMimeType" not in config:
                raise
            del config["responseMimeType"]
            notes.append("the model does not support JSON mode; asked for JSON in the prompt instead")
            out, finish, usage, model = self._generate(body)
        text = "".join(p.get("text", "") for p in out if isinstance(p, dict) and not p.get("thought"))
        if finish in _BLOCKED and not text.strip():
            raise ProviderError("refusal", f"Google blocked the answer ({finish}).")
        if not text.strip():
            raise ProviderError("empty", "The model returned no text. If it is a thinking model, its whole output budget may have gone to thinking; try again or raise the limit.")
        return ChatResult(
            text=text,
            model=model,
            usage={"input_tokens": usage.get("promptTokenCount", 0), "output_tokens": usage.get("candidatesTokenCount", 0)},
            truncated=finish == "MAX_TOKENS",
            notes=notes,
        )

    def generate_image(self, prompt: str, size: str = "1024x1024", reference: bytes | None = None) -> bytes:
        parts: list[dict[str, Any]] = []
        if reference:
            parts.append({"inlineData": {"mimeType": sniff_image_type(reference), "data": base64.b64encode(reference).decode("ascii")}})
        parts.append({"text": prompt})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
        out, finish, _usage, _model = self._generate(body)
        for p in out:
            blob = p.get("inlineData") or p.get("inline_data") if isinstance(p, dict) else None
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
        if finish in _BLOCKED:
            raise ProviderError("refusal", f"Google blocked the image ({finish}).")
        raise ProviderError("unsupported", "The model returned no image. Choose a Gemini model that can output images for the image role.")

    def list_models(self) -> list[str]:
        ids: list[str] = []
        token = ""
        for _ in range(5):
            data = self._send("GET", "/models?pageSize=200" + (f"&pageToken={token}" if token else ""))
            ids += [str(m.get("name", "")).removeprefix("models/") for m in data.get("models") or [] if m.get("name")]
            token = data.get("nextPageToken") or ""
            if not token:
                break
        return sorted(set(ids))


__all__ = ["GeminiProvider"]
