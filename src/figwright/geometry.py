"""Connector geometry: where edges attach to nodes, how they bend, arrowheads.

Mirrored by ``edgeGeometry`` in ``web/scene.js``; keep the two in sync.
"""

from __future__ import annotations

import math
from typing import Any

Point = tuple[float, float]

GAP = 3.0
STUB = 18.0
_NORMALS = {"top": (0.0, -1.0), "right": (1.0, 0.0), "bottom": (0.0, 1.0), "left": (-1.0, 0.0)}
_OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


def center(node: dict) -> Point:
    return node["x"] + node["w"] / 2.0, node["y"] + node["h"] / 2.0


def visual_box(node: dict) -> tuple[float, float, float, float]:
    """Axis-aligned bounds ``(x0, y0, x1, y1)`` of a node, taking its rotation into account."""
    x, y, w, h = float(node["x"]), float(node["y"]), float(node["w"]), float(node["h"])
    rot = float(node.get("rotation") or 0.0)
    if not rot:
        return x, y, x + w, y + h
    a = math.radians(rot)
    ca, sa = abs(math.cos(a)), abs(math.sin(a))
    bw, bh = w * ca + h * sa, w * sa + h * ca
    cx, cy = x + w / 2.0, y + h / 2.0
    return cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0


def shape_points(node: dict) -> list[Point] | None:
    """Polygon outline for the polygonal shape types (shared with the renderer and the PPTX exporter)."""
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    t = node.get("type")
    cx, cy = x + w / 2, y + h / 2
    if t == "diamond":
        return [(cx, y), (x + w, cy), (cx, y + h), (x, cy)]
    if t == "hexagon":
        i = min(w * 0.25, h * 0.5)
        return [(x + i, y), (x + w - i, y), (x + w, cy), (x + w - i, y + h), (x + i, y + h), (x, cy)]
    if t == "parallelogram":
        s = min(w * 0.2, h * 0.5)
        return [(x + s, y), (x + w, y), (x + w - s, y + h), (x, y + h)]
    if t == "triangle":
        return [(cx, y), (x + w, y + h), (x, y + h)]
    return None


def side_inset(node: dict) -> float:
    """How far the left / right outline sits inside the box at mid-height (slanted shapes)."""
    kind = node.get("type")
    if kind == "triangle":
        return node["w"] / 4.0
    if kind == "parallelogram":
        return min(node["w"] * 0.2, node["h"] * 0.5) / 2.0
    return 0.0


def side_anchor(node: dict, side: str, gap: float = GAP) -> Point:
    cx, cy = center(node)
    if side == "top":
        return cx, node["y"] - gap
    if side == "bottom":
        return cx, node["y"] + node["h"] + gap
    inset = side_inset(node)
    if side == "left":
        return node["x"] + inset - gap, cy
    return node["x"] + node["w"] - inset + gap, cy


def boundary_point(node: dict, toward: Point, gap: float = GAP) -> Point:
    """Point where the ray from the node centre towards ``toward`` leaves the shape."""
    cx, cy = center(node)
    dx, dy = toward[0] - cx, toward[1] - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return cx, cy
    hw, hh = max(node["w"] / 2.0, 0.5), max(node["h"] / 2.0, 0.5)
    kind = node.get("type")
    poly = shape_points(node) if kind in ("hexagon", "parallelogram", "triangle") else None
    if kind == "ellipse":
        t = 1.0 / math.sqrt((dx / hw) ** 2 + (dy / hh) ** 2)
    elif kind == "diamond":
        t = 1.0 / (abs(dx) / hw + abs(dy) / hh)
    elif poly:
        # Slanted outlines: cut the ray at the real edge, not at the bounding box.
        t = 0.0
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                continue
            tt = ((a[0] - cx) * ey - (a[1] - cy) * ex) / den
            uu = ((a[0] - cx) * dy - (a[1] - cy) * dx) / den
            if tt > 0 and -1e-6 <= uu <= 1 + 1e-6:
                t = max(t, tt)
        if t <= 0:
            t = min(hw / abs(dx) if abs(dx) > 1e-9 else float("inf"), hh / abs(dy) if abs(dy) > 1e-9 else float("inf"))
    else:
        tx = hw / abs(dx) if abs(dx) > 1e-9 else float("inf")
        ty = hh / abs(dy) if abs(dy) > 1e-9 else float("inf")
        t = min(tx, ty)
    ux, uy = dx / dist, dy / dist
    return cx + dx * t + ux * gap, cy + dy * t + uy * gap


def auto_sides(a: Point, b: Point) -> tuple[str, str]:
    """Pick facing sides for a connector running from centre ``a`` to centre ``b``."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def _resolve(end: Any, nodes: dict[str, dict]) -> tuple[dict | None, Point | None]:
    if isinstance(end, str):
        n = nodes.get(end)
        if n is None or n.get("hidden"):
            return None, None
        return n, center(n)
    if isinstance(end, (list, tuple)) and len(end) == 2:
        return None, (float(end[0]), float(end[1]))
    return None, None


def _anchor(node: dict | None, point: Point, side: str, gap: float) -> Point:
    return side_anchor(node, side, gap) if node is not None else point


def _elbow_simple(p0: Point, p3: Point, sa: str, sb: str) -> list[Point]:
    ha, hb = sa in ("left", "right"), sb in ("left", "right")
    if ha and hb:
        if sa == sb:
            out = (max(p0[0], p3[0]) + 28) if sa == "right" else (min(p0[0], p3[0]) - 28)
            return [p0, (out, p0[1]), (out, p3[1]), p3]
        if abs(p0[1] - p3[1]) < 0.5:
            return [p0, p3]
        mx = (p0[0] + p3[0]) / 2.0
        return [p0, (mx, p0[1]), (mx, p3[1]), p3]
    if not ha and not hb:
        if sa == sb:
            out = (max(p0[1], p3[1]) + 28) if sa == "bottom" else (min(p0[1], p3[1]) - 28)
            return [p0, (p0[0], out), (p3[0], out), p3]
        if abs(p0[0] - p3[0]) < 0.5:
            return [p0, p3]
        my = (p0[1] + p3[1]) / 2.0
        return [p0, (p0[0], my), (p3[0], my), p3]
    if ha:
        return [p0, (p3[0], p0[1]), p3]
    return [p0, (p0[0], p3[1]), p3]


def _step(a: Point, b: Point) -> tuple[int, int]:
    """Axis direction of a segment; ``(2, 2)`` for a diagonal, ``(0, 0)`` for a point."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return 0, 0
    if abs(dy) < 0.01:
        return (1 if dx > 0 else -1), 0
    if abs(dx) < 0.01:
        return 0, (1 if dy > 0 else -1)
    return 2, 2


def _clean_route(points: list[Point]) -> list[Point] | None:
    """Drop repeated and collinear points. ``None`` if the route doubles back or runs diagonally."""
    out: list[Point] = [points[0]]
    last: tuple[int, int] | None = None
    for p in points[1:]:
        d = _step(out[-1], p)
        if d == (0, 0):
            continue
        if d == (2, 2):
            return None
        if last is not None:
            if d == last:
                out[-1] = p
                continue
            if d == (-last[0], -last[1]):
                return None
        out.append(p)
        last = d
    return out if len(out) >= 2 else None


def _crosses(a: Point, b: Point, box: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1
    return max(a[0], b[0]) > x0 and min(a[0], b[0]) < x1 and max(a[1], b[1]) > y0 and min(a[1], b[1]) < y1


def _route_around(p0: Point, p3: Point, sa: str, sb: str, boxes: list[tuple[float, float, float, float]]) -> list[Point] | None:
    """Orthogonal route for the awkward cases: leave along the side's normal, arrive against it."""
    na, nb = _NORMALS[sa], _NORMALS[sb]
    s = (p0[0] + na[0] * STUB, p0[1] + na[1] * STUB)
    e = (p3[0] + nb[0] * STUB, p3[1] + nb[1] * STUB)
    xs = [p0[0], p3[0], s[0], e[0]] + [v for b in boxes for v in (b[0], b[2])]
    ys = [p0[1], p3[1], s[1], e[1]] + [v for b in boxes for v in (b[1], b[3])]
    lo_x, hi_x, lo_y, hi_y = min(xs) - STUB, max(xs) + STUB, min(ys) - STUB, max(ys) + STUB
    mx, my = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0
    options: list[list[Point]] = [
        [],
        [(e[0], s[1])],
        [(s[0], e[1])],
        [(mx, s[1]), (mx, e[1])],
        [(s[0], my), (e[0], my)],
        [(s[0], lo_y), (e[0], lo_y)],
        [(s[0], hi_y), (e[0], hi_y)],
        [(lo_x, s[1]), (lo_x, e[1])],
        [(hi_x, s[1]), (hi_x, e[1])],
    ]
    best: list[Point] | None = None
    best_cost = float("inf")
    for mid in options:
        route = _clean_route([p0, s, *mid, e, p3])
        if route is None:
            continue
        cost = sum(math.dist(route[i], route[i + 1]) for i in range(len(route) - 1)) + 30.0 * (len(route) - 2)
        # The first and last runs are the stubs at the two shapes; only the middle may not cut through a box.
        for i in range(1, len(route) - 2):
            cost += sum(1000.0 for b in boxes if _crosses(route[i], route[i + 1], b))
        if cost < best_cost - 1e-6:
            best, best_cost = route, cost
    return best


def _elbow(p0: Point, p3: Point, sa: str, sb: str, boxes: list[tuple[float, float, float, float]] | None = None) -> list[Point]:
    simple = _elbow_simple(p0, p3, sa, sb)
    na, nb = _NORMALS[sa], _NORMALS[sb]
    first, last = _step(simple[0], simple[1]), _step(simple[-2], simple[-1])
    if first == (int(na[0]), int(na[1])) and last == (-int(nb[0]), -int(nb[1])) and _clean_route(simple) is not None:
        return simple
    # The plain bend would leave backwards or arrive from inside the shape.
    return _route_around(p0, p3, sa, sb, boxes or []) or simple


def _dedupe(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or math.dist(out[-1], p) > 0.01:
            out.append(p)
    return out


def bezier_point(p0: Point, c1: Point, c2: Point, p3: Point, t: float) -> Point:
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p3[1],
    )


def polyline_midpoint(points: list[Point]) -> Point:
    total = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    if total <= 0:
        return points[0]
    half = total / 2.0
    run = 0.0
    for i in range(len(points) - 1):
        seg = math.dist(points[i], points[i + 1])
        if run + seg >= half and seg > 0:
            t = (half - run) / seg
            return points[i][0] + (points[i + 1][0] - points[i][0]) * t, points[i][1] + (points[i + 1][1] - points[i][1]) * t
        run += seg
    return points[-1]


def _unit(a: Point, b: Point) -> Point:
    d = math.dist(a, b)
    if d < 1e-9:
        return 1.0, 0.0
    return (b[0] - a[0]) / d, (b[1] - a[1]) / d


def _head(kind: str, tip: Point, direction: Point, size: float) -> tuple[dict, float]:
    """Build one line ending. Returns (shape, how far to pull the line back)."""
    ux, uy = direction
    px, py = -uy, ux
    if kind == "inhibit":
        half = size * 0.62
        return {"kind": "inhibit", "points": [(tip[0] + px * half, tip[1] + py * half), (tip[0] - px * half, tip[1] - py * half)]}, 0.0
    if kind == "circle":
        r = size * 0.32
        return {"kind": "circle", "center": (tip[0] - ux * r, tip[1] - uy * r), "r": r}, 2 * r
    base = (tip[0] - ux * size, tip[1] - uy * size)
    half = size * 0.42
    return {"kind": "arrow", "points": [tip, (base[0] + px * half, base[1] + py * half), (base[0] - px * half, base[1] - py * half)]}, size * 0.85


def fmt(v: float) -> str:
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return "0" if s == "-0" else s


def edge_geometry(scene: dict, edge: dict, nodes: dict[str, dict] | None = None) -> dict | None:
    """Resolve an edge to drawable geometry, or ``None`` if it cannot be drawn."""
    if edge.get("hidden"):
        return None
    if nodes is None:
        nodes = {n["id"]: n for n in scene.get("nodes", [])}
    style = scene.get("style") or {}
    na, ca = _resolve(edge.get("from"), nodes)
    nb, cb = _resolve(edge.get("to"), nodes)
    if ca is None or cb is None:
        return None
    width = float(edge.get("width") or style.get("edgeWidth", 2))
    head = edge.get("head", "arrow")
    routing = edge.get("routing") or "straight"
    gap_end = GAP + (2.0 if head == "inhibit" else 0.0)
    gap_start = GAP

    bez = None
    if routing == "straight" and not edge.get("fromSide") and not edge.get("toSide"):
        p0 = boundary_point(na, cb, gap_start) if na is not None else ca
        p3 = boundary_point(nb, ca, gap_end) if nb is not None else cb
        pts = [p0, p3]
    else:
        sa_auto, sb_auto = auto_sides(ca, cb)
        sa = edge.get("fromSide") or sa_auto
        sb = edge.get("toSide") or sb_auto
        p0 = _anchor(na, ca, sa, gap_start)
        p3 = _anchor(nb, cb, sb, gap_end)
        if routing == "curve":
            span = math.dist(p0, p3)
            k = max(30.0, span * 0.4)
            if sa == sb:
                # A loop that leaves and re-enters on the same side: keep the bulge bounded.
                k = min(120.0, max(46.0, span * 0.6))
            n1, n2 = _NORMALS[sa], _NORMALS[sb]
            c1 = (p0[0] + n1[0] * k, p0[1] + n1[1] * k)
            c2 = (p3[0] + n2[0] * k, p3[1] + n2[1] * k)
            bez = [p0, c1, c2, p3]
            pts = [bezier_point(p0, c1, c2, p3, i / 20.0) for i in range(21)]
        elif routing == "elbow":
            pts = _elbow(p0, p3, sa, sb, [visual_box(n) for n in (na, nb) if n is not None])
        else:
            pts = [p0, p3]
    pts = _dedupe(pts)
    if len(pts) < 2:
        return None

    size = float(style.get("arrowSize", 9)) + width * 1.5
    heads: list[dict] = []
    label_pos = bezier_point(*bez, 0.5) if bez else polyline_midpoint(pts)
    raw_pts = list(pts)  # untrimmed: exporters with native arrowheads want the true endpoints
    pts = list(pts)

    def trim(points: list[Point], at_end: bool, amount: float) -> None:
        if amount <= 0:
            return
        i, j = (-1, -2) if at_end else (0, 1)
        seg = math.dist(points[i], points[j])
        amount = min(amount, seg * 0.9)
        ux, uy = _unit(points[j], points[i])
        points[i] = (points[i][0] - ux * amount, points[i][1] - uy * amount)

    if head in ("arrow", "inhibit", "circle", "both"):
        kind = "arrow" if head == "both" else head
        direction = _unit(bez[2], bez[3]) if bez and math.dist(bez[2], bez[3]) > 1e-6 else _unit(pts[-2], pts[-1])
        shape, pull = _head(kind, pts[-1], direction, size)
        heads.append(shape)
        if bez:
            ux, uy = direction
            pull = min(pull, math.dist(bez[2], bez[3]) * 0.9) if math.dist(bez[2], bez[3]) > 1e-6 else pull
            bez[3] = (bez[3][0] - ux * pull, bez[3][1] - uy * pull)
        trim(pts, True, pull)
    if head == "both":
        direction = _unit(bez[1], bez[0]) if bez and math.dist(bez[1], bez[0]) > 1e-6 else _unit(pts[1], pts[0])
        shape, pull = _head("arrow", pts[0], direction, size)
        heads.append(shape)
        if bez:
            ux, uy = direction
            bez[0] = (bez[0][0] - ux * pull, bez[0][1] - uy * pull)
        trim(pts, False, pull)

    if bez:
        d = "M{} {} C{} {} {} {} {} {}".format(*(fmt(v) for p in bez for v in p))
    else:
        d = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts)
    return {
        "path": d,
        "points": raw_pts,
        "bezier": bez,
        "heads": heads,
        "label": label_pos,
        "width": width,
        "color": edge.get("color") or style.get("edgeColor", "#3b4a66"),
        "dash": bool(edge.get("dash")),
        "size": size,
    }
