"""Common interface of the model providers."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field


class ProviderError(Exception):
    """A provider call failed. ``code`` is machine-readable, the message is for the user.

    Codes: ``auth``, ``permission``, ``not_found``, ``rate_limit``, ``bad_request``,
    ``refusal``, ``network``, ``server``, ``unsupported``, ``config``, ``empty``.
    """

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class ChatResult:
    text: str
    model: str = ""
    usage: dict = field(default_factory=dict)
    truncated: bool = False
    notes: list[str] = field(default_factory=list)


def sniff_image_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def data_url(data: bytes) -> str:
    return f"data:{sniff_image_type(data)};base64,{base64.b64encode(data).decode('ascii')}"


def scrub(text: str, secret: str | None) -> str:
    """Remove an API key from text that is about to be shown or logged."""
    if secret and len(secret) >= 6 and secret in text:
        text = text.replace(secret, "[key]")
    return text


class Provider:
    """Base class. Subclasses implement the calls their service supports."""

    offline = False

    def __init__(self, settings: dict) -> None:
        self.id = settings.get("id", "")
        self.model = settings.get("model", "")
        self.base_url = (settings.get("base_url") or "").rstrip("/")
        self._key = settings.get("api_key") or ""

    def __repr__(self) -> str:  # never include the key
        return f"<{type(self).__name__} {self.id} model={self.model!r}>"

    def chat(self, system: str, user: str, images: list[bytes] | None = None, json_mode: bool = True, max_tokens: int = 8000) -> ChatResult:
        raise ProviderError("unsupported", f"{self.id} cannot be used for text generation.")

    def generate_image(self, prompt: str, size: str = "1024x1024", reference: bytes | None = None) -> bytes:
        raise ProviderError("unsupported", f"{self.id} cannot generate images. Choose another provider for the image role in Settings.")

    def list_models(self) -> list[str]:
        raise ProviderError("unsupported", f"{self.id} does not offer a model list.")

    def close(self) -> None:
        pass
