"""The scene model: one JSON document describes a whole editable figure.

A scene is plain data (dicts and lists) so it can travel unchanged between the
LLM, the Python renderer / exporters and the browser editor::

    {
      "version": 1, "kind": "illustration", "title": "...",
      "width": 1200, "height": 800, "background": "#ffffff",
      "style": {...theme-derived defaults...},
      "nodes": [{"id": "n1", "type": "rect", "x": 80, "y": 60, "w": 180, "h": 70, "text": "..."}, ...],
      "edges": [{"id": "e1", "from": "n1", "to": "n2", "head": "arrow", "label": "..."}, ...],
      "meta": {...provenance...}
    }

``normalize_scene`` is deliberately forgiving: models misname fields, send
numbers as strings and invent node types. Everything that can be repaired is
repaired here so the rest of the code can trust the data.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from .geometry import visual_box
from .icons import ICONS, match_icon
from .text import LINE_HEIGHT, text_block_size
from .themes import DEFAULT_THEME, THEMES, get_theme, style_for_theme

SCENE_VERSION = 1

NODE_TYPES = (
    "rect",
    "ellipse",
    "diamond",
    "hexagon",
    "parallelogram",
    "cylinder",
    "pill",
    "triangle",
    "frame",
    "bilayer",
    "text",
    "icon",
    "image",
    "path",
    "note",
)
SHAPE_TYPES = ("rect", "ellipse", "diamond", "hexagon", "parallelogram", "cylinder", "pill", "triangle")
EDGE_HEADS = ("arrow", "inhibit", "none", "both", "circle")
EDGE_ROUTINGS = ("straight", "elbow", "curve")
SIDES = ("top", "right", "bottom", "left")

_TYPE_ALIASES = {
    "rectangle": "rect",
    "box": "rect",
    "square": "rect",
    "roundrect": "rect",
    "rounded": "rect",
    "rounded_rect": "rect",
    "roundedrect": "rect",
    "process": "rect",
    "card": "rect",
    "subprocess": "rect",
    "circle": "ellipse",
    "oval": "ellipse",
    "rhombus": "diamond",
    "decision": "diamond",
    "io": "parallelogram",
    "input": "parallelogram",
    "output": "parallelogram",
    "database": "cylinder",
    "db": "cylinder",
    "can": "cylinder",
    "terminator": "pill",
    "stadium": "pill",
    "capsule": "pill",
    "start": "pill",
    "end": "pill",
    "group": "frame",
    "container": "frame",
    "panel": "frame",
    "compartment": "frame",
    "region": "frame",
    "label": "text",
    "title": "text",
    "caption": "text",
    "annotation": "text",
    "img": "image",
    "picture": "image",
    "shape": "path",
    "freeform": "path",
    "comment": "note",
    "sticky": "note",
    "membrane": "bilayer",
}

_HEAD_ALIASES = {
    "activate": "arrow",
    "activation": "arrow",
    "->": "arrow",
    "triangle": "arrow",
    "normal": "arrow",
    "inhibition": "inhibit",
    "tbar": "inhibit",
    "t-bar": "inhibit",
    "bar": "inhibit",
    "block": "inhibit",
    "-|": "inhibit",
    "line": "none",
    "-": "none",
    "plain": "none",
    "<->": "both",
    "double": "both",
    "bidirectional": "both",
    "dot": "circle",
}

_ROUTING_ALIASES = {"orthogonal": "elbow", "step": "elbow", "ortho": "elbow", "curved": "curve", "bezier": "curve", "line": "straight", "direct": "straight"}

_SNAKE = {
    "font_size": "fontSize",
    "font_weight": "fontWeight",
    "font_style": "fontStyle",
    "stroke_width": "strokeWidth",
    "text_color": "color",
    "textColor": "color",
    "fontColor": "color",
    "font_color": "color",
    "corner_radius": "rx",
    "cornerRadius": "rx",
    "radius": "rx",
    "width": "w",
    "height": "h",
    "label": "text",
    "from_side": "fromSide",
    "to_side": "toSide",
    "fill_rule": "fillRule",
    "view_box": "vb",
    "viewBox": "vb",
    "src": "href",
    "url": "href",
}

_NAMED = {
    "black": "#000000",
    "white": "#ffffff",
    "red": "#e53935",
    "green": "#2e9e59",
    "blue": "#2f6fb7",
    "yellow": "#f2c230",
    "orange": "#f08c2e",
    "purple": "#8a5fc7",
    "pink": "#e87aa4",
    "gray": "#8a8f98",
    "grey": "#8a8f98",
    "lightgray": "#d9dce1",
    "lightgrey": "#d9dce1",
    "darkgray": "#4b5563",
    "darkgrey": "#4b5563",
    "brown": "#8d5a3b",
    "cyan": "#22b8cf",
    "teal": "#2a9d8f",
    "navy": "#1f2a44",
    "magenta": "#c2409a",
    "lightblue": "#cfe3f7",
    "lightgreen": "#d3efda",
    "lightyellow": "#fbf2c7",
    "gold": "#d4a514",
    "silver": "#c0c4cc",
    "beige": "#f3ead8",
    "maroon": "#7b2434",
    "olive": "#7a7a2a",
    "salmon": "#f4927c",
    "skyblue": "#8fc8ee",
    "steelblue": "#4a7fb0",
    "tomato": "#ee5c42",
    "violet": "#a57bd8",
    "indigo": "#4b4fa3",
    "crimson": "#d1234b",
    "coral": "#f1805b",
    "turquoise": "#3cc3b4",
    "lavender": "#e3defa",
    "ivory": "#fbf8ee",
}

_HEX3 = re.compile(r"^#([0-9a-fA-F]{3})$")
_HEX6 = re.compile(r"^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")
_RGB = re.compile(r"^rgba?\(\s*([\d.]+)%?\s*[, ]\s*([\d.]+)%?\s*[, ]\s*([\d.]+)%?")


def norm_color(value: Any, default: str | None = None) -> str | None:
    """Normalise a CSS-ish colour to ``#rrggbb`` or ``"none"``."""
    if value is None:
        return default
    if not isinstance(value, str):
        return default
    v = value.strip().lower()
    if v in ("none", "transparent", "", "null"):
        return "none" if v else default
    m = _HEX3.match(v)
    if m:
        return "#" + "".join(c * 2 for c in m.group(1))
    m = _HEX6.match(v)
    if m:
        return "#" + m.group(1)
    m = _RGB.match(v)
    if m:
        parts = [max(0, min(255, int(round(float(g))))) for g in m.groups()]
        return "#%02x%02x%02x" % tuple(parts)
    if v in _NAMED:
        return _NAMED[v]
    return default


def _num(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f == f and abs(f) != float("inf") else default
    if isinstance(value, str):
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", value)
        if m:
            return float(m.group(1))
    return default


def _round(v: float) -> float:
    r = round(float(v), 1)
    return int(r) if r == int(r) else r


def new_scene(width: float = 1200, height: float = 800, theme: str | None = None, kind: str = "illustration", title: str = "") -> dict:
    style = style_for_theme(theme)
    return {
        "version": SCENE_VERSION,
        "kind": kind,
        "title": title,
        "width": width,
        "height": height,
        "background": get_theme(style["theme"])["bg"],
        "style": style,
        "nodes": [],
        "edges": [],
        "meta": {},
    }


def _camel(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        out[_SNAKE.get(k, k)] = v
    return out


def _unique(base: str, used: set[str]) -> str:
    base = re.sub(r"[^\w\-]", "_", str(base))[:40] or "n"
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}_{i}" in used:
        i += 1
    used.add(f"{base}_{i}")
    return f"{base}_{i}"


def default_node_size(node: dict, style: dict) -> tuple[float, float]:
    t = node.get("type")
    fs = float(node.get("fontSize") or style.get("fontSize", 16))
    bold = node.get("fontWeight") == "bold"
    text = node.get("text") or ""
    if t == "text":
        w, h, _ = text_block_size(text, 420, fs, bold)
        return max(40.0, w + 8), max(fs * LINE_HEIGHT, h) + 4
    if t == "icon":
        if text:
            tw, th, _ = text_block_size(text, 150, fs, bold)
            return max(96.0, min(170.0, tw + 16)), 76 + th + 8
        return 80.0, 80.0
    if t == "image":
        return 240.0, 180.0
    if t == "frame":
        return 360.0, 240.0
    if t == "bilayer":
        return 600.0, 46.0
    if t == "note":
        return 180.0, 90.0
    if t == "path":
        return 120.0, 120.0
    tw, th, _ = text_block_size(text, 220, fs, bold)
    w = max(120.0, tw + 36)
    h = max(52.0, th + 24)
    if t in ("diamond", "hexagon"):
        w, h = w * 1.35, h * 1.5
    if t == "ellipse":
        w, h = w * 1.15, h * 1.2
    return w, h


def normalize_node(raw: Any, style: dict, used: set[str], index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    n = _camel(raw)
    t = str(n.get("type") or n.get("shape") or "rect").strip().lower()
    original_type = t
    t = _TYPE_ALIASES.get(t, t)
    if t not in NODE_TYPES:
        # An unknown type that happens to be an icon name becomes an icon.
        if t in ICONS:
            n["icon"] = t
            t = "icon"
        else:
            t = "rect"
    out: dict[str, Any] = {"id": _unique(n.get("id") or f"n{index + 1}", used), "type": t}

    text = n.get("text")
    if text is None and isinstance(n.get("title"), str):
        text = n["title"]
    if text is not None and not isinstance(text, str):
        text = "\n".join(str(x) for x in text) if isinstance(text, (list, tuple)) else str(text)
    if text:
        out["text"] = text.replace("\\n", "\n")

    if t == "icon":
        icon = str(n.get("icon") or n.get("name") or "").strip().lower()
        if icon not in ICONS:
            icon = match_icon(icon + " " + (out.get("text") or ""), default="target")
        out["icon"] = icon
    if t == "image":
        href = n.get("href")
        href = href if isinstance(href, str) else ""
        # Embedded data only: see render._safe_href.
        low = href.strip().lower()
        out["href"] = href if low.startswith("data:image/") and not low.startswith("data:image/svg") else ""
    if t == "path":
        d = n.get("d") or n.get("path")
        out["d"] = d if isinstance(d, str) else ""
        vb = n.get("vb")
        if isinstance(vb, (list, tuple)) and len(vb) >= 2:
            vw, vh = (_num(vb[-2]), _num(vb[-1])) if len(vb) >= 4 else (_num(vb[0]), _num(vb[1]))
            if vw and vh:
                out["vb"] = [vw, vh]
        if out["d"] and not out.get("vb"):
            # Move the path into a box of its own and record that box. Measuring
            # a curve properly needs a flattener, which the browser side has no
            # business carrying: with the box written down, both renderers place
            # the path identically instead of each guessing its extent.
            from .pathutil import path_bbox, transform_path

            box = path_bbox(out["d"])
            if box and box[2] > 0 and box[3] > 0:
                bx, by, bw, bh = box
                if abs(bx) > 1e-9 or abs(by) > 1e-9:
                    out["d"] = transform_path(out["d"], 1.0, 1.0, -bx, -by)
                out["vb"] = [round(bw, 3), round(bh, 3)]
        if n.get("fillRule") in ("evenodd", "nonzero"):
            out["fillRule"] = n["fillRule"]
    if t == "note" and isinstance(n.get("author"), str):
        out["author"] = n["author"][:60]

    for k in ("fontSize", "strokeWidth", "rx", "opacity", "rotation"):
        v = _num(n.get(k))
        if v is not None:
            out[k] = v
    if "fontSize" in out:
        out["fontSize"] = max(6.0, min(200.0, out["fontSize"]))
    if "opacity" in out:
        out["opacity"] = max(0.0, min(1.0, out["opacity"]))
        if out["opacity"] == 1:
            del out["opacity"]
    if "rotation" in out and not out["rotation"]:
        del out["rotation"]
    if "strokeWidth" in out:
        out["strokeWidth"] = max(0.0, min(40.0, out["strokeWidth"]))
    for k in ("fill", "stroke", "color", "accent"):
        c = norm_color(n.get(k))
        if c is not None:
            out[k] = c
    fw = str(n.get("fontWeight") or "").lower()
    if fw in ("bold", "600", "700", "800", "900", "semibold") or n.get("bold") is True:
        out["fontWeight"] = "bold"
    if str(n.get("fontStyle") or "").lower() == "italic" or n.get("italic") is True:
        out["fontStyle"] = "italic"
    if n.get("align") in ("left", "center", "right"):
        out["align"] = n["align"]
    if n.get("valign") in ("top", "middle", "bottom"):
        out["valign"] = n["valign"]
    dash = n.get("dash")
    if dash is True or str(n.get("style") or "").lower() in ("dashed", "dotted") or (isinstance(dash, str) and dash.lower() in ("dashed", "dotted", "true")):
        out["dash"] = True
    for k in ("hidden", "locked"):
        if n.get(k) is True:
            out[k] = True
    if isinstance(n.get("name"), str) and n["name"].strip():
        out["name"] = n["name"].strip()[:80]
    if isinstance(n.get("role"), str):
        out["role"] = n["role"][:40]
    if isinstance(n.get("group"), (str, int)) and not isinstance(n.get("group"), bool) and str(n["group"]).strip():
        out["group"] = re.sub(r"[^\w\-]", "_", str(n["group"]).strip())[:40]
    if original_type in ("title",) and "fontWeight" not in out:
        out["fontWeight"] = "bold"

    w, h = _num(n.get("w")), _num(n.get("h"))
    x, y = _num(n.get("x")), _num(n.get("y"))
    r = _num(n.get("r"))
    cx, cy = _num(n.get("cx")), _num(n.get("cy"))
    if r and not (w and h):
        w = h = 2 * r
    dw, dh = default_node_size(out, style)
    w = w if w and w > 0 else dw
    h = h if h and h > 0 else dh
    if x is None and cx is not None:
        x = cx - w / 2
    if y is None and cy is not None:
        y = cy - h / 2
    out["x"] = _round(x if x is not None else 40 + 30 * (index % 8))
    out["y"] = _round(y if y is not None else 40 + 30 * (index % 8))
    out["w"] = _round(max(4.0, min(20000.0, w)))
    out["h"] = _round(max(4.0, min(20000.0, h)))
    return out


def _endpoint(value: Any, ids: set[str]) -> Any:
    if isinstance(value, str) and value in ids:
        return value
    if isinstance(value, (int, float)) and str(value) in ids:
        return str(value)
    if isinstance(value, dict):
        px, py = _num(value.get("x")), _num(value.get("y"))
        if px is not None and py is not None:
            return [_round(px), _round(py)]
        if isinstance(value.get("id"), str) and value["id"] in ids:
            return value["id"]
    if isinstance(value, (list, tuple)) and len(value) == 2:
        px, py = _num(value[0]), _num(value[1])
        if px is not None and py is not None:
            return [_round(px), _round(py)]
    return None


def normalize_edge(raw: Any, ids: set[str], used: set[str], index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    e = _camel(raw)
    src = _endpoint(e.get("from", e.get("source", e.get("start"))), ids)
    dst = _endpoint(e.get("to", e.get("target", e.get("end"))), ids)
    if src is None or dst is None or (isinstance(src, str) and src == dst):
        return None
    out: dict[str, Any] = {"id": _unique(e.get("id") or f"e{index + 1}", used), "from": src, "to": dst}
    head = str(e.get("head") or e.get("arrow") or e.get("type") or e.get("kind") or "arrow").strip().lower()
    head = _HEAD_ALIASES.get(head, head)
    out["head"] = head if head in EDGE_HEADS else "arrow"
    routing = str(e.get("routing") or e.get("route") or "").strip().lower()
    routing = _ROUTING_ALIASES.get(routing, routing)
    if routing in EDGE_ROUTINGS:
        out["routing"] = routing
    text = e.get("text")
    if isinstance(text, (str, int, float)) and str(text).strip():
        out["label"] = str(text).strip()
    dash = e.get("dash")
    if dash is True or str(e.get("style") or "").lower() in ("dashed", "dotted") or (isinstance(dash, str) and dash.lower() in ("dashed", "dotted", "true")):
        out["dash"] = True
    c = norm_color(e.get("color") or e.get("stroke"))
    if c and c != "none":
        out["color"] = c
    wv = _num(e.get("w") if "w" in e else e.get("strokeWidth"))
    if wv:
        out["width"] = max(0.5, min(20.0, wv))
    fs = _num(e.get("fontSize"))
    if fs:
        out["fontSize"] = max(6.0, min(80.0, fs))
    for k in ("fromSide", "toSide"):
        if e.get(k) in SIDES:
            out[k] = e[k]
    if e.get("hidden") is True:
        out["hidden"] = True
    return out


def normalize_scene(raw: Any, theme: str | None = None, base_style: dict | None = None) -> dict:
    """Coerce arbitrary (possibly model-written) data into a valid scene."""
    if not isinstance(raw, dict):
        raise ValueError("A scene must be a JSON object.")
    src = raw.get("scene") if isinstance(raw.get("scene"), dict) else raw
    canvas = src.get("canvas") if isinstance(src.get("canvas"), dict) else {}
    raw_style = src.get("style") if isinstance(src.get("style"), dict) else {}
    theme_name = theme or raw_style.get("theme") or (base_style or {}).get("theme") or DEFAULT_THEME
    if theme_name not in THEMES:
        theme_name = DEFAULT_THEME
    style = style_for_theme(theme_name)
    if base_style:
        style.update({k: v for k, v in base_style.items() if k in style})
    for k, v in raw_style.items():
        if k in ("fontSize", "strokeWidth", "edgeWidth", "cornerRadius", "arrowSize"):
            nv = _num(v)
            if nv is not None and nv >= 0:
                style[k] = nv
        elif k in ("textColor", "mutedColor", "stroke", "fill", "edgeColor", "panel"):
            c = norm_color(v)
            if c:
                style[k] = c
        elif k == "fontFamily" and isinstance(v, str) and v.strip():
            style[k] = re.sub(r"[<>\"&]", "", v)[:200]
        elif k == "locked":
            style[k] = bool(v)
        elif k in ("palette", "soft") and isinstance(v, list):
            cols = [c for c in (norm_color(x) for x in v) if c and c != "none"]
            if cols:
                style[k] = cols
    style["theme"] = theme_name

    width = _num(src.get("width"), _num(canvas.get("width"), _num(canvas.get("w"), 1200.0)))
    height = _num(src.get("height"), _num(canvas.get("height"), _num(canvas.get("h"), 800.0)))
    width = max(100.0, min(12000.0, width or 1200.0))
    height = max(100.0, min(12000.0, height or 800.0))
    background = norm_color(src.get("background") or canvas.get("background"), get_theme(theme_name)["bg"])

    used: set[str] = set()
    nodes: list[dict] = []
    for i, n in enumerate(src.get("nodes") or src.get("elements") or []):
        node = normalize_node(n, style, used, i)
        if node:
            nodes.append(node)
    ids = {n["id"] for n in nodes}
    edges: list[dict] = []
    used_e: set[str] = set(ids)
    for i, e in enumerate(src.get("edges") or src.get("connections") or src.get("links") or []):
        edge = normalize_edge(e, ids, used_e, i)
        if edge:
            edges.append(edge)

    kind = src.get("kind") if isinstance(src.get("kind"), str) else "illustration"
    meta = src.get("meta") if isinstance(src.get("meta"), dict) else {}
    return {
        "version": SCENE_VERSION,
        "kind": kind,
        "title": str(src.get("title") or "")[:200],
        "width": _round(width),
        "height": _round(height),
        "background": background,
        "style": style,
        "nodes": nodes,
        "edges": edges,
        "meta": meta,
    }


def node_by_id(scene: dict) -> dict[str, dict]:
    return {n["id"]: n for n in scene.get("nodes", [])}


def bbox(node: dict) -> tuple[float, float, float, float]:
    return float(node["x"]), float(node["y"]), float(node["w"]), float(node["h"])


def scene_bounds(scene: dict) -> tuple[float, float, float, float] | None:
    """Bounding box (x0, y0, x1, y1) of all visible nodes and free edge points."""
    xs: list[float] = []
    ys: list[float] = []
    for n in scene.get("nodes", []):
        if n.get("hidden"):
            continue
        x0, y0, x1, y1 = visual_box(n)
        xs += [x0, x1]
        ys += [y0, y1]
    for e in scene.get("edges", []):
        for end in (e.get("from"), e.get("to")):
            if isinstance(end, list):
                xs.append(end[0])
                ys.append(end[1])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


_PLACEHOLDER = "@keep"


def strip_heavy(scene: dict) -> dict:
    """Copy of the scene without bulky payloads (embedded images, long paths).

    Used before sending a scene to a model: the placeholders tell the model the
    content exists, and :func:`restore_heavy` puts the originals back.
    """
    light = deepcopy(scene)
    light.pop("meta", None)
    for n in light.get("nodes", []):
        if n.get("type") == "image" and n.get("href"):
            n["href"] = _PLACEHOLDER
        if n.get("type") == "path" and len(n.get("d") or "") > 160:
            n["d"] = _PLACEHOLDER
    return light


def restore_heavy(scene: dict, original: dict) -> dict:
    """Put back payloads removed by :func:`strip_heavy` (matched by node id)."""
    orig = node_by_id(original)
    for n in scene.get("nodes", []):
        o = orig.get(n["id"])
        if not o or o.get("type") != n.get("type"):
            continue
        if n.get("type") == "image" and (not n.get("href") or n.get("href") == _PLACEHOLDER):
            n["href"] = o.get("href", "")
        if n.get("type") == "path":
            if not n.get("d") or n.get("d") == _PLACEHOLDER:
                n["d"] = o.get("d", "")
            for k in ("vb", "fillRule"):
                if k in o and k not in n:
                    n[k] = o[k]
    scene["nodes"] = [n for n in scene.get("nodes", []) if not (n.get("type") == "image" and n.get("href") == _PLACEHOLDER) and not (n.get("type") == "path" and n.get("d") in ("", _PLACEHOLDER))]
    ids = {n["id"] for n in scene["nodes"]}
    scene["edges"] = [e for e in scene.get("edges", []) if all(not isinstance(end, str) or end in ids for end in (e["from"], e["to"]))]
    return scene


def compact_json(scene: dict) -> str:
    return json.dumps(scene, ensure_ascii=False, separators=(",", ":"))


def scene_hash(scene: dict) -> str:
    body = {k: scene.get(k) for k in ("width", "height", "background", "nodes", "edges")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
