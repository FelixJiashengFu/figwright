"""Sketch analysis with classical computer vision.

Finds the closed shapes in a photo or scan of a hand-drawn diagram and the
strokes that connect them. The result is used two ways: as a positional hint
for a vision model (which also reads the handwriting), and, with no model at
all, as a clean but unlabelled figure.
"""

from __future__ import annotations

import math
from typing import Any

from .builders.common import Canvas

MAX_SIDE = 1400


class SketchError(ValueError):
    """The upload could not be read as an image."""


def load_gray(data: bytes, max_side: int = MAX_SIDE):
    import cv2
    import numpy as np

    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise SketchError("The file is not an image this tool can read (use PNG, JPEG or WebP).")
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _classify(cnt, w: float, h: float) -> str:
    import cv2

    area = cv2.contourArea(cnt)
    extent = area / max(1.0, w * h)
    approx = cv2.approxPolyDP(cnt, 0.035 * cv2.arcLength(cnt, True), True)
    n = len(approx)
    if n == 3 and extent < 0.68:
        return "triangle"
    if n == 4 and extent < 0.66:
        # A diamond's corners sit near the middles of its bounding-box sides.
        x0, y0 = cnt[:, 0, 0].min(), cnt[:, 0, 1].min()
        near_mid = 0
        for p in approx[:, 0, :]:
            fx, fy = (p[0] - x0) / max(1.0, w), (p[1] - y0) / max(1.0, h)
            if min(abs(fx - 0.5), abs(fy - 0.5)) < 0.2:
                near_mid += 1
        return "diamond" if near_mid >= 3 else "parallelogram"
    if extent >= 0.87:
        return "rect"
    if extent >= 0.68 and n >= 6:
        return "ellipse"
    return "rect"


def detect(data: bytes) -> dict[str, Any]:
    """Return ``{"width", "height", "shapes": [...], "links": [...]}`` for a sketch image."""
    import cv2
    import numpy as np

    gray = load_gray(data)
    H, W = gray.shape[:2]
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    ink = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 14)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)), iterations=1)

    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    vals = dist[ink > 0]
    stroke = float(max(2.0, min(14.0, 4.0 * float(np.median(vals)) if vals.size else 3.0)))

    contours, hierarchy = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    shapes: list[dict[str, Any]] = []
    min_area = max(900.0, W * H * 0.0012)
    if hierarchy is not None:
        for i, cnt in enumerate(contours):
            if hierarchy[0][i][3] < 0:
                continue  # an outer boundary; shapes are the *holes* enclosed by a drawn outline
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if w < 24 or h < 18 or w > W * 0.985 and h > H * 0.985:
                continue
            pad = stroke / 2.0
            shapes.append({"type": _classify(cnt, w, h), "x": round(x - pad, 1), "y": round(y - pad, 1), "w": round(w + 2 * pad, 1), "h": round(h + 2 * pad, 1), "_area": area})
    shapes.sort(key=lambda s: (-s["_area"]))

    # A shape that encloses others is a container (frame), not a node.
    for a in shapes:
        inside = sum(1 for b in shapes if b is not a and b["x"] >= a["x"] and b["y"] >= a["y"] and b["x"] + b["w"] <= a["x"] + a["w"] and b["y"] + b["h"] <= a["y"] + a["h"])
        if inside:
            a["type"] = "frame"

    # ---- connectors: what is left after the shapes are erased ---------------------
    rest = ink.copy()
    grow = int(round(stroke * 0.5)) + 2  # just past the outline, so arrowheads next to a shape survive
    for s in shapes:
        x0, y0, x1, y1 = int(s["x"]), int(s["y"]), int(s["x"] + s["w"]), int(s["y"] + s["h"])
        if s["type"] == "frame":
            cv2.rectangle(rest, (x0, y0), (x1, y1), 0, thickness=2 * grow)
        else:
            cv2.rectangle(rest, (x0 - grow, y0 - grow), (x1 + grow, y1 + grow), 0, thickness=-1)
    n_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(rest, connectivity=8)
    nodes = [s for s in shapes if s["type"] != "frame"]
    reach = max(34.0, 0.05 * math.hypot(W, H)) + grow

    def gap(pt: tuple[float, float], s: dict) -> float:
        dx = max(s["x"] - pt[0], 0.0, pt[0] - (s["x"] + s["w"]))
        dy = max(s["y"] - pt[1], 0.0, pt[1] - (s["y"] + s["h"]))
        return math.hypot(dx, dy)

    links: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for lab in range(1, n_labels):
        x, y, w, h, area = (int(v) for v in stats[lab])
        if math.hypot(w, h) < max(36.0, 6 * stroke):
            continue
        ys, xs = np.nonzero(labels[y : y + h, x : x + w] == lab)
        pts = np.stack([xs + x, ys + y], axis=1).astype(np.float32)
        hull = cv2.convexHull(pts)[:, 0, :]
        best, p, q = 0.0, None, None
        for i in range(len(hull)):
            d = np.hypot(hull[:, 0] - hull[i, 0], hull[:, 1] - hull[i, 1])
            j = int(d.argmax())
            if d[j] > best:
                best, p, q = float(d[j]), hull[i], hull[j]
        if p is None or best < max(36.0, 6 * stroke):
            continue
        if area > best * stroke * 3.2:
            continue  # too much ink for a line of this length: handwriting or a scribble
        ends = []
        for pt in (p, q):
            ranked = sorted(((gap((float(pt[0]), float(pt[1])), s), k) for k, s in enumerate(nodes)), key=lambda t: t[0])
            ends.append(ranked[0] if ranked and ranked[0][0] <= reach else None)
        if not ends[0] or not ends[1] or ends[0][1] == ends[1][1]:
            continue
        a, b = ends[0][1], ends[1][1]
        # The arrowhead end carries more ink than the plain end.
        r = stroke * 4.0
        mass = [float(((pts[:, 0] - pt[0]) ** 2 + (pts[:, 1] - pt[1]) ** 2 <= r * r).sum()) for pt in (p, q)]
        arrow = True
        if mass[0] > mass[1] * 1.3:
            a, b = b, a  # the head is at p, so the link runs q -> p
        elif mass[1] > mass[0] * 1.3:
            pass
        else:
            arrow = False
            sa, sb = nodes[a], nodes[b]
            dx = (sb["x"] + sb["w"] / 2) - (sa["x"] + sa["w"] / 2)
            dy = (sb["y"] + sb["h"] / 2) - (sa["y"] + sa["h"] / 2)
            if (dy if abs(dy) >= 0.4 * abs(dx) else dx) < 0:
                a, b = b, a  # no clear head: assume reading order (downwards first, else rightwards)
        if (a, b) in seen or (b, a) in seen:
            continue
        seen.add((a, b))
        links.append({"from": a, "to": b, "arrow": arrow})

    for s in shapes:
        s.pop("_area", None)
    ordered = nodes + [s for s in shapes if s["type"] == "frame"]
    return {"width": W, "height": H, "shapes": ordered, "links": links, "stroke": round(stroke, 1)}


def hints_to_scene(hints: dict, theme: str | None = None) -> dict:
    """A tidy, unlabelled figure straight from the detected geometry."""
    c = Canvas(theme, "illustration", "")
    scale = min(1.0, 1200.0 / max(1.0, hints["width"]))
    ids: list[str | None] = []
    frames = [s for s in hints["shapes"] if s["type"] == "frame"]
    nodes = [s for s in hints["shapes"] if s["type"] != "frame"]
    for s in frames:
        c.add("frame", s["x"] * scale, s["y"] * scale, s["w"] * scale, s["h"] * scale)
    for i, s in enumerate(nodes):
        ids.append(c.add(s["type"], s["x"] * scale, s["y"] * scale, s["w"] * scale, s["h"] * scale, fill=c.soft(i), stroke=c.strong(i)))
    for link in hints["links"]:
        if link["from"] < len(ids) and link["to"] < len(ids):
            # Unclear heads are drawn as arrows in reading order: in a sketch a missed arrow is the worse mistake.
            c.edge(ids[link["from"]], ids[link["to"]], head="arrow")
    return c.finish(hints["width"] * scale, hints["height"] * scale)


def hints_text(hints: dict) -> str:
    """Compact description of the detected geometry for the vision model."""
    lines = [f"Image size {hints['width']} x {hints['height']} px. Detected closed shapes (index: type x y w h):"]
    nodes = [s for s in hints["shapes"] if s["type"] != "frame"]
    for i, s in enumerate(nodes):
        lines.append(f"  {i}: {s['type']} {s['x']:.0f} {s['y']:.0f} {s['w']:.0f} {s['h']:.0f}")
    for s in hints["shapes"]:
        if s["type"] == "frame":
            lines.append(f"  container: {s['x']:.0f} {s['y']:.0f} {s['w']:.0f} {s['h']:.0f}")
    if hints["links"]:
        lines.append("Detected connectors (from index -> to index): " + ", ".join(f"{k['from']}->{k['to']}" for k in hints["links"]))
    return "\n".join(lines)
