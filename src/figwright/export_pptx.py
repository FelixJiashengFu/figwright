"""Scene to an editable PowerPoint slide.

Nothing is flattened to a picture: boxes become native shapes with real text,
icons become groups of native shapes, traced artwork becomes freeform shapes
with true Bezier curves, and arrows become native connectors that are glued to
their shapes, so dragging a box in PowerPoint drags its arrows along.

What cannot be expressed natively is listed in the returned notes instead of
being faked silently (PowerPoint has no T-bar line ending, for one).
"""

from __future__ import annotations

import base64
import io
import math
from typing import Any

from .geometry import edge_geometry, side_anchor
from .icons import ICON_BOX, ICONS, icon_stroke_units, role_paint
from .pathutil import parse_path
from .render import LINE_HEIGHT, NOTE_FILL, NOTE_STROKE, bilayer_geometry, icon_layout, node_style, path_transform, shape_points, text_area, text_layout
from .text import text_width, wrap_text

EMU_PX = 9525.0
MAX_SLIDE_PX = 5300.0  # PowerPoint's limit is 56 inches
UNIT = 100  # custom-geometry units per pixel

# Connection-site index for each side, per preset shape (from the OOXML preset shape definitions).
_SITES = {
    "rect": {"top": 0, "left": 1, "bottom": 2, "right": 3},
    "ellipse": {"top": 0, "left": 2, "bottom": 4, "right": 6},
    "diamond": {"top": 0, "left": 1, "bottom": 2, "right": 3},
    "hexagon": {"right": 0, "left": 3},  # no site in the middle of the flat sides
    "parallelogram": {"top": 0, "right": 2, "bottom": 4, "left": 5},
    "triangle": {"top": 0, "left": 1, "bottom": 3, "right": 5},
    # Cylinders are left unglued on purpose: the site order of the "can" preset could not be verified.
}
_SIDE_NORMAL = {"top": (0.0, -1.0), "right": (1.0, 0.0), "bottom": (0.0, 1.0), "left": (-1.0, 0.0)}


class _Ctx:
    def __init__(self, scene: dict, slide, k: float, font: str) -> None:
        self.scene = scene
        self.style = scene.get("style") or {}
        self.slide = slide
        self.k = k  # EMU per scene pixel
        self.font = font
        self.anchors: dict[str, tuple[int, str]] = {}  # node id -> (shape id, site table key)
        self.notes: list[str] = []

    def emu(self, px: float) -> int:
        return int(round(px * self.k))

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


def _rgb(color: Any):
    from pptx.dml.color import RGBColor

    if isinstance(color, str) and len(color) == 7 and color.startswith("#"):
        try:
            return RGBColor.from_string(color[1:].upper())
        except ValueError:
            return None
    return None


def _strip_style(shape) -> None:
    """Drop the theme style reference so that only the explicit fill, line and font apply."""
    from pptx.oxml.ns import qn

    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)


def _fill(shape, color: Any, opacity: float | None = None) -> None:
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls

    rgb = _rgb(color)
    if rgb is None:
        shape.fill.background()
        return
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb
    if opacity is not None and opacity < 1:
        clr = shape.fill._xPr.solidFill.srgbClr
        clr.append(parse_xml(f'<a:alpha {nsdecls("a")} val="{int(round(max(0.0, opacity) * 100000))}"/>'))


def _line(ctx: _Ctx, shape, color: Any, width_px: float, dash: bool = False, opacity: float | None = None) -> None:
    from pptx.enum.dml import MSO_LINE
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls
    from pptx.util import Emu

    rgb = _rgb(color)
    if rgb is None or width_px <= 0:
        shape.line.fill.background()
        return
    shape.line.color.rgb = rgb
    shape.line.width = Emu(max(3175, ctx.emu(width_px)))
    if opacity is not None and opacity < 1:
        shape.line.fill._xPr.solidFill.srgbClr.append(parse_xml(f'<a:alpha {nsdecls("a")} val="{int(round(max(0.0, opacity) * 100000))}"/>'))
    if dash:
        shape.line.dash_style = MSO_LINE.DASH
    ln = shape.line._get_or_add_ln()
    ln.append(parse_xml(f'<a:round {nsdecls("a")}/>'))


def _line_ends(shape, head: str | None, tail: str | None) -> None:
    """Native line endings: ``head`` is at the start of the line, ``tail`` at its end."""
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls

    ln = shape.line._get_or_add_ln()
    for tag, kind in (("headEnd", head), ("tailEnd", tail)):
        if kind:
            ln.append(parse_xml(f'<a:{tag} {nsdecls("a")} type="{kind}" w="lg" len="lg"/>'))


def _finish(shape, name: str, rotation: float | None = None) -> None:
    shape.name = name[:60]
    if rotation:
        shape.rotation = float(rotation)


def _write_text(ctx: _Ctx, shape, text: str, fs_px: float, color: str, bold: bool, italic: bool, align: str, valign: str, insets: tuple[float, float, float, float], wrap: bool = True) -> None:
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls, qn
    from pptx.util import Emu, Pt

    tf = shape.text_frame
    tf.word_wrap = wrap
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = (Emu(max(0, ctx.emu(v))) for v in insets)
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "bottom": MSO_ANCHOR.BOTTOM}.get(valign, MSO_ANCHOR.MIDDLE)
    size = Pt(max(1.0, round(fs_px * ctx.k / 12700.0 * 2) / 2))
    rgb = _rgb(color)
    for i, para_text in enumerate(str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"left": PP_ALIGN.LEFT, "right": PP_ALIGN.RIGHT}.get(align, PP_ALIGN.CENTER)
        p.line_spacing = 1.08
        run = p.add_run()
        run.text = para_text
        f = run.font
        f.size = size
        f.bold = bool(bold)
        f.italic = bool(italic)
        f.name = ctx.font
        if rgb is not None:
            f.color.rgb = rgb
        latin = run._r.rPr.find(qn("a:latin"))
        if latin is not None:
            latin.addnext(parse_xml(f'<a:ea {nsdecls("a")} typeface="Microsoft YaHei"/>'))


def _custom_geometry(shape, subpaths: list[list[tuple]], w_px: float, h_px: float, filled: bool) -> None:
    """Replace a shape's preset geometry with paths made of M / L / C / Q / Z segments (pixel coordinates in its box)."""
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls, qn

    def pt(x: float, y: float) -> str:
        return f'<a:pt x="{int(round(x * UNIT))}" y="{int(round(y * UNIT))}"/>'

    body: list[str] = []
    for segs in subpaths:
        for seg in segs:
            op = seg[0]
            if op == "M":
                body.append(f"<a:moveTo>{pt(seg[1], seg[2])}</a:moveTo>")
            elif op == "L":
                body.append(f"<a:lnTo>{pt(seg[1], seg[2])}</a:lnTo>")
            elif op == "C":
                body.append(f"<a:cubicBezTo>{pt(seg[1], seg[2])}{pt(seg[3], seg[4])}{pt(seg[5], seg[6])}</a:cubicBezTo>")
            elif op == "Q":
                body.append(f"<a:quadBezTo>{pt(seg[1], seg[2])}{pt(seg[3], seg[4])}</a:quadBezTo>")
            elif op == "Z":
                body.append("<a:close/>")
    fill = "" if filled else ' fill="none"'
    xml = (
        f'<a:custGeom {nsdecls("a")}><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/>'
        f'<a:pathLst><a:path w="{max(1, int(round(w_px * UNIT)))}" h="{max(1, int(round(h_px * UNIT)))}"{fill}>{"".join(body)}</a:path></a:pathLst></a:custGeom>'
    )
    sp_pr = shape._element.spPr
    sp_pr.replace(sp_pr.find(qn("a:prstGeom")), parse_xml(xml))


def _shift(segs: list[tuple], dx: float, dy: float, sx: float = 1.0, sy: float = 1.0) -> list[tuple]:
    out = []
    for seg in segs:
        if seg[0] == "Z":
            out.append(seg)
        else:
            vals = list(seg[1:])
            out.append((seg[0], *[(v * (sx if i % 2 == 0 else sy) + (dx if i % 2 == 0 else dy)) for i, v in enumerate(vals)]))
    return out


def _bounds(segs: list[tuple]) -> tuple[float, float, float, float]:
    xs = [v for seg in segs if seg[0] != "Z" for v in seg[1::2]]
    ys = [v for seg in segs if seg[0] != "Z" for v in seg[2::2]]
    return min(xs), min(ys), max(xs), max(ys)


def _freeform(ctx: _Ctx, shapes, segs: list[tuple], filled: bool):
    """A custom-geometry shape for absolute-pixel path segments. Control points count towards the box (harmless)."""
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu

    x0, y0, x1, y1 = _bounds(segs)
    w, h = max(x1 - x0, 0.01), max(y1 - y0, 0.01)
    shape = shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(ctx.emu(x0)), Emu(ctx.emu(y0)), Emu(max(1, ctx.emu(w))), Emu(max(1, ctx.emu(h))))
    _strip_style(shape)
    _custom_geometry(shape, [_shift(segs, -x0, -y0)], w, h, filled)
    return shape


def _builtin_inset(node: dict, style: dict) -> tuple[float, float]:
    """How far PowerPoint's own text rectangle sits inside the shape box, for the presets used here."""
    t, w, h = node.get("type"), node["w"], node["h"]
    if t == "ellipse":
        return 0.1464 * w, 0.1464 * h
    if t == "diamond":
        return 0.25 * w, 0.25 * h
    if t in ("rect", "pill", "frame"):
        rx = h / 2.0 if t == "pill" else float(node.get("rx", style.get("cornerRadius", 10) if t == "rect" else 12))
        rx = max(0.0, min(rx, w / 2.0, h / 2.0))
        return rx * 0.29289, rx * 0.29289
    return 0.0, 0.0


def _shape_text(ctx: _Ctx, shape, node: dict) -> None:
    tl = text_layout(node, ctx.style)
    if not tl:
        return
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    ax, ay, aw, ah, align, valign = text_area(node, ctx.style)
    t = node.get("type")
    if t in ("hexagon", "parallelogram", "triangle", "cylinder"):
        insets = (0.0, 0.0, 0.0, 0.0)  # these presets already have a text rectangle close to ours
    else:
        bx, by = _builtin_inset(node, ctx.style)
        insets = (max(0.0, ax - x - bx), max(0.0, ay - y - by), max(0.0, x + w - ax - aw - bx), max(0.0, y + h - ay - ah - by))
    wrap = not (t == "text" and len(tl["lines"]) == 1)
    _write_text(ctx, shape, node["text"], tl["fs"], tl["color"], tl["bold"], tl["italic"], align, valign, insets, wrap)


def _preset(ctx: _Ctx, shapes, node: dict):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu

    t = node.get("type")
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    ns = node_style(node, ctx.style)
    box = (Emu(ctx.emu(x)), Emu(ctx.emu(y)), Emu(max(1, ctx.emu(w))), Emu(max(1, ctx.emu(h))))
    small = max(1.0, min(w, h))
    adj: float | None = None
    site = "rect"
    if t in ("rect", "pill", "frame", "note"):
        rx = h / 2.0 if t == "pill" else (4.0 if t == "note" else float(node.get("rx", ctx.style.get("cornerRadius", 10) if t == "rect" else 12)))
        rx = max(0.0, min(rx, w / 2.0, h / 2.0))
        kind = MSO_SHAPE.ROUNDED_RECTANGLE if rx > 0.5 else MSO_SHAPE.RECTANGLE
        adj = min(0.5, rx / small) if rx > 0.5 else None
    elif t == "ellipse":
        kind, site = MSO_SHAPE.OVAL, "ellipse"
    elif t == "diamond":
        kind, site = MSO_SHAPE.DIAMOND, "diamond"
    elif t == "hexagon":
        kind, site, adj = MSO_SHAPE.HEXAGON, "hexagon", min(w * 0.25, h * 0.5) / small
    elif t == "parallelogram":
        kind, site, adj = MSO_SHAPE.PARALLELOGRAM, "parallelogram", min(w * 0.2, h * 0.5) / small
    elif t == "triangle":
        kind, site = MSO_SHAPE.ISOSCELES_TRIANGLE, "triangle"
    elif t == "cylinder":
        kind, site, adj = MSO_SHAPE.CAN, "cylinder", 2.0 * min(h * 0.15, 16.0) / small
    else:
        kind = MSO_SHAPE.RECTANGLE
    shape = shapes.add_shape(kind, *box)
    _strip_style(shape)
    if adj is not None and len(shape.adjustments):
        shape.adjustments[0] = float(adj)
    opacity = node.get("opacity")
    _fill(shape, ns["fill"], opacity)
    _line(ctx, shape, ns["stroke"], ns["sw"], bool(node.get("dash")), opacity)
    _shape_text(ctx, shape, node)
    ctx.anchors[node["id"]] = (shape.shape_id, site)
    return shape


def _text_box(ctx: _Ctx, shapes, node: dict):
    from pptx.util import Emu

    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    tl = text_layout(node, ctx.style)
    grow = 0.0
    if tl and len(tl["lines"]) > 1:
        grow = w * 0.03  # a little slack: PowerPoint's own line breaking differs slightly from the estimate
    shape = shapes.add_textbox(Emu(ctx.emu(x - grow)), Emu(ctx.emu(y)), Emu(max(1, ctx.emu(w + 2 * grow))), Emu(max(1, ctx.emu(h))))
    ns = node_style(node, ctx.style)
    if ns["fill"] != "none":
        _fill(shape, ns["fill"], node.get("opacity"))
    if ns["stroke"] != "none" and ns["sw"] > 0:
        _line(ctx, shape, ns["stroke"], ns["sw"], bool(node.get("dash")))
    _shape_text(ctx, shape, node)
    ctx.anchors[node["id"]] = (shape.shape_id, "rect")
    return shape


def _role(role: str, fill: str, stroke: str, accent: str, sw_px: float) -> tuple[str | None, str | None, float]:
    paint = role_paint(role, fill, stroke, accent, 1.0)
    f = paint.get("fill")
    s = paint.get("stroke")
    width = sw_px * float(paint.get("stroke-width", 1.0)) if s and s != "none" else 0.0
    return (None if f in (None, "none") else f), (None if s in (None, "none") else s), width


def _icon(ctx: _Ctx, shapes, node: dict):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu

    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    ns = node_style(node, ctx.style)
    lay = icon_layout(node, ctx.style)
    name = node.get("icon") if node.get("icon") in ICONS else "target"
    stroke = ns["stroke"] if ns["stroke"] != "none" else ctx.style.get("stroke", "#3b4a66")
    size, ix, iy = lay["size"], lay["ix"], lay["iy"]
    s = size / ICON_BOX
    sw_px = icon_stroke_units(size, ns["sw"] or 2) * s
    group = shapes.add_group_shape()
    # An invisible box the size of the node: it fixes the group's extent and gives connectors something to hold.
    anchor = group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(ctx.emu(x)), Emu(ctx.emu(y)), Emu(max(1, ctx.emu(w))), Emu(max(1, ctx.emu(h))))
    _strip_style(anchor)
    anchor.fill.background()
    anchor.line.fill.background()
    anchor.name = "anchor"
    ctx.anchors[node["id"]] = (anchor.shape_id, "rect")
    for prim in ICONS[name]:
        kind, role = prim[0], prim[-1]
        fill, line, width = _role(role, ns["fill"], stroke, ns["accent"], sw_px)
        if kind in ("c", "e"):
            cx, cy = prim[1], prim[2]
            rx, ry = (prim[3], prim[3]) if kind == "c" else (prim[3], prim[4])
            part = group.shapes.add_shape(MSO_SHAPE.OVAL, Emu(ctx.emu(ix + (cx - rx) * s)), Emu(ctx.emu(iy + (cy - ry) * s)), Emu(max(1, ctx.emu(2 * rx * s))), Emu(max(1, ctx.emu(2 * ry * s))))
            _strip_style(part)
        elif kind == "r":
            px, py, pw, ph, pr = prim[1], prim[2], prim[3], prim[4], prim[5]
            part = group.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if pr else MSO_SHAPE.RECTANGLE, Emu(ctx.emu(ix + px * s)), Emu(ctx.emu(iy + py * s)), Emu(max(1, ctx.emu(pw * s))), Emu(max(1, ctx.emu(ph * s))))
            _strip_style(part)
            if pr and len(part.adjustments):
                part.adjustments[0] = min(0.5, pr / max(0.01, min(pw, ph)))
        else:
            if kind == "p":
                pts = prim[1]
                segs: list[tuple] = [("M", pts[0], pts[1])] + [("L", pts[i], pts[i + 1]) for i in range(2, len(pts), 2)]
                closed = bool(prim[2])
                if closed:
                    segs.append(("Z",))
            else:
                segs = parse_path(prim[1])
                closed = any(seg[0] == "Z" for seg in segs)
            if not segs:
                continue
            part = _freeform(ctx, group.shapes, _shift(segs, ix, iy, s, s), filled=fill is not None)
            if not closed and fill is not None:
                fill = None if role in ("l", "la") else fill
        _fill(part, fill)
        _line(ctx, part, line, width)
        part.name = f"{name} part"
    if lay["lines"]:
        lh = ns["fs"] * LINE_HEIGHT
        box = group.shapes.add_textbox(Emu(ctx.emu(x - 4)), Emu(ctx.emu(lay["ty"])), Emu(max(1, ctx.emu(w + 8))), Emu(max(1, ctx.emu(len(lay["lines"]) * lh + 2))))
        _write_text(ctx, box, node.get("text") or "", ns["fs"], ns["color"], ns["bold"], ns["italic"], "center", "top", (0, 0, 0, 0), wrap=len(lay["lines"]) > 1)
        box.name = "caption"
    return group


def _bilayer(ctx: _Ctx, shapes, node: dict):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu

    ns = node_style(node, ctx.style)
    g = bilayer_geometry(node)
    line = ns["stroke"] if ns["stroke"] != "none" else ctx.style.get("stroke", "#3b4a66")
    lw = max(1.0, ns["sw"] * 0.6)
    group = shapes.add_group_shape()
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    anchor = group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(ctx.emu(x)), Emu(ctx.emu(y)), Emu(max(1, ctx.emu(w))), Emu(max(1, ctx.emu(h))))
    _strip_style(anchor)
    anchor.fill.background()
    anchor.line.fill.background()
    anchor.name = "anchor"
    ctx.anchors[node["id"]] = (anchor.shape_id, "rect")
    segs: list[tuple] = []
    for a, b in g["tails"]:
        segs += [("M", a[0], a[1]), ("L", b[0], b[1])]
    if segs:
        tails = _freeform(ctx, group.shapes, segs, filled=False)
        tails.fill.background()
        _line(ctx, tails, line, lw)
        tails.name = "lipid tails"
    r = g["r"]
    for hx, hy in g["heads"]:
        head = group.shapes.add_shape(MSO_SHAPE.OVAL, Emu(ctx.emu(hx - r)), Emu(ctx.emu(hy - r)), Emu(max(1, ctx.emu(2 * r))), Emu(max(1, ctx.emu(2 * r))))
        _strip_style(head)
        _fill(head, ns["fill"])
        _line(ctx, head, line, lw)
        head.name = "lipid head"
    return group


def decode_data_url(href: str) -> bytes | None:
    if not isinstance(href, str) or not href.startswith("data:image/") or ";base64," not in href:
        return None
    try:
        return base64.b64decode(href.split(";base64,", 1)[1], validate=False)
    except (ValueError, IndexError):
        return None


def _image(ctx: _Ctx, shapes, node: dict):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu

    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    data = decode_data_url(node.get("href", ""))
    shape = None
    if data:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as im:
                iw, ih = im.size
                if (im.format or "").upper() not in ("PNG", "JPEG", "GIF", "BMP", "TIFF"):
                    buf = io.BytesIO()
                    im.convert("RGBA").save(buf, format="PNG")
                    data = buf.getvalue()
            scale = min(w / iw, h / ih)  # same as preserveAspectRatio="xMidYMid meet"
            dw, dh = iw * scale, ih * scale
            shape = shapes.add_picture(io.BytesIO(data), Emu(ctx.emu(x + (w - dw) / 2)), Emu(ctx.emu(y + (h - dh) / 2)), Emu(max(1, ctx.emu(dw))), Emu(max(1, ctx.emu(dh))))
        except Exception:  # noqa: BLE001 - an unreadable embedded image becomes a placeholder
            shape = None
    if shape is None:
        shape = shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(ctx.emu(x)), Emu(ctx.emu(y)), Emu(max(1, ctx.emu(w))), Emu(max(1, ctx.emu(h))))
        _strip_style(shape)
        _fill(shape, "#f1f3f6")
        _line(ctx, shape, "#9aa3b2", 1.5, dash=True)
        if node.get("href"):
            ctx.note("a linked (not embedded) image was exported as a placeholder: embed the image in the figure first")
    ctx.anchors[node["id"]] = (shape.shape_id, "rect")
    return shape


def _path(ctx: _Ctx, shapes, node: dict):
    tr = path_transform(node)
    segs = parse_path(node.get("d") or "")
    if not tr or not segs:
        return None
    sx, sy, tx, ty = tr
    ns = node_style(node, ctx.style)
    shape = _freeform(ctx, shapes, _shift(segs, tx, ty, sx, sy), filled=ns["fill"] != "none")
    _fill(shape, ns["fill"], node.get("opacity"))
    _line(ctx, shape, ns["stroke"], ns["sw"], bool(node.get("dash")))
    ctx.anchors[node["id"]] = (shape.shape_id, "rect")
    return shape


def _node(ctx: _Ctx, node: dict, include_notes: bool):
    t = node.get("type")
    if node.get("hidden") or (t == "note" and not include_notes):
        return
    shapes = ctx.slide.shapes
    if t == "text":
        shape = _text_box(ctx, shapes, node)
    elif t == "icon":
        shape = _icon(ctx, shapes, node)
    elif t == "bilayer":
        shape = _bilayer(ctx, shapes, node)
    elif t == "image":
        shape = _image(ctx, shapes, node)
    elif t == "path":
        shape = _path(ctx, shapes, node)
    else:
        if t == "note":
            node = {**node, "fill": node.get("fill") or NOTE_FILL, "stroke": node.get("stroke") or NOTE_STROKE}
        shape = _preset(ctx, shapes, node)
    if shape is not None:
        _finish(shape, str(node.get("name") or node.get("text") or node["id"]).split("\n")[0], node.get("rotation"))


# ------------------------------------------------------------------ connectors
def _rot(v: tuple[float, float], quarter: int) -> tuple[float, float]:
    """Rotate a vector clockwise (screen coordinates) by ``quarter`` x 90 degrees."""
    x, y = v
    for _ in range(quarter % 4):
        x, y = -y, x
    return x, y


def _fit_connector(pts: list[tuple[float, float]], kind: str) -> dict | None:
    """Placement of a bent connector preset whose route equals ``pts`` exactly, or ``None``.

    A connector's own path starts at its top-left corner and ends at the
    bottom-right one. Flips mirror it inside its box and the rotation turns the
    box about its centre, so for each quarter turn there is exactly one box and
    flip pair that joins the two end points; the route decides which turn fits.
    """
    s, e = pts[0], pts[-1]
    cx, cy = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0
    for quarter in (0, 1, 3, 2):
        d = _rot((e[0] - s[0], e[1] - s[1]), -quarter)
        w, h = abs(d[0]), abs(d[1])
        flip_h, flip_v = d[0] < -1e-6, d[1] < -1e-6
        eu = _rot((-1.0 if flip_h else 1.0, 0.0), quarter)  # where the path's first leg points on the slide
        ev = _rot((0.0, -1.0 if flip_v else 1.0), quarter)
        adj = None
        if kind == "bent2":
            if len(pts) != 3 or w < 0.5 or h < 0.5:
                return None
            corner = (s[0] + eu[0] * w, s[1] + eu[1] * w)
            if math.dist(corner, pts[1]) > 0.6:
                continue
        else:
            if len(pts) != 4 or w < 0.5:
                continue
            x1 = (pts[1][0] - s[0]) * eu[0] + (pts[1][1] - s[1]) * eu[1]
            p1 = (s[0] + eu[0] * x1, s[1] + eu[1] * x1)
            p2 = (p1[0] + ev[0] * h, p1[1] + ev[1] * h)
            if math.dist(p1, pts[1]) > 0.6 or math.dist(p2, pts[2]) > 0.6:
                continue
            adj = x1 / w
            if abs(adj) > 40:
                continue
        return {"x": cx - w / 2.0, "y": cy - h / 2.0, "w": w, "h": h, "rot": quarter * 90, "flip_h": flip_h, "flip_v": flip_v, "adj": adj}
    return None


def _fit_curve(s: tuple[float, float], e: tuple[float, float], n1: tuple[float, float], n2: tuple[float, float]) -> tuple[str, dict] | None:
    """Preset for a curved connector leaving along ``n1`` and arriving against ``n2``."""
    d = (e[0] - s[0], e[1] - s[1])
    ahead = d[0] * n1[0] + d[1] * n1[1]
    if ahead <= 1.0:
        return None
    quarter = 0 if abs(n1[0]) > 0.5 else 1
    local = _rot(d, -quarter)
    w, h = abs(local[0]), abs(local[1])
    place = {"x": (s[0] + e[0]) / 2.0 - w / 2.0, "y": (s[1] + e[1]) / 2.0 - h / 2.0, "w": w, "h": h, "rot": quarter * 90, "flip_h": local[0] < -1e-6, "flip_v": local[1] < -1e-6, "adj": None}
    if abs(n1[0] + n2[0]) < 1e-6 and abs(n1[1] + n2[1]) < 1e-6:
        return ("curvedConnector3", place) if w >= 0.5 else None
    if abs(n1[0] * n2[0] + n1[1] * n2[1]) < 1e-6 and -(d[0] * n2[0] + d[1] * n2[1]) > 1.0 and w >= 0.5 and h >= 0.5:
        return "curvedConnector2", place
    return None


def _place_connector(ctx: _Ctx, conn, prst: str, place: dict) -> None:
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls, qn

    sp_pr = conn._element.spPr
    xfrm = sp_pr.find(qn("a:xfrm"))
    for attr in ("rot", "flipH", "flipV"):
        if attr in xfrm.attrib:
            del xfrm.attrib[attr]
    if place["rot"]:
        xfrm.set("rot", str(int(place["rot"] * 60000)))
    if place["flip_h"]:
        xfrm.set("flipH", "1")
    if place["flip_v"]:
        xfrm.set("flipV", "1")
    off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
    off.set("x", str(ctx.emu(place["x"])))
    off.set("y", str(ctx.emu(place["y"])))
    ext.set("cx", str(max(0, ctx.emu(place["w"]))))
    ext.set("cy", str(max(0, ctx.emu(place["h"]))))
    av = ""
    if place.get("adj") is not None:
        av = f'<a:gd name="adj1" fmla="val {int(round(place["adj"] * 100000))}"/>'
    sp_pr.replace(sp_pr.find(qn("a:prstGeom")), parse_xml(f'<a:prstGeom {nsdecls("a")} prst="{prst}"><a:avLst>{av}</a:avLst></a:prstGeom>'))


def _glue(ctx: _Ctx, conn, end: Any, point: tuple[float, float], side: str | None, nodes: dict[str, dict], begin: bool) -> None:
    """Attach a connector end to its shape, when the shape has a connection site where the line ends."""
    if not isinstance(end, str) or end not in ctx.anchors:
        return
    shape_id, table = ctx.anchors[end]
    node = nodes.get(end)
    if node is None or node.get("rotation"):
        return
    if side is None:
        best, best_d = None, 1e9
        for cand in ("top", "right", "bottom", "left"):
            d = math.dist(side_anchor(node, cand, 0.0), point)
            if d < best_d:
                best, best_d = cand, d
        # A free-angle line ends somewhere on the outline; glue it only where a site is close enough to look the same.
        if best is None or best_d > max(10.0, 0.22 * min(node["w"], node["h"])):
            return
        side = best
    idx = _SITES.get(table, {}).get(side)
    if idx is None:
        return
    cnv = conn._element.nvCxnSpPr.cNvCxnSpPr
    cxn = cnv.get_or_add_stCxn() if begin else cnv.get_or_add_endCxn()
    cxn.id = shape_id
    cxn.idx = idx


def _edge(ctx: _Ctx, edge: dict, nodes: dict[str, dict]) -> None:
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.util import Emu

    g = edge_geometry(ctx.scene, edge, nodes)
    if not g:
        return
    shapes = ctx.slide.shapes
    pts = [(float(x), float(y)) for x, y in g["points"]]
    head = edge.get("head", "arrow")
    tail_end = {"arrow": "triangle", "both": "triangle", "circle": "oval"}.get(head)
    head_end = "triangle" if head == "both" else None
    routing = edge.get("routing") or "straight"
    explicit = bool(edge.get("fromSide") or edge.get("toSide"))
    sided = routing in ("elbow", "curve") or explicit
    side_a = side_b = None
    if sided:
        from .geometry import auto_sides, center

        ca = center(nodes[edge["from"]]) if isinstance(edge["from"], str) and edge["from"] in nodes else tuple(edge["from"])
        cb = center(nodes[edge["to"]]) if isinstance(edge["to"], str) and edge["to"] in nodes else tuple(edge["to"])
        auto_a, auto_b = auto_sides(ca, cb)
        side_a, side_b = edge.get("fromSide") or auto_a, edge.get("toSide") or auto_b

    conn = None
    if g["bezier"] is None and len(pts) == 2:
        conn = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Emu(ctx.emu(pts[0][0])), Emu(ctx.emu(pts[0][1])), Emu(ctx.emu(pts[1][0])), Emu(ctx.emu(pts[1][1])))
    elif g["bezier"] is None and len(pts) in (3, 4):
        kind = "bent2" if len(pts) == 3 else "bent3"
        place = _fit_connector(pts, kind)
        if place:
            conn = shapes.add_connector(MSO_CONNECTOR.ELBOW, Emu(0), Emu(0), Emu(10), Emu(10))
            _place_connector(ctx, conn, "bentConnector2" if kind == "bent2" else "bentConnector3", place)
    elif g["bezier"] is not None and side_a and side_b:
        fit = _fit_curve(pts[0], pts[-1], _SIDE_NORMAL[side_a], _SIDE_NORMAL[side_b])
        if fit:
            conn = shapes.add_connector(MSO_CONNECTOR.CURVE, Emu(0), Emu(0), Emu(10), Emu(10))
            _place_connector(ctx, conn, fit[0], fit[1])

    if conn is not None:
        _strip_style(conn)
        _glue(ctx, conn, edge.get("from"), pts[0], side_a, nodes, True)
        _glue(ctx, conn, edge.get("to"), pts[-1], side_b, nodes, False)
        line_shape = conn
    else:
        # A route no connector preset can draw (a loop back to the same side, say): exact geometry, not glued.
        if g["bezier"] is not None:
            b = [(float(x), float(y)) for x, y in g["bezier"]]
            b[0], b[3] = pts[0], pts[-1]
            segs: list[tuple] = [("M", *b[0]), ("C", *b[1], *b[2], *b[3])]
        else:
            segs = [("M", *pts[0])] + [("L", *p) for p in pts[1:]]
        line_shape = _freeform(ctx, shapes, segs, filled=False)
        line_shape.fill.background()
        ctx.note("a connector with an unusual route was drawn as a free line: it keeps its shape but does not follow when a box is moved")
    _line(ctx, line_shape, g["color"], g["width"], g["dash"])
    _line_ends(line_shape, head_end, tail_end)
    line_shape.name = f"connector {edge['id']}"[:60]

    if head == "inhibit":
        for hd in g["heads"]:
            if hd["kind"] == "inhibit":
                (ax, ay), (bx, by) = hd["points"]
                bar = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Emu(ctx.emu(ax)), Emu(ctx.emu(ay)), Emu(ctx.emu(bx)), Emu(ctx.emu(by)))
                _strip_style(bar)
                _line(ctx, bar, g["color"], g["width"] * 1.4)
                bar.name = "inhibition bar"
        ctx.note("PowerPoint has no T-bar line ending: inhibition bars are separate short lines next to their connector")

    label = edge.get("label")
    if label:
        fs = float(edge.get("fontSize") or ctx.style.get("fontSize", 16) * 0.82)
        lines = wrap_text(str(label), 220, fs)
        lh = fs * LINE_HEIGHT
        tw = max(text_width(line, fs) for line in lines)
        total = len(lines) * lh
        lx, ly = g["label"]
        box = shapes.add_textbox(Emu(ctx.emu(lx - tw / 2 - 8)), Emu(ctx.emu(ly - total / 2 - 1)), Emu(max(1, ctx.emu(tw + 16))), Emu(max(1, ctx.emu(total + 2))))
        bg = ctx.scene.get("background") or "#ffffff"
        _fill(box, "#ffffff" if bg == "none" else bg, 0.92)
        _write_text(ctx, box, str(label), fs, ctx.style.get("textColor", "#1f2a44"), False, False, "center", "middle", (0, 0, 0, 0), wrap=len(lines) > 1)
        box.name = "connector label"


def pptx_font(style: dict) -> str:
    """The Latin typeface to name in the file: the first family of the scene's stack if PowerPoint is likely to have it."""
    family = str(style.get("fontFamily") or "").split(",")[0].strip().strip("'\"")
    return family if family and family.lower() not in ("inter", "sans-serif", "system-ui") else "Arial"


def scene_to_pptx(scene: dict, include_notes: bool = False, disclosure: str = "") -> tuple[bytes, list[str]]:
    """Build a one-slide presentation. Returns ``(file bytes, notes about anything not exported natively)``."""
    from pptx import Presentation
    from pptx.util import Emu

    w, h = float(scene.get("width", 1200)), float(scene.get("height", 800))
    k = EMU_PX * min(1.0, MAX_SLIDE_PX / max(w, h))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(int(round(w * k))), Emu(int(round(h * k)))
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = _Ctx(scene, slide, k, pptx_font(scene.get("style") or {}))
    bg = _rgb(scene.get("background"))
    if bg is not None and str(scene.get("background")).lower() != "#ffffff":
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = bg
    nodes = {n["id"]: n for n in scene.get("nodes", [])}
    for node in scene.get("nodes", []):
        _node(ctx, node, include_notes)
    for edge in scene.get("edges", []):
        _edge(ctx, edge, nodes)
    if k < EMU_PX:
        ctx.note("the figure was scaled down to fit PowerPoint's maximum slide size")

    lines = [str(scene.get("title") or "").strip()]
    comments = [n for n in scene.get("nodes", []) if n.get("type") == "note" and n.get("text")]
    if comments:
        lines.append("Comments:")
        lines += [f"- {(n.get('author') + ': ') if n.get('author') else ''}{n['text']}" for n in comments]
    if disclosure:
        lines.append(disclosure)
    text = "\n".join(line for line in lines if line)
    if text:
        slide.notes_slide.notes_text_frame.text = text
    prs.core_properties.title = str(scene.get("title") or "Figure")[:200]
    prs.core_properties.author = ""
    prs.core_properties.comments = "Made with Figwright"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue(), ctx.notes


# ------------------------------------------------------------------------------ charts
def _err_bars_xml(plus: list[float], color: str) -> str:
    from pptx.oxml.ns import nsdecls

    pts = "".join(f'<c:pt idx="{i}"><c:v>{v:.6g}</c:v></c:pt>' for i, v in enumerate(plus))
    lit = f'<c:numLit><c:formatCode>General</c:formatCode><c:ptCount val="{len(plus)}"/>{pts}</c:numLit>'
    return (
        f'<c:errBars {nsdecls("c", "a")}><c:errDir val="y"/><c:errBarType val="both"/><c:errValType val="cust"/><c:noEndCap val="0"/>'
        f"<c:plus>{lit}</c:plus><c:minus>{lit}</c:minus>"
        f'<c:spPr><a:ln w="9525"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln></c:spPr></c:errBars>'
    )


def _before_data(ser_el, xml: str) -> None:
    """Insert a series child where the schema wants it: right before the category / x values."""
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import qn

    for tag in ("c:cat", "c:xVal", "c:val", "c:yVal"):
        anchor = ser_el.find(qn(tag))
        if anchor is not None:
            anchor.addprevious(parse_xml(xml))
            return


def _axis_look(axis, title: str, ink, size: int, log: bool = False) -> None:
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls, qn
    from pptx.util import Pt

    axis.has_major_gridlines = False
    axis.has_minor_gridlines = False
    axis.format.line.color.rgb = ink
    axis.format.line.width = Pt(0.75)
    axis.tick_labels.font.size = Pt(size)
    axis.tick_labels.font.color.rgb = ink
    if title:
        axis.has_title = True
        tf = axis.axis_title.text_frame
        tf.text = title
        run = tf.paragraphs[0].runs[0]
        run.font.size, run.font.bold, run.font.color.rgb = Pt(size + 1), False, ink
    if log:
        scaling = axis._element.find(qn("c:scaling"))
        if scaling is not None and scaling.find(qn("c:logBase")) is None:
            scaling.insert(0, parse_xml(f'<c:logBase {nsdecls("c")} val="10"/>'))


def plot_to_pptx(df, spec: dict, theme: str | None = None, caption: str = "", disclosure: str = "") -> tuple[bytes, list[str]]:
    """One slide with the chart. Returns ``(file bytes, notes)``.

    Bar, line, scatter and pie charts become native PowerPoint charts: the
    numbers sit in the embedded workbook and can be edited there, and error
    bars are real error bars. Other kinds have no native equivalent and are
    placed as a 300 dpi picture, which the notes say.
    """
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData, XyChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
    from pptx.util import Emu, Inches, Pt

    from .plot import chart_data, render_plot
    from .themes import get_theme

    data = chart_data(df, spec, theme)
    notes: list[str] = []
    t = get_theme(theme)
    ink = RGBColor.from_string(t["ink"].lstrip("#").upper())
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title = ""

    def rgb(c: str):
        return RGBColor.from_string(c.lstrip("#").upper()[:6])

    if data is None:
        png, info = render_plot(df, spec, theme, "png", dpi=300)
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            iw, ih = im.size
        scale = min(Inches(12.3) / iw, Inches(6.9) / ih)
        w, h = int(iw * scale), int(ih * scale)
        slide.shapes.add_picture(io.BytesIO(png), int((prs.slide_width - w) / 2), int((prs.slide_height - h) / 2), Emu(w), Emu(h))
        title = info["spec"]["title"]
        notes.append(f"a {info['spec']['kind']} chart has no native PowerPoint equivalent: it was placed as a 300 dpi picture (use the SVG export for an editable vector)")
    else:
        kind = data["kind"]
        title = data["title"]
        sp = data["spec"]
        ratio = sp["width"] / sp["height"]
        ch = min(Inches(6.7), Inches(12.2) / ratio)
        cw = int(ch * ratio)
        left, top = int((prs.slide_width - cw) / 2), int((prs.slide_height - ch) / 2)
        series = data["series"]
        colors = data["colors"]
        xy = kind == "scatter" or (kind == "line" and data["numeric_x"])
        if xy:
            cd: Any = XyChartData()
            for row in series:
                s = cd.add_series(row["name"])
                for xv, yv in zip(row["x"], row["values"]):
                    if yv is not None:
                        s.add_data_point(xv, yv)
            ctype = XL_CHART_TYPE.XY_SCATTER if kind == "scatter" else XL_CHART_TYPE.XY_SCATTER_LINES
        else:
            cd = CategoryChartData()
            cd.categories = data["categories"]
            for row in series:
                cd.add_series(row["name"], row["values"])
            ctype = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.DOUGHNUT}[kind]
        chart = slide.shapes.add_chart(ctype, left, top, cw, int(ch), cd).chart
        chart.font.size = Pt(12)
        chart.font.name = "Arial"
        chart.font.color.rgb = ink
        chart.has_title = bool(title)
        if title:
            chart.chart_title.text_frame.text = title
            run = chart.chart_title.text_frame.paragraphs[0].runs[0]
            run.font.size, run.font.bold, run.font.color.rgb = Pt(16), True, ink
        chart.has_legend = kind == "pie" or len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.RIGHT
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(11)
        plot = chart.plots[0]
        if kind == "pie":
            plot.vary_by_categories = True
            plot.has_data_labels = True
            labels = plot.data_labels
            labels.show_percentage, labels.show_value, labels.show_category_name = True, False, False
            labels.number_format, labels.number_format_is_linked = "0.0%", False
            labels.font.size = Pt(11)
            for i in range(len(data["categories"])):
                pt = plot.series[0].points[i]
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = rgb(colors[i % len(colors)])
                pt.format.line.color.rgb = RGBColor(255, 255, 255)
        else:
            _axis_look(chart.category_axis, data["xlabel"], ink, 11, log=xy and data["logx"])
            _axis_look(chart.value_axis, data["ylabel"], ink, 11, log=data["logy"])
            if kind == "bar":
                plot.gap_width = 55
                plot.overlap = -8 if len(series) > 1 else 0
                plot.vary_by_categories = False
            for i, ser in enumerate(plot.series):
                color = rgb(colors[i % len(colors)])
                row = series[i]
                if kind == "bar":
                    ser.format.fill.solid()
                    ser.format.fill.fore_color.rgb = color
                    ser.format.line.color.rgb = ink
                    ser.format.line.width = Pt(0.75)
                    if data["vary"]:
                        for j, v in enumerate(row["values"]):
                            if v is None:
                                continue
                            pt = ser.points[j]
                            pt.format.fill.solid()
                            pt.format.fill.fore_color.rgb = rgb(colors[j % len(colors)])
                            pt.format.line.color.rgb = ink
                            pt.format.line.width = Pt(0.75)
                else:
                    if kind == "scatter":
                        ser.format.line.fill.background()
                    else:
                        ser.format.line.color.rgb = color
                        ser.format.line.width = Pt(1.75)
                        ser.smooth = False
                    ser.marker.style = XL_MARKER_STYLE.CIRCLE
                    ser.marker.size = 6
                    ser.marker.format.fill.solid()
                    ser.marker.format.fill.fore_color.rgb = color
                    ser.marker.format.line.color.rgb = RGBColor(255, 255, 255) if kind == "scatter" else color
                errs = row.get("errors")
                if errs and any(e > 0 for e in errs):
                    kept = [e for e, v in zip(errs, row["values"]) if v is not None] if xy else list(errs)
                    _before_data(ser._element, _err_bars_xml(kept, t["ink"].lstrip("#").upper()))
                if kind == "scatter" and data.get("fit"):
                    from pptx.oxml.ns import nsdecls

                    _before_data(
                        ser._element,
                        f'<c:trendline {nsdecls("c", "a")}><c:spPr><a:ln w="15875"><a:solidFill><a:srgbClr val="{t["ink"].lstrip("#").upper()}"/></a:solidFill>'
                        '<a:prstDash val="dash"/></a:ln></c:spPr><c:trendlineType val="linear"/><c:dispRSqr val="0"/><c:dispEq val="0"/></c:trendline>',
                    )
            if kind == "scatter" and sp["fit"] and not data.get("fit"):
                notes.append("the fit line was left out of the native chart (it spans several groups or a log axis); add a trendline in PowerPoint or use the picture export")
            if data.get("error"):
                label = {"sd": "SD", "sem": "SEM", "ci95": "95% CI"}[data["error"]]
                notes.append(f"error bars are native custom error bars holding the {label} values: edit them under Error Bars > Custom if you change the data")
            if sp["stats"]:
                notes.append("significance brackets are not part of a native chart; they are in the SVG / PNG export and the statistics are in the caption")
            if sp["points"] and kind == "bar":
                notes.append("individual data points are shown in the SVG / PNG export only; the native chart holds the group means")

    text = "\n".join(x for x in (title, caption, disclosure) if x)
    if text:
        slide.notes_slide.notes_text_frame.text = text
    prs.core_properties.title = str(title or "Chart")[:200]
    prs.core_properties.author = ""
    prs.core_properties.comments = "Made with Figwright"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue(), notes
