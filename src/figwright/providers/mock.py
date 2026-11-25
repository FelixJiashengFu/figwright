"""The offline demo provider.

It needs no key and never touches the network. The generation pipelines notice
``offline = True`` and use the heuristics in :mod:`figwright.offline` instead
of calling a model; images are procedural placeholders. It exists so that the
app is usable the moment it is installed and so that tests run anywhere.
"""

from __future__ import annotations

import hashlib
import io
import math

from .base import ChatResult, Provider, ProviderError


class MockProvider(Provider):
    offline = True

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings or {"id": "mock"})
        self.id = "mock"
        self.model = "offline-demo"

    def chat(self, system: str, user: str, images: list[bytes] | None = None, json_mode: bool = True, max_tokens: int = 8000) -> ChatResult:
        raise ProviderError("unsupported", "The offline demo has no language model. Choose a provider in Settings for this feature.")

    def generate_image(self, prompt: str, size: str = "1024x1024", reference: bytes | None = None) -> bytes:
        """A deterministic abstract placeholder so the image workflow can be tried without a key."""
        from PIL import Image, ImageDraw, ImageFilter

        try:
            w, h = (max(128, min(2048, int(v))) for v in size.lower().split("x"))
        except ValueError:
            w, h = 1024, 1024
        seed = int.from_bytes(hashlib.sha256(prompt.encode("utf-8")).digest()[:8], "big")

        def rnd() -> float:
            nonlocal seed
            seed = (seed * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            return (seed >> 11) / float(1 << 53)

        palette = [(47, 111, 183), (224, 122, 63), (42, 157, 143), (184, 85, 139), (138, 111, 209), (201, 162, 39)]
        img = Image.new("RGB", (w, h), (247, 249, 252))
        draw = ImageDraw.Draw(img, "RGBA")
        for _ in range(9):
            cx, cy = rnd() * w, rnd() * h
            r = (0.08 + rnd() * 0.2) * min(w, h)
            col = palette[int(rnd() * len(palette)) % len(palette)]
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (70,))
        img = img.filter(ImageFilter.GaussianBlur(radius=min(w, h) / 60))
        draw = ImageDraw.Draw(img, "RGBA")
        # A stylised cell: membrane ring, nucleus and a few organelles.
        cx, cy, r = w / 2, h / 2, min(w, h) * 0.3
        draw.ellipse([cx - r, cy - r * 0.86, cx + r, cy + r * 0.86], fill=(219, 233, 248, 235), outline=(47, 111, 183, 255), width=max(3, w // 170))
        draw.ellipse([cx - r * 0.2, cy - r * 0.28, cx + r * 0.36, cy + r * 0.28], fill=(47, 111, 183, 220))
        for k in range(7):
            a = 2 * math.pi * k / 7 + rnd()
            ox, oy = cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.5
            s = r * (0.06 + rnd() * 0.05)
            col = palette[(k + 1) % len(palette)]
            draw.ellipse([ox - s * 1.6, oy - s, ox + s * 1.6, oy + s], fill=col + (230,))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def list_models(self) -> list[str]:
        return ["offline-demo"]
