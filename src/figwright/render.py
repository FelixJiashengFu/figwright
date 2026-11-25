"""Scene to SVG (and, optionally, PNG).

The SVG uses only presentation attributes (no CSS classes, no markers, no
filters) so that it opens cleanly in Illustrator, Inkscape, Affinity, Figma and
PowerPoint. Every node and edge is its own ``<g data-id="...">`` group and all
text stays real text, which is what "editable vector" means in practice.

``web/scene.js`` is the JavaScript twin of this module; keep them in sync.
"""

from __future__ import annotations

import base64
import json
import re
from xml.sax.saxutils import escape, quoteattr, unescape

from . import __version__
from .geometry import edge_geometry, fmt, shape_points  # noqa: F401  (shape_points is re-exported)
from .icons import ICONS, icon_svg
from .pathutil import path_bbox
from .text import LINE_HEIGHT, text_width, wrap_text

NOTE_FILL = "#fff6bf"
NOTE_STROKE = "#d9bf3d"
METADATA_NS = "https://github.com/FelixJiashengFu/figwright/ns"
MAX_EMBED_BYTES = 2_000_000


def node_style(node: dict, style: dict) -> dict:
    """Resolve the effective paint of a node (explicit value, else type default)."""
    t = node.get("type")
    fill = node.get("fill")
    stroke = node.get("stroke")
    sw = node.get("strokeWidth")
    if t == "frame":
        fill = fill or style.get("panel", "#f4f6fa")
        stroke = stroke or style.get("mutedColor", "#5b6478")
        sw = 1.5 if sw is None else sw
    elif t == "text":
        fill = fill or "none"
        stroke = stroke or "none"
        sw = 0 if sw is None else sw
    elif t == "note":
        fill = fill or NOTE_FILL
        stroke = stroke or NOTE_STROKE
        sw = 1.5 if sw is None else sw
    elif t == "path":
        fill = fill or style.get("fill", "#dbe9f8")
        stroke = stroke or "none"
        sw = 0 if (sw is None and stroke == "none") else (style.get("strokeWidth", 2) if sw is None else sw)
    elif t == "image":
        fill = fill or "none"
        stroke = stroke or "none"
        sw = 0 if sw is None else sw
    else:
        fill = fill or style.get("fill", "#dbe9f8")
        stroke = stroke or style.get("stroke", "#3b4a66")
        sw = style.get("strokeWidth", 2) if sw is None else sw
    accent = node.get("accent")
    if not accent:
        soft = [c.lower() for c in style.get("soft", [])]
        palette = style.get("palette", [])
        if isinstance(fill, str) and fill.lower() in soft and palette:
            accent = palette[soft.index(fill.lower()) % len(palette)]
        else:
            accent = palette[0] if palette else stroke
    fs = float(node.get("fontSize") or (style.get("fontSize", 16) * (0.9 if t in ("frame", "note") else 1.0)))
    color = node.get("color") or (style.get("mutedColor", "#5b6478") if t == "frame" else ("#4a4215" if t == "note" else style.get("textColor", "#1f2a44")))
    bold = node.get("fontWeight") == "bold" or (t == "frame" and "fontWeight" not in node)
    return {
        "fill": fill,
        "stroke": stroke,
        "sw": float(sw),
        "accent": accent,
        "fs": fs,
        "color": color,
        "bold": bold,
        "italic": node.get("fontStyle") == "italic",
    }


def icon_layout(node: dict, style: dict) -> dict:
    """Where the pictogram and its caption go inside an icon node."""
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    ns = node_style(node, style)
    text = node.get("text") or ""
    if not text:
        size = max(8.0, min(w, h))
        return {"ix": x + (w - size) / 2, "iy": y + (h - size) / 2, "size": size, "lines": [], "ty": y + h}
    lines = wrap_text(text, w, ns["fs"], ns["bold"])
    th = len(lines) * ns["fs"] * LINE_HEIGHT
    size = max(16.0, min(w, h - th - 6))
    return {"ix": x + (w - size) / 2, "iy": y, "size": size, "lines": lines, "ty": y + size + 5}


def text_area(node: dict, style: dict) -> tuple[float, float, float, float, str, str]:
    """Text box of a node: (x, y, w, h, align, valign)."""
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    t = node.get("type")
    align = node.get("align")
    valign = node.get("valign")
    if t == "text":
        return x, y, w, h, align or "center", valign or "middle"
    if t == "frame":
        return x + 12, y + 9, max(10.0, w - 24), max(10.0, h - 18), align or "left", valign or "top"
    if t == "note":
        return x + 10, y + 8, max(10.0, w - 20), max(10.0, h - 16), align or "left", valign or "top"
    if t == "ellipse":
        return x + w * 0.14, y + h * 0.12, w * 0.72, h * 0.76, align or "center", valign or "middle"
    if t == "diamond":
        return x + w * 0.2, y + h * 0.2, w * 0.6, h * 0.6, align or "center", valign or "middle"
    if t == "hexagon":
        inset = min(w * 0.25, h * 0.5)
        return x + inset * 0.6 + 4, y + 4, max(10.0, w - inset * 1.2 - 8), h - 8, align or "center", valign or "middle"
    if t == "parallelogram":
        skew = min(w * 0.2, h * 0.5)
        return x + skew * 0.7 + 4, y + 4, max(10.0, w - skew * 1.4 - 8), h - 8, align or "center", valign or "middle"
    if t == "triangle":
        return x + w * 0.25, y + h * 0.42, w * 0.5, h * 0.5, align or "center", valign or "middle"
    if t == "cylinder":
        ry = min(h * 0.15, 16.0)
        return x + 10, y + ry * 2, max(10.0, w - 20), max(10.0, h - ry * 3), align or "center", valign or "middle"
    if t == "pill":
        pad = min(h * 0.3, w * 0.2)
        return x + pad, y + 4, max(10.0, w - 2 * pad), h - 8, align or "center", valign or "middle"
    return x + 10, y + 6, max(10.0, w - 20), max(10.0, h - 12), align or "center", valign or "middle"


def text_layout(node: dict, style: dict) -> dict | None:
    """Wrapped lines plus the anchor and first baseline for a node's text."""
    text = node.get("text")
    t = node.get("type")
    if not text or t in ("icon", "image", "path", "bilayer"):
        return None
    ns = node_style(node, style)
    ax, ay, aw, ah, align, valign = text_area(node, style)
    lines = wrap_text(text, aw, ns["fs"], ns["bold"])
    lh = ns["fs"] * LINE_HEIGHT
    total = len(lines) * lh
    if valign == "top":
        top = ay
    elif valign == "bottom":
        top = ay + ah - total
    else:
        top = ay + (ah - total) / 2.0
    if align == "left":
        tx, anchor = ax, "start"
    elif align == "right":
        tx, anchor = ax + aw, "end"
    else:
        tx, anchor = ax + aw / 2.0, "middle"
    return {"lines": lines, "x": tx, "y": top + lh / 2.0 + ns["fs"] * 0.35, "lh": lh, "anchor": anchor, "fs": ns["fs"], "bold": ns["bold"], "italic": ns["italic"], "color": ns["color"], "top": top, "height": total}


def _text_svg(lines: list[str], x: float, y: float, lh: float, anchor: str, fs: float, color: str, bold: bool, italic: bool) -> str:
    if not lines:
        return ""
    attrs = f'x="{fmt(x)}" y="{fmt(y)}" font-size="{fmt(fs)}" fill="{color}" text-anchor="{anchor}"'
    if bold:
        attrs += ' font-weight="bold"'
    if italic:
        attrs += ' font-style="italic"'
    if len(lines) == 1:
        return f"<text {attrs}>{escape(lines[0])}</text>"
    spans = "".join(f'<tspan x="{fmt(x)}" dy="{fmt(0 if i == 0 else lh)}">{escape(line) or " "}</tspan>' for i, line in enumerate(lines))
    return f"<text {attrs}>{spans}</text>"


def bilayer_geometry(node: dict) -> dict:
    """Lipid heads and tails of a ``bilayer`` band."""
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    r = max(2.0, min(h * 0.17, 9.0))
    pitch = 2 * r + 2.5
    count = max(1, int(w // pitch))
    start = x + (w - (count - 1) * pitch) / 2.0
    heads = []
    tails = []
    mid = y + h / 2.0
    for i in range(count):
        cx = start + i * pitch
        heads.append((cx, y + r + 1))
        heads.append((cx, y + h - r - 1))
        tails.append(((cx, y + 2 * r + 1), (cx, mid - 1)))
        tails.append(((cx, y + h - 2 * r - 1), (cx, mid + 1)))
    return {"r": r, "heads": heads, "tails": tails}


def path_transform(node: dict) -> tuple[float, float, float, float] | None:
    """Scale / translate that maps a path node's own coordinates into its box."""
    d = node.get("d") or ""
    vb = node.get("vb")
    if vb:
        bx, by, bw, bh = 0.0, 0.0, float(vb[0]), float(vb[1])
    else:
        box = path_bbox(d)
        if not box:
            return None
        bx, by, bw, bh = box
    if bw <= 0 or bh <= 0:
        return None
    sx, sy = node["w"] / bw, node["h"] / bh
    return sx, sy, node["x"] - bx * sx, node["y"] - by * sy


def _paint(ns: dict, dash: bool, fill: str | None = None) -> str:
    out = f'fill="{fill if fill is not None else ns["fill"]}"'
    if ns["stroke"] != "none" and ns["sw"] > 0:
        out += f' stroke="{ns["stroke"]}" stroke-width="{fmt(ns["sw"])}" stroke-linejoin="round"'
        if dash:
            out += f' stroke-dasharray="{fmt(ns["sw"] * 3.2)} {fmt(ns["sw"] * 2.4)}"'
    else:
        out += ' stroke="none"'
    return out


def _safe_href(href: str) -> str:
    """Only embedded raster data is drawn.

    A remote URL is refused on purpose: a figure should never fetch anything
    when it is opened, and a link that arrived in a model's answer is exactly
    how a tracking pixel would get in.
    """
    h = (href or "").strip()
    low = h.lower()
    if low.startswith("data:image/") and not low.startswith("data:image/svg"):
        return h
    return ""


def render_node(node: dict, style: dict, include_notes: bool = False) -> str:
    if node.get("hidden"):
        return ""
    t = node.get("type")
    if t == "note" and not include_notes:
        return ""
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    ns = node_style(node, style)
    dash = bool(node.get("dash"))
    body: list[str] = []
    if t in ("rect", "pill", "frame", "note"):
        if t == "pill":
            rx = h / 2.0
        elif t == "note":
            rx = 4.0
        else:
            rx = node.get("rx", style.get("cornerRadius", 10) if t == "rect" else 12)
        rx = max(0.0, min(float(rx), w / 2.0, h / 2.0))
        rxa = f' rx="{fmt(rx)}"' if rx else ""
        body.append(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}"{rxa} {_paint(ns, dash)}/>')
        if t == "note":
            c = min(14.0, w / 3, h / 3)
            body.append(f'<polygon points="{fmt(x + w - c)},{fmt(y + h)} {fmt(x + w)},{fmt(y + h - c)} {fmt(x + w - c)},{fmt(y + h - c)}" fill="{NOTE_STROKE}" stroke="none"/>')
    elif t == "ellipse":
        body.append(f'<ellipse cx="{fmt(x + w / 2)}" cy="{fmt(y + h / 2)}" rx="{fmt(w / 2)}" ry="{fmt(h / 2)}" {_paint(ns, dash)}/>')
    elif t in ("diamond", "hexagon", "parallelogram", "triangle"):
        pts = " ".join(f"{fmt(px)},{fmt(py)}" for px, py in shape_points(node) or [])
        body.append(f'<polygon points="{pts}" {_paint(ns, dash)}/>')
    elif t == "cylinder":
        ry = min(h * 0.15, 16.0)
        rxv = w / 2.0
        body.append(
            f'<path d="M{fmt(x)} {fmt(y + ry)} A{fmt(rxv)} {fmt(ry)} 0 0 1 {fmt(x + w)} {fmt(y + ry)} L{fmt(x + w)} {fmt(y + h - ry)} '
            f'A{fmt(rxv)} {fmt(ry)} 0 0 1 {fmt(x)} {fmt(y + h - ry)} Z" {_paint(ns, dash)}/>'
        )
        body.append(f'<path d="M{fmt(x)} {fmt(y + ry)} A{fmt(rxv)} {fmt(ry)} 0 0 0 {fmt(x + w)} {fmt(y + ry)}" {_paint(ns, dash, fill="none")}/>')
    elif t == "bilayer":
        g = bilayer_geometry(node)
        line = ns["stroke"] if ns["stroke"] != "none" else style.get("stroke", "#3b4a66")
        tails = "".join(f"M{fmt(a[0])} {fmt(a[1])} L{fmt(b[0])} {fmt(b[1])} " for a, b in g["tails"])
        body.append(f'<path d="{tails.strip()}" fill="none" stroke="{line}" stroke-width="{fmt(max(1.0, ns["sw"] * 0.6))}" stroke-linecap="round"/>')
        for hx, hy in g["heads"]:
            body.append(f'<circle cx="{fmt(hx)}" cy="{fmt(hy)}" r="{fmt(g["r"])}" fill="{ns["fill"]}" stroke="{line}" stroke-width="{fmt(max(1.0, ns["sw"] * 0.6))}"/>')
    elif t == "icon":
        lay = icon_layout(node, style)
        name = node.get("icon") if node.get("icon") in ICONS else "target"
        body.append(icon_svg(name, lay["ix"], lay["iy"], lay["size"], ns["fill"], ns["stroke"] if ns["stroke"] != "none" else style.get("stroke", "#3b4a66"), ns["accent"], ns["sw"] or 2))
        if lay["lines"]:
            lh = ns["fs"] * LINE_HEIGHT
            body.append(_text_svg(lay["lines"], x + w / 2, lay["ty"] + lh / 2 + ns["fs"] * 0.35, lh, "middle", ns["fs"], ns["color"], ns["bold"], ns["italic"]))
    elif t == "image":
        href = _safe_href(node.get("href", ""))
        if href:
            body.append(f'<image x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" preserveAspectRatio="xMidYMid meet" href={quoteattr(href)}/>')
        else:
            body.append(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" fill="#f1f3f6" stroke="#9aa3b2" stroke-width="1.5" stroke-dasharray="6 4"/>')
        if ns["stroke"] != "none" and ns["sw"] > 0:
            body.append(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" fill="none" stroke="{ns["stroke"]}" stroke-width="{fmt(ns["sw"])}"/>')
    elif t == "path":
        tr = path_transform(node)
        if tr and node.get("d"):
            sx, sy, tx, ty = tr
            scale = (abs(sx) + abs(sy)) / 2.0 or 1.0
            paint = f'fill="{ns["fill"]}"'
            if node.get("fillRule") == "evenodd":
                paint += ' fill-rule="evenodd"'
            if ns["stroke"] != "none" and ns["sw"] > 0:
                paint += f' stroke="{ns["stroke"]}" stroke-width="{fmt(ns["sw"] / scale)}" stroke-linejoin="round"'
            body.append(f'<path transform="translate({fmt(tx)} {fmt(ty)}) scale({sx:.5g} {sy:.5g})" d={quoteattr(node["d"])} {paint}/>')
    tl = text_layout(node, style)
    if tl:
        body.append(_text_svg(tl["lines"], tl["x"], tl["y"], tl["lh"], tl["anchor"], tl["fs"], tl["color"], tl["bold"], tl["italic"]))
    if not body:
        return ""
    attrs = f'data-id={quoteattr(str(node["id"]))} data-type="{t}"'
    if node.get("rotation"):
        attrs += f' transform="rotate({fmt(node["rotation"])} {fmt(x + w / 2)} {fmt(y + h / 2)})"'
    if node.get("opacity") is not None and node["opacity"] < 1:
        attrs += f' opacity="{node["opacity"]:.3g}"'
    return f"<g {attrs}>{''.join(body)}</g>"


def render_edge(scene: dict, edge: dict, nodes: dict[str, dict]) -> str:
    g = edge_geometry(scene, edge, nodes)
    if not g:
        return ""
    style = scene.get("style") or {}
    color, width = g["color"], g["width"]
    dash = f' stroke-dasharray="{fmt(width * 3.2)} {fmt(width * 2.6)}"' if g["dash"] else ""
    parts = [f'<path d="{g["path"]}" fill="none" stroke="{color}" stroke-width="{fmt(width)}" stroke-linecap="round" stroke-linejoin="round"{dash}/>']
    for head in g["heads"]:
        if head["kind"] == "arrow":
            pts = " ".join(f"{fmt(px)},{fmt(py)}" for px, py in head["points"])
            parts.append(f'<polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="{fmt(max(1.0, width * 0.5))}" stroke-linejoin="round"/>')
        elif head["kind"] == "inhibit":
            (ax, ay), (bx, by) = head["points"]
            parts.append(f'<path d="M{fmt(ax)} {fmt(ay)} L{fmt(bx)} {fmt(by)}" fill="none" stroke="{color}" stroke-width="{fmt(width * 1.4)}" stroke-linecap="round"/>')
        elif head["kind"] == "circle":
            parts.append(f'<circle cx="{fmt(head["center"][0])}" cy="{fmt(head["center"][1])}" r="{fmt(head["r"])}" fill="{color}"/>')
    label = edge.get("label")
    if label:
        fs = float(edge.get("fontSize") or style.get("fontSize", 16) * 0.82)
        lines = wrap_text(str(label), 220, fs)
        lh = fs * LINE_HEIGHT
        tw = max(text_width(line, fs) for line in lines)
        lx, ly = g["label"]
        total = len(lines) * lh
        bg = scene.get("background") or "#ffffff"
        if bg == "none":
            bg = "#ffffff"
        parts.append(f'<rect x="{fmt(lx - tw / 2 - 4)}" y="{fmt(ly - total / 2 - 1)}" width="{fmt(tw + 8)}" height="{fmt(total + 2)}" rx="3" fill="{bg}" fill-opacity="0.92"/>')
        parts.append(_text_svg(lines, lx, ly - total / 2 + lh / 2 + fs * 0.35, lh, "middle", fs, edge.get("labelColor") or style.get("textColor", "#1f2a44"), False, False))
    return f'<g data-id={quoteattr(str(edge["id"]))} data-type="edge">{"".join(parts)}</g>'


_IN_SVG = "@svg"  # placeholder: the picture is already in the SVG body, no need to store it twice


def _metadata(scene: dict) -> str:
    light = scene
    if any(n.get("type") == "image" and len(n.get("href") or "") > 400 for n in scene.get("nodes", [])):
        light = dict(scene, nodes=[dict(n, href=_IN_SVG) if n.get("type") == "image" and len(n.get("href") or "") > 400 and _safe_href(n["href"]) else n for n in scene["nodes"]])
    payload = json.dumps(light, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_EMBED_BYTES:
        return ""
    b64 = base64.b64encode(payload).decode("ascii")
    return f'<metadata><fw:scene xmlns:fw="{METADATA_NS}" version="{__version__}" encoding="base64">{b64}</fw:scene></metadata>'


def render_svg(scene: dict, include_notes: bool = False, embed_scene: bool = True, scale: float = 1.0) -> str:
    """Render a scene as a standalone SVG document."""
    w, h = float(scene.get("width", 1200)), float(scene.get("height", 800))
    style = scene.get("style") or {}
    family = style.get("fontFamily") or "Arial, sans-serif"
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{fmt(w * scale)}" height="{fmt(h * scale)}" viewBox="0 0 {fmt(w)} {fmt(h)}" font-family={quoteattr(family)}>'
    ]
    title = scene.get("title")
    if title:
        out.append(f"<title>{escape(str(title))}</title>")
    if embed_scene:
        out.append(_metadata(scene))
    bg = scene.get("background")
    if bg and bg != "none":
        out.append(f'<rect data-type="background" x="0" y="0" width="{fmt(w)}" height="{fmt(h)}" fill="{bg}"/>')
    nodes = {n["id"]: n for n in scene.get("nodes", [])}
    for node in scene.get("nodes", []):
        out.append(render_node(node, style, include_notes))
    for edge in scene.get("edges", []):
        out.append(render_edge(scene, edge, nodes))
    out.append("</svg>")
    return "".join(out)


_IMAGE_GROUP = re.compile(r"""<g data-id=(?:"([^"]*)"|'([^']*)') data-type="image"[^>]*>\s*<image\b[^>]*?\shref=(?:"([^"]*)"|'([^']*)')""")


def extract_scene_from_svg(svg_text: str) -> dict | None:
    """Recover the scene embedded by :func:`render_svg`, if there is one.

    Works on the text alone (no XML parser), so entity tricks in a hostile file have nothing to bite on.
    """
    marker = "<fw:scene"
    i = svg_text.find(marker)
    if i < 0:
        return None
    start = svg_text.find(">", i)
    end = svg_text.find("</fw:scene>", start)
    if start < 0 or end < 0:
        return None
    try:
        data = base64.b64decode(svg_text[start + 1 : end].strip())
        scene = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(scene, dict):
        return None
    nodes = scene.get("nodes")
    if isinstance(nodes, list) and any(isinstance(n, dict) and n.get("href") == _IN_SVG for n in nodes):
        pictures = {unescape(m.group(1) or m.group(2) or "", {"&quot;": '"', "&apos;": "'"}): unescape(m.group(3) or m.group(4) or "", {"&quot;": '"', "&apos;": "'"}) for m in _IMAGE_GROUP.finditer(svg_text)}
        for n in nodes:
            if isinstance(n, dict) and n.get("href") == _IN_SVG:
                n["href"] = pictures.get(str(n.get("id")), "")
    return scene


def sanitize_foreign_svg(svg_text: str) -> str:
    """Make somebody else's SVG safe to rasterise: no DTD, no scripts, no references outside the file."""
    if re.search(r"<!DOCTYPE|<!ENTITY", svg_text, re.I):
        # Checked before the DTD is stripped: an entity can name a local file or
        # expand without end, and a file that uses one is not worth repairing.
        if re.search(r"<!ENTITY", svg_text, re.I):
            raise ValueError("This SVG declares XML entities, which are not accepted.")
        svg_text = re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", svg_text, flags=re.I | re.S)
    svg_text = re.sub(r"<script\b.*?</script\s*>|<script\b[^>]*/>", "", svg_text, flags=re.I | re.S)
    svg_text = re.sub(r"<foreignObject\b.*?</foreignObject\s*>", "", svg_text, flags=re.I | re.S)

    def keep_local(m: re.Match) -> str:
        value = m.group(2).strip()
        return m.group(0) if value.startswith("#") or value.lower().startswith("data:image/") else f'{m.group(1)}=""'

    svg_text = re.sub(r"""((?:xlink:)?href)\s*=\s*["']([^"']*)["']""", keep_local, svg_text, flags=re.I)
    svg_text = re.sub(r"url\(\s*['\"]?\s*(?!#)[^)]*\)", "none", svg_text, flags=re.I)
    return svg_text


def foreign_svg_to_png(svg_text: str, max_side: int = 2400) -> bytes:
    """Rasterise an SVG that did not come from Figwright (for importing it as a picture)."""
    clean = sanitize_foreign_svg(svg_text)
    m = re.search(r"<svg\b[^>]*>", clean, re.I)
    if not m:
        raise ValueError("This file does not look like an SVG.")
    tag = m.group(0)
    size = 0.0
    vb = re.search(r"""viewBox\s*=\s*["']\s*[-\d.eE]+[\s,]+[-\d.eE]+[\s,]+([\d.eE]+)[\s,]+([\d.eE]+)""", tag)
    if vb:
        size = max(float(vb.group(1)), float(vb.group(2)))
    else:
        dims = [float(v) for v in re.findall(r"""\b(?:width|height)\s*=\s*["']\s*([\d.]+)""", tag)]
        size = max(dims) if dims else 0.0
    zoom = max(0.1, min(4.0, max_side / size)) if size > 0 else 1.0
    return svg_to_png(clean, scale=zoom)


def svg_to_png(svg: str, scale: float = 2.0, background: str | None = None) -> bytes:
    """Rasterise SVG to PNG bytes with resvg."""
    try:
        import resvg_py
    except ImportError as exc:  # pragma: no cover - resvg-py is a declared dependency
        raise RuntimeError("PNG export needs the 'resvg-py' package: pip install resvg-py") from exc
    kwargs = {"svg_string": svg, "zoom": float(scale)}
    if background and background != "none":
        kwargs["background"] = background
    return bytes(resvg_py.svg_to_bytes(**kwargs))


def render_png(scene: dict, scale: float = 2.0) -> bytes:
    return svg_to_png(render_svg(scene, embed_scene=False), scale=scale)
