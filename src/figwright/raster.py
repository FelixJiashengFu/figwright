"""Image lab: clean up photos, scans and screenshots for publication.

Everything here is classical image processing (OpenCV / Pillow). That is a
deliberate choice for scientific images: these operations are deterministic
and do not invent content, which a generative "enhancer" may do. The one
generative operation, redrawing a region, lives in :mod:`figwright.generate`
and is clearly labelled as such.

Do not use any of this on data images (gels, blots, micrographs) in ways your
journal's image-integrity policy forbids: adjustments must apply to the whole
image and must not hide or create features. Each call returns the list of
steps that were applied so that they can be reported.
"""

from __future__ import annotations

import io
from typing import Any

MAX_BYTES = 60 * 1024 * 1024
MAX_PIXELS = 80_000_000
MAX_OUT_SIDE = 12_000
FORMATS = ("png", "jpeg", "tiff", "webp")
CVD_KINDS = ("deuteranopia", "protanopia", "tritanopia")

# Machado, Oliveira & Fernandes (2009), severity 1.0, applied to linear RGB.
_CVD = {
    "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritanopia": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


class ImageError(ValueError):
    """The upload cannot be processed; the message is for the user."""


def open_image(data: bytes):
    """Decode an upload to a Pillow image in RGB or RGBA, upright."""
    from PIL import Image, ImageOps

    if not data:
        raise ImageError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ImageError("The image file is larger than 60 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ImageError(f"The image has {img.width * img.height / 1e6:.0f} megapixels; the limit is {MAX_PIXELS // 1_000_000}.")
        img.load()
        img = ImageOps.exif_transpose(img)
    except ImageError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow raises many types for bad or oversized data
        raise ImageError("The file is not an image this tool can read (PNG, JPEG, TIFF, WebP, BMP or GIF).") from exc
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        return img.convert("RGBA")
    if img.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        # 16-bit / float scientific images: scale the full range to 8 bit for display.
        import numpy as np

        arr = np.asarray(img, dtype=np.float64)
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo) * 255.0 if hi > lo else np.zeros_like(arr)
        return Image.fromarray(arr.astype("uint8"), "L").convert("RGB")
    return img.convert("RGB")


def _split(img):
    import numpy as np

    arr = np.asarray(img)
    if arr.ndim == 3 and arr.shape[2] == 4:
        return arr[:, :, :3].copy(), arr[:, :, 3].copy()
    return arr.copy(), None


def _join(rgb, alpha):
    import numpy as np
    from PIL import Image

    if alpha is None:
        return Image.fromarray(rgb, "RGB")
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def _clamp(v: Any, lo: float, hi: float, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:
        return default
    return max(lo, min(hi, f))


def denoise(rgb, strength: float):
    import cv2

    h = 3.0 + 11.0 * strength
    return cv2.fastNlMeansDenoisingColored(rgb, None, h, h, 7, 21)


def sharpen(rgb, strength: float):
    import cv2

    blur = cv2.GaussianBlur(rgb, (0, 0), 1.4)
    amount = 0.35 + 1.4 * strength
    return cv2.addWeighted(rgb, 1.0 + amount, blur, -amount, 0)


def local_contrast(rgb, strength: float):
    """Stretch the tonal range, then add a little local contrast (kept mild: strong CLAHE turns noise into texture)."""
    import cv2
    import numpy as np

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lum = lab[:, :, 0].astype(np.float32)
    lo, hi = np.percentile(lum, [0.5, 99.5])
    if hi - lo > 8:
        stretched = np.clip((lum - lo) * (255.0 / (hi - lo)), 0, 255)
        lum = lum + (stretched - lum) * strength
    clahe = cv2.createCLAHE(clipLimit=1.0 + 1.2 * strength, tileGridSize=(4, 4))
    local = clahe.apply(lum.astype(np.uint8)).astype(np.float32)
    lab[:, :, 0] = np.clip(lum + (local - lum) * 0.5 * strength, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def _illumination(lum):
    """Smooth estimate of the paper brightness across the image.

    A quadratic surface is fitted to the bright envelope of a coarse grid. Dark
    cells (ink, filled shapes) are treated as outliers and dropped, so large
    coloured areas keep their colour instead of being washed out.
    """
    import numpy as np

    h, w = lum.shape
    gy, gx = max(4, min(28, h // 12)), max(4, min(28, w // 12))
    ys = np.linspace(0, h, gy + 1).astype(int)
    xs = np.linspace(0, w, gx + 1).astype(int)
    pts, vals = [], []
    for i in range(gy):
        for j in range(gx):
            cell = lum[ys[i] : ys[i + 1], xs[j] : xs[j + 1]]
            if cell.size:
                pts.append(((xs[j] + xs[j + 1]) / 2.0 / w, (ys[i] + ys[i + 1]) / 2.0 / h))
                vals.append(float(np.percentile(cell, 90)))
    pts_a, v = np.asarray(pts, dtype=np.float64), np.asarray(vals, dtype=np.float64)

    def design(x, y):
        return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1)

    A = design(pts_a[:, 0], pts_a[:, 1])
    keep = v >= np.percentile(v, 35)
    coef = None
    for _ in range(6):
        if keep.sum() < 12:
            break
        coef, *_rest = np.linalg.lstsq(A[keep], v[keep], rcond=None)
        resid = v - A @ coef
        spread = max(2.0, float(np.median(np.abs(resid[keep]))) * 2.5)
        new_keep = resid > -spread  # darker than the surface: not paper
        if (new_keep == keep).all():
            break
        keep = new_keep
    if coef is None:
        return np.full_like(lum, max(1.0, float(np.percentile(lum, 95)))), keep.reshape(gy, gx) if keep.size == gy * gx else None
    yy, xx = np.mgrid[0:h, 0:w]
    surface = design(xx / w, yy / h) @ coef
    return np.clip(surface, 16.0, 255.0).astype(np.float32), None


def whiten_background(rgb):
    """Even out the lighting and push the paper to white (photos of notebooks and whiteboards, scans).

    Meant for drawings on a light, mostly empty background. One gain per pixel
    is applied to all three channels, so colours keep their hue.
    """
    import numpy as np

    f = rgb.astype(np.float32)
    lum = f.max(axis=2)
    surface, _ = _illumination(lum)
    flat = f * (250.0 / surface)[..., None]
    # White balance: what is still close to paper brightness after flattening is paper.
    paper = flat[flat.max(axis=2) >= 235.0]
    if paper.shape[0] > 50:
        tint = np.median(paper, axis=0)
        flat *= (250.0 / np.maximum(tint, 1.0))[None, None, :]
    return np.clip(flat * (255.0 / 244.0), 0, 255).astype(np.uint8)


def adjust(rgb, brightness: float = 0.0, saturation: float = 0.0):
    import cv2
    import numpy as np

    out = rgb
    if saturation:
        hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * (1.0 + saturation), 0, 255)
        out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    if brightness:
        # Gamma keeps black and white fixed, so nothing clips.
        gamma = 2.0 ** (-brightness * 1.2)
        table = (np.linspace(0, 1, 256) ** gamma * 255.0).astype(np.uint8)
        out = cv2.LUT(out, table)
    return out


def border_color(rgb, alpha=None):
    """Median colour of the outermost pixels: the background of most figures."""
    import numpy as np

    b = max(1, min(rgb.shape[0], rgb.shape[1]) // 100)
    edge = np.concatenate([rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3), rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)])
    return np.median(edge, axis=0)


def _distance(rgb, color):
    """Perceptual-ish distance of every pixel to a colour (CIE76 in Lab)."""
    import cv2
    import numpy as np

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    ref = cv2.cvtColor(np.uint8([[np.clip(color, 0, 255)]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    d = lab - ref
    d[:, :, 0] *= 100.0 / 255.0  # OpenCV stores L scaled to 0..255
    return np.sqrt((d * d).sum(axis=2))


def remove_background(rgb, alpha=None, tolerance: float = 0.25, everywhere: bool = False):
    """Make the background colour transparent.

    The background is the colour of the image border. By default only areas
    connected to the border are removed, so a white label inside the subject
    stays white; ``everywhere`` removes that colour wherever it occurs.
    Returns the new alpha channel.
    """
    import cv2
    import numpy as np

    h, w = rgb.shape[:2]
    tol = 4.0 + 46.0 * tolerance
    dist = _distance(rgb, border_color(rgb))
    similar = (dist <= tol).astype(np.uint8)
    if everywhere:
        bg = similar
    else:
        padded = np.zeros((h + 2, w + 2), np.uint8)
        padded[1:-1, 1:-1] = similar
        padded[0, :] = padded[-1, :] = padded[:, 0] = padded[:, -1] = 1
        _n, labels = cv2.connectedComponents(padded, connectivity=4)
        bg = (labels[1:-1, 1:-1] == labels[0, 0]).astype(np.uint8)
    # Soft edge: pixels just outside the tolerance next to the background fade out instead of leaving a halo.
    near = cv2.dilate(bg, np.ones((3, 3), np.uint8)) > 0
    soft = np.clip((dist - tol) / max(1.0, tol * 0.7), 0.0, 1.0)
    a = np.where(bg > 0, 0.0, np.where(near, soft, 1.0))
    out = (a * 255.0).astype(np.uint8)
    if alpha is not None:
        out = np.minimum(out, alpha)
    return out


def content_box(rgb, alpha=None, tolerance: float = 0.12) -> tuple[int, int, int, int] | None:
    import numpy as np

    if alpha is not None and alpha.min() < 250:
        mask = alpha > 12
    else:
        mask = _distance(rgb, border_color(rgb)) > (4.0 + 46.0 * tolerance)
    ys, xs = np.nonzero(mask)
    if not xs.size:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def simulate_cvd(rgb, kind: str = "deuteranopia"):
    """How the image looks with a colour-vision deficiency (for checking, not for export)."""
    import numpy as np

    m = np.asarray(_CVD.get(kind, _CVD["deuteranopia"]), dtype=np.float32)
    srgb = rgb.astype(np.float32) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    sim = np.clip(linear @ m.T, 0.0, 1.0)
    out = np.where(sim <= 0.0031308, sim * 12.92, 1.055 * sim ** (1 / 2.4) - 0.055)
    return (np.clip(out, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def encode(img, fmt: str = "png", dpi: int | None = None, quality: int = 95) -> bytes:
    from PIL import Image

    fmt = {"jpg": "jpeg", "tif": "tiff"}.get((fmt or "png").lower(), (fmt or "png").lower())
    if fmt not in FORMATS:
        raise ImageError(f"Unknown image format {fmt!r}. Available: {', '.join(FORMATS)}.")
    kwargs: dict[str, Any] = {}
    if dpi:
        kwargs["dpi"] = (dpi, dpi)
    if fmt == "jpeg":
        if img.mode == "RGBA":
            flat = Image.new("RGB", img.size, "white")
            flat.paste(img, mask=img.getchannel("A"))
            img = flat
        kwargs.update(quality=quality, subsampling=0, optimize=True)
    elif fmt == "tiff":
        kwargs["compression"] = "tiff_lzw"
    elif fmt == "png":
        kwargs["optimize"] = True
    buf = io.BytesIO()
    img.save(buf, format=fmt.upper(), **kwargs)
    return buf.getvalue()


def enhance(data: bytes, options: dict | None = None) -> tuple[bytes, dict]:
    """Apply the requested clean-up steps. Returns ``(image bytes, info)``.

    Options (all optional): ``whiten`` bool, ``denoise`` 0..1, ``contrast`` 0..1,
    ``brightness`` -1..1, ``saturation`` -1..1, ``remove_bg`` bool with
    ``bg_tolerance`` 0..1 and ``bg_everywhere`` bool, ``trim`` bool with
    ``margin`` px, ``upscale`` 1..4, ``width_mm`` + ``dpi`` (print size),
    ``sharpen`` 0..1, ``grayscale`` bool, ``cvd`` (preview only), ``format``.
    """
    import cv2
    import numpy as np
    from PIL import Image

    o = options or {}
    img = open_image(data)
    rgb, alpha = _split(img)
    steps: list[str] = []
    notes: list[str] = []
    src_w, src_h = img.size

    if o.get("whiten"):
        rgb = whiten_background(rgb)
        steps.append("background flattened and whitened")
    s = _clamp(o.get("denoise"), 0, 1)
    if s > 0:
        rgb = denoise(rgb, s)
        steps.append(f"noise reduction (non-local means, strength {s:.2f})")
    s = _clamp(o.get("contrast"), 0, 1)
    if s > 0:
        rgb = local_contrast(rgb, s)
        steps.append(f"local contrast (CLAHE, strength {s:.2f})")
    b, sat = _clamp(o.get("brightness"), -1, 1), _clamp(o.get("saturation"), -1, 1)
    if b or sat:
        rgb = adjust(rgb, b, sat)
        steps.append(f"brightness {b:+.2f}, saturation {sat:+.2f}")
    if o.get("remove_bg"):
        tol = _clamp(o.get("bg_tolerance", 0.25), 0, 1, 0.25)
        alpha = remove_background(rgb, alpha, tol, bool(o.get("bg_everywhere")))
        removed = float((alpha < 128).mean())
        steps.append(f"background made transparent ({removed:.0%} of the image)")
        if removed < 0.02:
            notes.append("almost nothing was removed: the border of the image is not a uniform background, or the tolerance is too low")
        elif removed > 0.97:
            notes.append("nearly everything was removed: lower the tolerance")
    if o.get("trim"):
        box = content_box(rgb, alpha)
        if box:
            m = int(_clamp(o.get("margin", 12), 0, 400, 12))
            x0, y0, x1, y1 = max(0, box[0] - m), max(0, box[1] - m), min(rgb.shape[1], box[2] + m), min(rgb.shape[0], box[3] + m)
            if (x1 - x0, y1 - y0) != (rgb.shape[1], rgb.shape[0]):
                rgb = rgb[y0:y1, x0:x1]
                alpha = alpha[y0:y1, x0:x1] if alpha is not None else None
                steps.append("empty margins trimmed")

    dpi = int(_clamp(o.get("dpi"), 0, 2400)) or None
    h, w = rgb.shape[:2]
    target_w = w
    width_mm = _clamp(o.get("width_mm"), 0, 2000)
    factor = _clamp(o.get("upscale", 1), 1, 4, 1)
    if width_mm and dpi:
        target_w = max(1, round(width_mm / 25.4 * dpi))
    elif factor > 1:
        target_w = round(w * factor)
    if target_w != w:
        target_h = max(1, round(h * target_w / w))
        if max(target_w, target_h) > MAX_OUT_SIDE:
            k = MAX_OUT_SIDE / max(target_w, target_h)
            target_w, target_h = max(1, int(target_w * k)), max(1, int(target_h * k))
            notes.append(f"the output was capped at {MAX_OUT_SIDE} px on its longer side")
        interp = cv2.INTER_LANCZOS4 if target_w > w else cv2.INTER_AREA
        rgb = cv2.resize(rgb, (target_w, target_h), interpolation=interp)
        if alpha is not None:
            alpha = cv2.resize(alpha, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        ratio = target_w / w
        steps.append(f"resampled {ratio:.2f}x to {target_w} x {target_h} px (Lanczos)" if ratio > 1 else f"reduced to {target_w} x {target_h} px")
        if ratio > 1.01:
            notes.append("enlarging interpolates between existing pixels: it meets a size or dpi requirement but adds no real detail")
    s = _clamp(o.get("sharpen"), 0, 1)
    if s > 0:
        rgb = sharpen(rgb, s)
        steps.append(f"sharpening (unsharp mask, strength {s:.2f})")
    if o.get("grayscale"):
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        rgb = np.dstack([g, g, g])
        steps.append("converted to greyscale")
    cvd = o.get("cvd")
    if cvd in CVD_KINDS:
        rgb = simulate_cvd(rgb, cvd)
        steps.append(f"colour-vision simulation ({cvd}); a preview for checking, not for publication")

    out = _join(np.ascontiguousarray(rgb), alpha)
    fmt = {"jpg": "jpeg", "tif": "tiff"}.get(str(o.get("format") or "png").lower(), str(o.get("format") or "png").lower())
    payload = encode(out, fmt, dpi)
    if fmt == "jpeg" and alpha is not None:
        notes.append("JPEG has no transparency: transparent areas were filled with white")
    info: dict[str, Any] = {"width": out.width, "height": out.height, "source": [src_w, src_h], "format": fmt, "bytes": len(payload), "steps": steps, "notes": notes, "transparent": alpha is not None}
    if dpi:
        info["dpi"] = dpi
        info["mm"] = [round(out.width / dpi * 25.4, 1), round(out.height / dpi * 25.4, 1)]
    return payload, info


def paste_region(base: bytes, patch: bytes, box: tuple[int, int, int, int], feather: int = 6) -> bytes:
    """Composite ``patch`` into ``base`` inside ``box`` with a feathered edge.

    Used after a model redraws a region: every pixel outside the box is
    guaranteed to be unchanged.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    img = open_image(base).convert("RGBA")
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ImageError("The selected region is empty.")
    part = open_image(patch).convert("RGBA").resize((x1 - x0, y1 - y0), Image.LANCZOS)
    f = max(0, min(feather, (x1 - x0) // 4, (y1 - y0) // 4))
    mask = Image.new("L", part.size, 0)
    inner = Image.new("L", (max(1, part.width - 2 * f), max(1, part.height - 2 * f)), 255)
    mask.paste(inner, (f, f))
    if f:
        mask = mask.filter(ImageFilter.GaussianBlur(f / 2.0))
    # Re-zero the outermost ring so the blur cannot leak change outside the box.
    m = np.asarray(mask).copy()
    m[0, :] = m[-1, :] = 0
    m[:, 0] = m[:, -1] = 0
    img.paste(part, (x0, y0), Image.fromarray(m, "L"))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def crop(data: bytes, box: tuple[int, int, int, int]) -> bytes:
    img = open_image(data)
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ImageError("The selected region is empty.")
    buf = io.BytesIO()
    img.crop((x0, y0, x1, y1)).save(buf, format="PNG")
    return buf.getvalue()
