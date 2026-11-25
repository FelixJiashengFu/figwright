"""Generation pipelines: request in, checked scene out.

Every pipeline has the same spine::

    content or scene from a model (or the offline heuristics)
      -> normalise -> automatic tidy-up -> layout check
      -> optional repair round (the model gets the list of problems)
      -> optional visual critique (a vision model looks at the rendering)

and returns an :class:`Outcome` with the scene, what was done and what is
still wrong, so the UI never has to guess.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from . import __version__, offline, prompts
from .builders import BUILDERS
from .config import load_config
from .jsonx import JSONExtractError, extract_json
from .lint import autofix, lint, summarize
from .ops import apply_ops
from .providers import Provider, ProviderError, provider_for_role
from .scene import compact_json, normalize_scene, restore_heavy, strip_heavy
from .sources import clip_source
from .themes import THEMES

QUALITIES = ("fast", "balanced", "best")
HOUSE_KEYS = ("fontFamily", "strokeWidth", "edgeWidth", "cornerRadius", "arrowSize")
Progress = Callable[[str], None]


class GenerationError(Exception):
    """The request could not be turned into a figure; the message is for the user."""

    def __init__(self, message: str, code: str = "generation") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Outcome:
    scene: dict
    kind: str
    provider: str
    model: str
    notes: list[str] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict:
        return {"scene": self.scene, "kind": self.kind, "provider": self.provider, "model": self.model, "notes": self.notes, "issues": self.issues, "usage": self.usage, "summary": self.summary}


def _noop(_msg: str) -> None:
    return None


def _score(issues: list[dict]) -> int:
    return sum(3 if i.get("severity") == "error" else 1 for i in issues)


def _add_usage(total: dict, usage: dict) -> None:
    for src, dst in (("input_tokens", "input_tokens"), ("prompt_tokens", "input_tokens"), ("output_tokens", "output_tokens"), ("completion_tokens", "output_tokens")):
        v = usage.get(src)
        if isinstance(v, (int, float)):
            total[dst] = total.get(dst, 0) + int(v)
    total["calls"] = total.get("calls", 0) + 1


def stamp(scene: dict, action: str, provider: str, model: str, **extra: Any) -> None:
    """Append a provenance record: what made or changed this figure, and when."""
    meta = scene.setdefault("meta", {})
    log = meta.get("provenance")
    if not isinstance(log, list):
        log = []
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": action, "tool": f"Figwright {__version__}", "provider": provider, "model": model}
    entry.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    log.append(entry)
    meta["provenance"] = log[-80:]


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def model_view(scene: dict) -> str:
    """The scene as shown to a model: geometry and text, no bulky payloads or style boilerplate."""
    light = strip_heavy(scene)
    style = light.get("style") or {}
    view = {"width": light.get("width"), "height": light.get("height"), "title": light.get("title", ""), "style": {"theme": style.get("theme"), "fontSize": style.get("fontSize")}, "nodes": light.get("nodes", []), "edges": light.get("edges", [])}
    return compact_json(view)


def apply_house_style(scene: dict, house: dict | None) -> None:
    """Carry the line look of the saved house style over to a new figure."""
    if not isinstance(house, dict):
        return
    for k in HOUSE_KEYS:
        if k in house:
            scene["style"][k] = house[k]


def _chat_json(provider: Provider, system: str, user: str, usage: dict, notes: list[str], images: list[bytes] | None = None, max_tokens: int = 8000) -> dict:
    result = provider.chat(system, user, images=images, json_mode=True, max_tokens=max_tokens)
    _add_usage(usage, result.usage)
    for n in result.notes:
        if n not in notes:
            notes.append(n)
    try:
        data = extract_json(result.text, dict)
    except JSONExtractError as exc:
        if result.truncated:
            raise GenerationError("The model ran out of output space before finishing the figure. Ask for a simpler figure, or pick a model with a larger output limit.", "truncated") from exc
        raise GenerationError(str(exc), "bad_json") from exc
    if result.truncated:
        notes.append("the model's answer was cut off at its output limit; the figure may be incomplete")
    return data


def _finish(scene: dict, snap: bool) -> tuple[dict, list[str], list[dict]]:
    scene, fixes = autofix(scene, snap=snap)
    return scene, fixes, lint(scene)


def _repair(provider: Provider, scene: dict, issues: list[dict], usage: dict, notes: list[str], images: list[bytes] | None = None, system: str | None = None, label: str = "layout repair") -> tuple[dict, list[dict]]:
    """One round of model-driven fixes. The result is kept only if the layout check does not get worse."""
    theme = (scene.get("style") or {}).get("theme")
    user = f"SCENE:\n{model_view(scene)}"
    if issues:
        user += f"\n\nPROBLEMS FOUND BY THE LAYOUT CHECK:\n{summarize(issues)}"
    try:
        data = _chat_json(provider, system or prompts.repair_system(theme), user, usage, notes, images=images, max_tokens=6000)
    except (GenerationError, ProviderError) as exc:
        notes.append(f"{label} skipped: {exc}")
        return scene, issues
    candidate, applied, _skipped = apply_ops(scene, data)
    if not applied:
        return scene, issues
    candidate = restore_heavy(candidate, scene)
    candidate, _fixes, new_issues = _finish(candidate, snap=False)
    if _score(new_issues) <= _score(issues):
        notes.append(f"{label}: {len(applied)} change(s)")
        return candidate, new_issues
    notes.append(f"{label} was discarded because it made the layout worse")
    return scene, issues


def render_for_model(scene: dict, max_side: int = 1400) -> bytes:
    from .render import render_png

    scale = min(2.0, max_side / max(float(scene.get("width", 1200)), float(scene.get("height", 800)), 1.0))
    return render_png(scene, scale=scale)


def _polish(scene: dict, issues: list[dict], cfg: dict, usage: dict, notes: list[str], progress: Progress) -> tuple[dict, list[dict]]:
    """Visual critique: a vision model looks at the rendering and proposes fixes."""
    try:
        vision = provider_for_role("vision", cfg)
    except ProviderError as exc:
        notes.append(f"visual critique skipped: {exc}")
        return scene, issues
    if vision.offline:
        return scene, issues
    progress("critique")
    try:
        png = render_for_model(scene)
    except Exception as exc:  # noqa: BLE001 - rendering problems must not sink the figure
        notes.append(f"visual critique skipped: could not render ({type(exc).__name__})")
        return scene, issues
    try:
        return _repair(vision, scene, issues, usage, notes, images=[png], system=prompts.critic_system(), label="visual critique")
    finally:
        vision.close()


# ----------------------------------------------------------------------- generate
def generate_figure(prompt: str, kind: str = "auto", theme: str | None = None, quality: str = "balanced", source: str = "", cfg: dict | None = None, progress: Progress | None = None) -> Outcome:
    """Text (plus optional source material) to a figure."""
    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    prompt = (prompt or "").strip()
    if not prompt and not (source or "").strip():
        raise GenerationError("Describe the figure you want (or attach source material).", "empty_prompt")
    if kind in ("auto", "", None):
        kind = offline.guess_kind(prompt) if prompt else "abstract"
    if kind not in offline.KINDS:
        raise GenerationError(f"Unknown figure kind {kind!r}.", "bad_kind")
    if quality not in QUALITIES:
        quality = "balanced"
    house = cfg.get("house_style") if isinstance(cfg.get("house_style"), dict) else None
    if theme not in THEMES:
        theme = (house or {}).get("theme") if (house or {}).get("theme") in THEMES else None
    src, clip_note = clip_source(source)
    notes: list[str] = [clip_note] if clip_note else []
    usage: dict = {}
    provider = provider_for_role("text", cfg)
    try:
        progress("plan")
        if provider.offline:
            notes.append("offline demo: built with text rules, no AI model was used")
            if kind == "illustration":
                scene = offline.concept_map(prompt or src[:400], theme)
            else:
                try:
                    scene = BUILDERS[kind](offline.content_for(kind, prompt, src), theme)
                except ValueError as exc:
                    raise GenerationError(f"The offline demo could not find the structure of this request ({exc}) Try arrows or numbered steps, or connect a model in Settings.", "offline_parse") from exc
        elif kind == "illustration":
            raw = _chat_json(provider, prompts.scene_system(theme), prompts.user_message(prompt, src), usage, notes, max_tokens=14000)
            scene = normalize_scene(raw, theme=theme, base_style=house)
            if not scene["nodes"]:
                raise GenerationError("The model returned an empty figure. Try again or rephrase the request.", "empty_scene")
        else:
            content = _chat_json(provider, prompts.structured_system(kind), prompts.user_message(prompt, src), usage, notes, max_tokens=7000)
            try:
                scene = BUILDERS[kind](content, theme)
            except ValueError as first:
                # One more try, telling the model what was missing.
                progress("retry")
                content = _chat_json(provider, prompts.structured_system(kind), prompts.user_message(prompt, src, f"Your previous answer could not be used: {first} Follow the shape exactly."), usage, notes, max_tokens=7000)
                try:
                    scene = BUILDERS[kind](content, theme)
                except ValueError as exc:
                    raise GenerationError(f"The model's answer could not be laid out ({exc}).", "bad_content") from exc
        warnings = (scene.get("meta") or {}).get("warnings") or []
        scene = normalize_scene(scene)
        scene["kind"] = kind
        apply_house_style(scene, house)
        progress("check")
        scene, fixes, issues = _finish(scene, snap=kind == "illustration")
        notes += fixes
        notes += [f"check: {w}" for w in warnings]
        if warnings:
            scene["meta"]["warnings"] = warnings
        if not provider.offline and kind == "illustration":
            if quality != "fast" and any(i["severity"] == "error" for i in issues):
                progress("repair")
                scene, issues = _repair(provider, scene, issues, usage, notes)
            if quality == "best":
                scene, issues = _polish(scene, issues, cfg, usage, notes, progress)
        stamp(scene, "generate", provider.id, provider.model, kind=kind, quality=quality, prompt_sha256=_digest(prompt), source_chars=len(source or "") or None)
        return Outcome(scene=scene, kind=kind, provider=provider.id, model=provider.model, notes=notes, issues=issues, usage=usage)
    finally:
        provider.close()


# -------------------------------------------------------------------------- refine
def refine_figure(scene: dict, instruction: str, selection: list[str] | None = None, cfg: dict | None = None, progress: Progress | None = None) -> Outcome:
    """Change an existing figure according to a plain-language instruction."""
    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    instruction = (instruction or "").strip()
    if not instruction:
        raise GenerationError("Say what should change.", "empty_prompt")
    scene = normalize_scene(scene)
    theme = scene["style"]["theme"]
    notes: list[str] = []
    usage: dict = {}
    summary = ""
    provider = provider_for_role("text", cfg)
    try:
        progress("plan")
        if provider.offline:
            ops = offline.refine_ops(scene, instruction)
            if not ops:
                lang = offline.guess_lang(instruction)
                return Outcome(scene=scene, kind=scene.get("kind", "illustration"), provider=provider.id, model=provider.model, notes=[offline.REFINE_HELP[lang]], issues=lint(scene), summary="")
            data: Any = {"ops": ops}
        else:
            user = f"SCENE:\n{model_view(scene)}"
            ids = [s for s in (selection or []) if isinstance(s, str)][:40]
            if ids:
                user += f"\n\nSELECTED ELEMENTS (\"this\", \"these\" and \"the selection\" refer to them): {', '.join(ids)}"
            user += f"\n\nINSTRUCTION:\n{instruction}"
            data = _chat_json(provider, prompts.refine_system(theme), user, usage, notes, max_tokens=9000)
            summary = str(data.get("summary") or "")[:300]
        new, applied, skipped = apply_ops(scene, data)
        new = restore_heavy(new, scene)
        if not applied:
            notes.append(summary or "nothing was changed")
            notes += [f"skipped: {s}" for s in skipped[:5]]
            return Outcome(scene=scene, kind=scene.get("kind", "illustration"), provider=provider.id, model=provider.model, notes=notes, issues=lint(scene), usage=usage, summary=summary)
        progress("check")
        new, fixes, issues = _finish(new, snap=False)
        notes += applied[:12] + fixes + [f"skipped: {s}" for s in skipped[:5]]
        stamp(new, "refine", provider.id, provider.model, instruction_sha256=_digest(instruction), changes=len(applied))
        return Outcome(scene=new, kind=new.get("kind", "illustration"), provider=provider.id, model=provider.model, notes=notes, issues=issues, usage=usage, summary=summary)
    finally:
        provider.close()


def polish_figure(scene: dict, cfg: dict | None = None, progress: Progress | None = None) -> Outcome:
    """Tidy an existing figure: automatic fixes first, then a model round on what is left."""
    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    scene = normalize_scene(scene)
    notes: list[str] = []
    usage: dict = {}
    progress("check")
    new, fixes, issues = _finish(scene, snap=True)
    notes += fixes
    provider = provider_for_role("text", cfg)
    try:
        if not provider.offline:
            if issues:
                progress("repair")
                new, issues = _repair(provider, new, issues, usage, notes)
            new, issues = _polish(new, issues, cfg, usage, notes, progress)
        if not notes:
            notes.append("nothing needed fixing")
        stamp(new, "polish", provider.id, provider.model)
        return Outcome(scene=new, kind=new.get("kind", "illustration"), provider=provider.id, model=provider.model, notes=notes, issues=issues, usage=usage)
    finally:
        provider.close()


# -------------------------------------------------------------------------- sketch
def sketch_to_figure(image: bytes, prompt: str = "", theme: str | None = None, cfg: dict | None = None, progress: Progress | None = None) -> Outcome:
    """A photo or scan of a hand-drawn sketch to a clean, editable figure."""
    from . import sketch

    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    if theme not in THEMES:
        theme = None
    progress("detect")
    try:
        hints = sketch.detect(image)
    except sketch.SketchError as exc:
        raise GenerationError(str(exc), "bad_image") from exc
    notes: list[str] = [f"computer vision found {sum(1 for s in hints['shapes'] if s['type'] != 'frame')} shape(s) and {len(hints['links'])} connector(s)"]
    usage: dict = {}
    provider = provider_for_role("vision", cfg)
    try:
        if provider.offline:
            if not hints["shapes"]:
                raise GenerationError("No closed shapes were found in the sketch. Draw boxes with closed outlines, or connect a vision model in Settings.", "empty_scene")
            notes.append("offline demo: shapes and connectors only. Handwriting is not read without a vision model, so type the labels in the editor")
            scene = sketch.hints_to_scene(hints, theme)
        else:
            progress("plan")
            import cv2
            import numpy as np

            gray = sketch.load_gray(image, 1500)
            ok, buf = cv2.imencode(".jpg", gray, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            picture = bytes(np.asarray(buf)) if ok else image
            user = prompts.user_message(prompt or "Recreate this hand-drawn sketch as a clean scientific figure.", extra="COMPUTER-VISION HINT:\n" + sketch.hints_text(hints))
            raw = _chat_json(provider, prompts.sketch_system(theme), user, usage, notes, images=[picture], max_tokens=14000)
            scene = normalize_scene(raw, theme=theme, base_style=cfg.get("house_style") if isinstance(cfg.get("house_style"), dict) else None)
            if not scene["nodes"]:
                raise GenerationError("The model returned an empty figure. Try a clearer photo.", "empty_scene")
        scene = normalize_scene(scene)
        progress("check")
        scene, fixes, issues = _finish(scene, snap=True)
        notes += fixes
        if not provider.offline and any(i["severity"] == "error" for i in issues):
            progress("repair")
            scene, issues = _repair(provider, scene, issues, usage, notes)
        stamp(scene, "sketch", provider.id, provider.model, image_sha256=hashlib.sha256(image).hexdigest()[:16])
        return Outcome(scene=scene, kind="illustration", provider=provider.id, model=provider.model, notes=notes, issues=issues, usage=usage)
    finally:
        provider.close()


# -------------------------------------------------------------------- image models
IMAGE_STYLES = {
    "flat": "Clean flat vector-style scientific illustration, simple shapes, soft pastel colour palette, white background.",
    "medical": "Professional medical illustration in the style of an anatomy atlas, accurate anatomy, soft shading, white background.",
    "3d": "Soft 3D render for a scientific journal cover, smooth materials, gentle studio lighting, plain light background.",
    "line": "Elegant black line-art scientific drawing with even stroke weight, no shading, white background.",
    "watercolor": "Delicate scientific watercolour illustration, light washes, white paper background.",
}
# Image models cannot spell. Labels are added afterwards as real, editable text.
NO_TEXT = "No text, no letters, no numbers, no labels, no captions, no watermark, no border."


def image_prompt(prompt: str, style: str = "flat") -> str:
    return f"{IMAGE_STYLES.get(style, IMAGE_STYLES['flat'])} {NO_TEXT}\n\nSubject: {prompt.strip()}"


def image_scene(png: bytes, title: str = "", theme: str | None = None, max_width: float = 1000.0) -> dict:
    """Wrap a raster image in a scene so that labels and arrows can be added on top."""
    from io import BytesIO

    from PIL import Image

    from .scene import new_scene

    try:
        with Image.open(BytesIO(png)) as im:
            w, h = im.size
            fmt = (im.format or "PNG").lower()
    except Exception as exc:  # noqa: BLE001 - PIL raises many types for bad data
        raise GenerationError("The image data could not be read.", "bad_image") from exc
    scale = min(1.0, max_width / max(1, w))
    dw, dh = round(w * scale, 1), round(h * scale, 1)
    scene = new_scene(width=dw + 80, height=dh + 80, theme=theme, kind="illustration", title=title)
    mime = "jpeg" if fmt in ("jpeg", "jpg") else ("webp" if fmt == "webp" else ("gif" if fmt == "gif" else "png"))
    scene["nodes"].append({"id": "image", "type": "image", "x": 40, "y": 40, "w": dw, "h": dh, "href": f"data:image/{mime};base64,{base64.b64encode(png).decode('ascii')}", "name": title or "image"})
    return scene


def illustrate(prompt: str, style: str = "flat", size: str = "1024x1024", theme: str | None = None, reference: bytes | None = None, cfg: dict | None = None, progress: Progress | None = None) -> Outcome:
    """A raster illustration from an image model, wrapped in an editable scene."""
    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    prompt = (prompt or "").strip()
    if not prompt:
        raise GenerationError("Describe the illustration you want.", "empty_prompt")
    if theme not in THEMES:
        theme = None
    provider = provider_for_role("image", cfg)
    try:
        progress("draw")
        png = provider.generate_image(image_prompt(prompt, style), size=size, reference=reference)
        scene = normalize_scene(image_scene(png, theme=theme))
        notes = ["image models cannot spell, so the picture was requested without text: add labels and arrows in the editor"]
        if provider.offline:
            notes.insert(0, "offline demo: this is a procedural placeholder, not an AI illustration. Choose an image model in Settings")
        stamp(scene, "illustrate", provider.id, provider.model, style=style, prompt_sha256=_digest(prompt))
        return Outcome(scene=scene, kind="illustration", provider=provider.id, model=provider.model, notes=notes, issues=lint(scene))
    finally:
        provider.close()


def redraw_region(image: bytes, box: tuple[float, float, float, float], prompt: str, style: str = "flat", cfg: dict | None = None, progress: Progress | None = None) -> tuple[bytes, dict]:
    """AI local redraw. Only pixels inside ``box`` (x0, y0, x1, y1 in image pixels) can change.

    The selected region is sent to the image model as a reference together with
    the instruction; the answer is scaled back and blended into the box with a
    feathered edge. Everything outside the box stays exactly as it was, which is
    guaranteed here by compositing and not left to the model's good manners.

    Returns ``(png bytes, info)``.
    """
    from . import raster

    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    prompt = (prompt or "").strip()
    if not prompt:
        raise GenerationError("Say what the selected region should become.", "empty_prompt")
    try:
        src = raster.open_image(image)
    except raster.ImageError as exc:
        raise GenerationError(str(exc), "bad_image") from exc
    x0, y0, x1, y1 = (int(round(float(v))) for v in box)
    x0, y0, x1, y1 = max(0, min(x0, x1)), max(0, min(y0, y1)), min(src.width, max(x0, x1)), min(src.height, max(y0, y1))
    if x1 - x0 < 16 or y1 - y0 < 16:
        raise GenerationError("Select a region of at least 16 by 16 pixels.", "bad_region")
    provider = provider_for_role("image", cfg)
    try:
        progress("draw")
        region = raster.crop(image, (x0, y0, x1, y1))
        # Ask for the supported size closest to the region's shape.
        ratio = (x1 - x0) / (y1 - y0)
        size = "1536x1024" if ratio > 1.3 else ("1024x1536" if ratio < 0.77 else "1024x1024")
        ask = (
            f"{IMAGE_STYLES.get(style, IMAGE_STYLES['flat'])} {NO_TEXT}\n\n"
            "Redraw the attached picture, which is one region cut from a larger figure. Keep its framing, perspective, lighting and colour palette "
            f"so that it still fits its surroundings, and change it as follows: {prompt}"
        )
        patch = provider.generate_image(ask, size=size, reference=region)
        out = raster.paste_region(image, patch, (x0, y0, x1, y1), feather=max(2, min(12, (x1 - x0) // 24, (y1 - y0) // 24)))
        notes = ["only the selected region was replaced; every pixel outside it is unchanged"]
        if provider.offline:
            notes.insert(0, "offline demo: the region was filled with a procedural placeholder, not an AI redraw. Choose an image model in Settings")
        return out, {"box": [x0, y0, x1, y1], "provider": provider.id, "model": provider.model, "notes": notes, "width": src.width, "height": src.height}
    except raster.ImageError as exc:
        raise GenerationError(str(exc), "bad_image") from exc
    finally:
        provider.close()


def suggest_plot(prompt: str, columns: list[dict], current: dict | None = None, cfg: dict | None = None, progress: Progress | None = None) -> tuple[dict, dict]:
    """Choose a chart for a table, or change the current one, from a sentence.

    Only the chart description (which columns, which kind, which options) comes
    from the model. The numbers are never sent anywhere except as the few
    example values in ``columns``, and the chart itself is drawn locally.

    Returns ``(spec, info)``.
    """
    progress = progress or _noop
    cfg = cfg if cfg is not None else load_config()
    provider = provider_for_role("text", cfg)
    notes: list[str] = []
    usage: dict = {}
    try:
        progress("plan")
        if provider.offline:
            notes.append("offline demo: the chart was chosen with text rules, no AI model was used")
            spec = offline.plot_edit(prompt, columns, current)
        else:
            lines = [f"- {c['name']} ({c.get('type', '')}, {c.get('unique', '?')} distinct): {', '.join(str(v) for v in (c.get('examples') or [])[:4])}" for c in columns[:60]]
            user = "Columns:\n" + "\n".join(lines)
            if current:
                keep = {k: v for k, v in current.items() if k in ("kind", "x", "y", "group", "label", "title", "xlabel", "ylabel", "error", "stats", "test", "fit", "points", "logx", "logy", "palette")}
                user += "\n\nCurrent chart (change only what the request asks for, repeat everything else):\n" + json.dumps(keep, ensure_ascii=False)
            user += "\n\nRequest: " + ((prompt or "").strip() or "Choose the most informative chart for this table.")
            spec = _chat_json(provider, prompts.PLOT_SYSTEM, user, usage, notes, max_tokens=1200)
        return spec, {"provider": provider.id, "model": provider.model, "notes": notes, "usage": usage}
    finally:
        provider.close()
