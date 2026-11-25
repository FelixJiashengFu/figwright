"""Claude through the official Anthropic SDK."""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlparse

from .base import ChatResult, Provider, ProviderError, scrub, sniff_image_type

# Models that take ``output_config.effort`` (and think by default, so they need output headroom).
_EFFORT = re.compile(r"^claude-(fable-5|mythos-5|opus-5|sonnet-5|haiku-5|opus-4-[6-9]|sonnet-4-6)")
# Models with server-side refusal fallbacks ("fallbacks": "default").
_FALLBACKS = re.compile(r"^claude-(fable-5|opus-5|sonnet-5-5)")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(Provider):
    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - declared dependency
            raise ProviderError("config", "The 'anthropic' package is missing: pip install anthropic") from exc
        self._sdk = anthropic
        host = urlparse(self.base_url).hostname if self.base_url else "api.anthropic.com"
        self._official = host == "api.anthropic.com"
        self._client = anthropic.Anthropic(api_key=self._key, base_url=self.base_url or None, max_retries=2, timeout=600.0)

    def close(self) -> None:
        self._client.close()

    def _wrap(self, exc: Exception) -> ProviderError:
        sdk = self._sdk
        msg = scrub(str(getattr(exc, "message", "") or exc), self._key)[:400]
        status = getattr(exc, "status_code", None)
        if isinstance(exc, sdk.AuthenticationError):
            return ProviderError("auth", f"Anthropic rejected the API key ({msg}).", status)
        if isinstance(exc, sdk.PermissionDeniedError):
            return ProviderError("permission", f"The key is not allowed to do this ({msg}).", status)
        if isinstance(exc, sdk.NotFoundError):
            return ProviderError("not_found", f"Model not found ({msg}). Check the model name in Settings.", status)
        if isinstance(exc, sdk.RateLimitError):
            return ProviderError("rate_limit", f"Rate limit reached ({msg}).", status)
        if isinstance(exc, sdk.BadRequestError):
            return ProviderError("bad_request", f"Anthropic rejected the request ({msg}).", status)
        if isinstance(exc, sdk.APIStatusError):
            return ProviderError("server", f"Anthropic had a problem (HTTP {status}: {msg}).", status)
        if isinstance(exc, sdk.APIConnectionError):
            return ProviderError("network", f"Could not reach Anthropic: {msg}")
        return ProviderError("server", msg or type(exc).__name__)

    def chat(self, system: str, user: str, images: list[bytes] | None = None, json_mode: bool = True, max_tokens: int = 8000) -> ChatResult:
        sdk = self._sdk
        content: Any = user
        if images:
            content = [{"type": "image", "source": {"type": "base64", "media_type": sniff_image_type(img), "data": base64.b64encode(img).decode("ascii")}} for img in images]
            content.append({"type": "text", "text": user})
        modern = bool(_EFFORT.match(self.model))
        # Thinking shares the output budget on current models, so leave room for it.
        limit = min(64000, max_tokens + 16000) if modern else min(max_tokens, 8192)
        base: dict[str, Any] = {"model": self.model, "max_tokens": limit, "system": system, "messages": [{"role": "user", "content": content}]}
        use_effort = modern
        # Refusal fallbacks: if a safety classifier declines the request, the API re-runs it
        # on the model Anthropic recommends, inside the same call. Claude API only.
        use_fallbacks = self._official and bool(_FALLBACKS.match(self.model))
        message = None
        for _ in range(3):
            kwargs = dict(base)
            if use_effort:
                kwargs["output_config"] = {"effort": "medium"}
            try:
                if use_fallbacks:
                    with self._client.beta.messages.stream(**kwargs, betas=[FALLBACK_BETA], fallbacks="default") as stream:
                        message = stream.get_final_message()
                else:
                    with self._client.messages.stream(**kwargs) as stream:
                        message = stream.get_final_message()
                break
            except sdk.BadRequestError as exc:
                text = str(exc).lower()
                if use_fallbacks and ("fallback" in text or "beta" in text):
                    use_fallbacks = False
                    continue
                if use_effort and ("output_config" in text or "effort" in text):
                    use_effort = False
                    continue
                raise self._wrap(exc) from exc
            except sdk.APIError as exc:
                raise self._wrap(exc) from exc
        if message is None:
            raise ProviderError("bad_request", "Anthropic kept rejecting the request.")

        notes: list[str] = []
        parts: list[str] = []
        for block in message.content or []:
            kind = getattr(block, "type", "")
            if kind == "text":
                parts.append(block.text)
            elif kind == "fallback":
                src = getattr(getattr(block, "from_", None), "model", "the requested model")
                dst = getattr(getattr(block, "to", None), "model", "a fallback model")
                notes.append(f"{src} declined this request; {dst} answered instead")
        if message.stop_reason == "refusal":
            category = getattr(getattr(message, "stop_details", None), "category", None)
            raise ProviderError("refusal", "Claude declined this request" + (f" (category: {category})." if category else "."))
        text = "".join(parts)
        if not text.strip():
            raise ProviderError("empty", "Claude returned no text.")
        usage = getattr(message, "usage", None)
        return ChatResult(
            text=text,
            model=getattr(message, "model", "") or self.model,
            usage={"input_tokens": getattr(usage, "input_tokens", 0) or 0, "output_tokens": getattr(usage, "output_tokens", 0) or 0},
            truncated=message.stop_reason == "max_tokens",
            notes=notes,
        )

    def list_models(self) -> list[str]:
        try:
            ids = []
            for m in self._client.models.list(limit=100):
                ids.append(m.id)
                if len(ids) >= 300:
                    break
            return ids
        except self._sdk.APIError as exc:
            raise self._wrap(exc) from exc
