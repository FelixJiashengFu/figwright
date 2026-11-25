"""Geometric lint and automatic tidy-up for scenes.

Models are decent at deciding *what* goes into a figure and noticeably worse at
arithmetic, so every model-written scene passes through here: ``autofix``
repairs what can be repaired mechanically (text that does not fit, shapes off
the canvas, near-miss alignment) and ``lint`` reports what is left. The report
is also what the optional critic round sends back to the model.
"""

from __future__ import annotations

from copy import deepcopy

from .geometry import edge_geometry, visual_box
from .render import icon_layout, node_style, text_area
from .text import LINE_HEIGHT, text_width, wrap_text

_BACKDROP = ("frame", "bilayer", "image", "path", "note")


def _area(n: dict) -> float:
    return max(0.0, n["w"]) * max(0.0, n["h"])


def _intersection(a: dict, b: dict) -> float:
    ax0, ay0, ax1, ay1 = visual_box(a)
    bx0, by0, bx1, by1 = visual_box(b)
    w = min(ax1, bx1) - max(ax0, bx0)
    h = min(ay1, by1) - max(ay0, by0)
    return max(0.0, w) * max(0.0, h)


def _segment_hits_box(p: tuple[float, float], q: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    """Liang-Barsky clip test: does segment pq pass through the box?"""
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return False
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if abs(pp) < 1e-12:
            if qq < 0:
                return False
            continue
        r = qq / pp
        if pp < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t1 - t0 > 1e-6


def text_fit(node: dict, style: dict) -> tuple[float, float, float, float]:
    """(needed_w, needed_h, available_w, available_h) for a node's text."""
    ns = node_style(node, style)
    if node.get("type") == "icon":
        lay = icon_layout(node, style)
        lines = lay["lines"]
        need_w = max((text_width(line, ns["fs"], ns["bold"]) for line in lines), default=0.0)
        need_h = len(lines) * ns["fs"] * LINE_HEIGHT + (40 if lines else 0)
        return need_w, need_h, node["w"], node["h"]
    ax, ay, aw, ah, _a, _v = text_area(node, style)
    lines = wrap_text(node.get("text") or "", aw, ns["fs"], ns["bold"])
    need_w = max((text_width(line, ns["fs"], ns["bold"]) for line in lines), default=0.0)
    return need_w, len(lines) * ns["fs"] * LINE_HEIGHT, aw, ah


def lint(scene: dict) -> list[dict]:
    """Return a list of issues: ``{"code", "severity", "message", "ids"}``."""
    issues: list[dict] = []
    style = scene.get("style") or {}
    W, H = float(scene.get("width", 0)), float(scene.get("height", 0))
    nodes = [n for n in scene.get("nodes", []) if not n.get("hidden")]
    if not nodes:
        issues.append({"code": "empty", "severity": "error", "message": "The figure has no elements.", "ids": []})
        return issues

    for n in nodes:
        bx0, by0, bx1, by1 = visual_box(n)
        if bx0 < -2 or by0 < -2 or bx1 > W + 2 or by1 > H + 2:
            issues.append({"code": "off_canvas", "severity": "error", "message": f"'{n['id']}' extends outside the {W:g}x{H:g} canvas.", "ids": [n["id"]]})
        if n.get("text") and n.get("type") not in ("image", "path", "bilayer"):
            need_w, need_h, aw, ah = text_fit(n, style)
            if need_h > ah + 3 or need_w > aw + 3:
                issues.append({"code": "text_overflow", "severity": "error", "message": f"The text of '{n['id']}' does not fit its {n['w']:g}x{n['h']:g} box.", "ids": [n["id"]]})
            if node_style(n, style)["fs"] < 9:
                issues.append({"code": "tiny_text", "severity": "warning", "message": f"The text of '{n['id']}' is smaller than 9 px and will be unreadable in print.", "ids": [n["id"]]})

    solid = [n for n in nodes if n.get("type") not in _BACKDROP]
    for i, a in enumerate(solid):
        for b in solid[i + 1 :]:
            inter = _intersection(a, b)
            if inter <= 0:
                continue
            small = min(_area(a), _area(b)) or 1.0
            ratio = inter / small
            if ratio >= 0.9:
                continue  # one sits inside the other: a deliberate container / label
            if ratio > 0.2:
                issues.append({"code": "overlap", "severity": "error", "message": f"'{a['id']}' and '{b['id']}' overlap.", "ids": [a["id"], b["id"]]})

    by_id = {n["id"]: n for n in scene.get("nodes", [])}
    for e in scene.get("edges", []):
        g = edge_geometry(scene, e, by_id)
        if not g:
            continue
        ends = {x for x in (e.get("from"), e.get("to")) if isinstance(x, str)}
        pts = g["points"]
        for n in solid:
            if n["id"] in ends:
                continue
            # A container that holds an endpoint is allowed to be crossed.
            if any(_intersection(n, by_id[x]) >= 0.9 * _area(by_id[x]) for x in ends if x in by_id and _area(by_id[x]) > 0):
                continue
            vx0, vy0, vx1, vy1 = visual_box(n)
            box = (vx0 + 5, vy0 + 5, vx1 - 5, vy1 - 5)
            if any(_segment_hits_box(pts[k], pts[k + 1], box) for k in range(len(pts) - 1)):
                issues.append({"code": "edge_through_node", "severity": "warning", "message": f"Connector '{e['id']}' runs across '{n['id']}'.", "ids": [e["id"], n["id"]]})
                break
    return issues


def _cluster_snap(values: list[tuple[float, int]], tol: float) -> dict[int, float]:
    """Group near-equal values; returns index -> snapped value for groups of 2+."""
    out: dict[int, float] = {}
    values = sorted(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1][0] - values[i][0] <= tol:
            j += 1
        if j > i and values[j][0] - values[i][0] > 1e-9:
            mean = sum(v for v, _ in values[i : j + 1]) / (j - i + 1)
            for _v, idx in values[i : j + 1]:
                out[idx] = mean
        i = j + 1
    return out


def fit_text(scene: dict) -> int:
    """Shrink fonts a little, then grow boxes, until every label fits. Returns the number of nodes changed."""
    style = scene.get("style") or {}
    changed = 0
    for n in scene.get("nodes", []):
        t = n.get("type")
        if not n.get("text") or t in ("image", "path", "bilayer", "frame"):
            continue
        ns = node_style(n, style)
        if t == "text":
            lines = wrap_text(n["text"], n["w"], ns["fs"], ns["bold"])
            need_h = len(lines) * ns["fs"] * LINE_HEIGHT
            need_w = max((text_width(line, ns["fs"], ns["bold"]) for line in lines), default=0.0)
            if need_h > n["h"] + 1 or need_w > n["w"] + 1:
                cy = n["y"] + n["h"] / 2
                cx = n["x"] + n["w"] / 2
                if need_w > n["w"] + 1:
                    n["w"] = round(need_w + 6, 1)
                    n["x"] = round(cx - n["w"] / 2, 1)
                if need_h > n["h"] + 1:
                    n["h"] = round(need_h + 2, 1)
                    n["y"] = round(cy - n["h"] / 2, 1)
                changed += 1
            continue
        need_w, need_h, aw, ah = text_fit(n, style)
        if need_h <= ah + 1 and need_w <= aw + 1:
            continue
        changed += 1
        fs = ns["fs"]
        floor = max(11.0, fs * 0.78)
        while fs > floor:
            fs = max(floor, fs - 1)
            n["fontSize"] = fs
            need_w, need_h, aw, ah = text_fit(n, style)
            if need_h <= ah + 1 and need_w <= aw + 1:
                break
        need_w, need_h, aw, ah = text_fit(n, style)
        if need_w > aw + 1:
            grow = need_w - aw + 2
            n["x"] = round(n["x"] - grow / 2, 1)
            n["w"] = round(n["w"] + grow, 1)
            need_w, need_h, aw, ah = text_fit(n, style)
        if need_h > ah + 1:
            grow = need_h - ah + 2
            # Shapes whose text area is a fraction of the box need proportionally more room.
            factor = n["h"] / ah if ah > 0 else 1.0
            grow *= max(1.0, min(2.5, factor))
            n["y"] = round(n["y"] - grow / 2, 1)
            n["h"] = round(n["h"] + grow, 1)
    return changed


def fit_canvas(scene: dict, margin: float = 24.0) -> bool:
    """Shift / enlarge the canvas so that nothing is cut off."""
    nodes = [n for n in scene.get("nodes", []) if not n.get("hidden")]
    if not nodes:
        return False
    boxes = [visual_box(n) for n in nodes]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    for e in scene.get("edges", []):
        for end in (e.get("from"), e.get("to")):
            if isinstance(end, list):
                x0, y0, x1, y1 = min(x0, end[0]), min(y0, end[1]), max(x1, end[0]), max(y1, end[1])
    dx = margin - x0 if x0 < 0 else 0.0
    dy = margin - y0 if y0 < 0 else 0.0
    changed = False
    if dx or dy:
        for n in scene.get("nodes", []):
            n["x"] = round(n["x"] + dx, 1)
            n["y"] = round(n["y"] + dy, 1)
        for e in scene.get("edges", []):
            for key in ("from", "to"):
                if isinstance(e.get(key), list):
                    e[key] = [round(e[key][0] + dx, 1), round(e[key][1] + dy, 1)]
        x1 += dx
        y1 += dy
        changed = True
    if x1 > scene["width"]:
        scene["width"] = round(x1 + margin, 1)
        changed = True
    if y1 > scene["height"]:
        scene["height"] = round(y1 + margin, 1)
        changed = True
    return changed


def snap_alignment(scene: dict, tol: float = 7.0) -> int:
    """Snap almost-aligned centres onto a common line. Returns the number of moves."""
    nodes = [n for n in scene.get("nodes", []) if not n.get("hidden") and not n.get("locked") and n.get("type") not in ("frame", "bilayer", "image", "path", "note")]
    moved = 0
    for axis, size in (("x", "w"), ("y", "h")):
        snaps = _cluster_snap([(n[axis] + n[size] / 2.0, i) for i, n in enumerate(nodes)], tol)
        for i, c in snaps.items():
            new = round(c - nodes[i][size] / 2.0, 1)
            if abs(new - nodes[i][axis]) > 0.05:
                nodes[i][axis] = new
                moved += 1
    return moved


def autofix(scene: dict, snap: bool = True) -> tuple[dict, list[str]]:
    """Return a tidied copy of ``scene`` and a list of what was done."""
    out = deepcopy(scene)
    notes: list[str] = []
    n = fit_text(out)
    if n:
        notes.append(f"resized {n} label(s) so the text fits")
    if snap:
        m = snap_alignment(out)
        if m:
            notes.append(f"aligned {m} element(s)")
    if fit_canvas(out):
        notes.append("extended the canvas to include every element")
    return out, notes


def summarize(issues: list[dict], limit: int = 12) -> str:
    """Compact, model-readable issue list."""
    lines = [f"- [{i['severity']}] {i['message']}" for i in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"- ... and {len(issues) - limit} more")
    return "\n".join(lines)
