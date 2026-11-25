"""Bitmap to editable vector.

The image is reduced to a few flat colours and every colour becomes a filled
path. Layers are *stacked*: each layer also covers everything drawn after it,
so simplifying the outlines can never open gaps between neighbouring colours.

This suits line art, logos, diagrams and flat illustrations. Photographs and
micrographs turn into posterised blobs; that is a property of tracing, not a
bug to be tuned away, and the result says so when it detects such an image.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from .pathutil import transform_path
from .raster import ImageError, open_image

DETAIL = {"low": 2.0, "medium": 1.1, "high": 0.6}
MAX_COLORS = 16
MAX_SPLIT_NODES = 300


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(float(v))))) for v in rgb)


def _f(v: float) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _nearest(lab_pixels, centers):
    """Index of the nearest centre for every pixel, plus the distance to it."""
    import numpy as np

    out = np.empty(len(lab_pixels), dtype=np.int32)
    dist = np.empty(len(lab_pixels), dtype=np.float32)
    for start in range(0, len(lab_pixels), 400_000):
        part = lab_pixels[start : start + 400_000]
        d = ((part[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        near = d.argmin(axis=1)
        out[start : start + len(part)] = near
        dist[start : start + len(part)] = np.sqrt(d[np.arange(len(part)), near])
    return out, dist


def _fringe_colors(labels, centers, flat, radius: int) -> list[int]:
    """Clusters that are only the anti-aliased blend between two real colours.

    Such a cluster has no flat interior, its colour lies between the two
    colours, and its pixels sit where regions of both meet. A thin line of a
    genuinely different colour fails the last test and is kept.
    """
    import cv2
    import numpy as np

    k = len(centers)
    if k < 3:
        return []
    valid = labels >= 0
    counts = np.bincount(labels[valid], minlength=k)
    flat_counts = np.bincount(labels[valid & flat], minlength=k)
    real = {i for i in range(k) if counts[i] and flat_counts[i] / counts[i] >= 0.3}
    present = [i for i in range(k) if counts[i]]
    if not real or len(present) < 3:
        return []
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    near = {i: cv2.dilate((labels == i).astype(np.uint8), kernel) > 0 for i in present}
    drop: list[int] = []
    for c in present:
        if c in real:
            continue
        mask = labels == c
        for a, b in combinations([i for i in present if i != c], 2):
            if a not in real and b not in real:
                continue  # at least one side must be a real, flat colour (the background of a label, say)
            ab = centers[b] - centers[a]
            t = float(np.dot(centers[c] - centers[a], ab) / max(1e-6, float(np.dot(ab, ab))))
            if not 0.1 < t < 0.9:
                continue
            if float(np.linalg.norm(centers[c] - (centers[a] + t * ab))) > 11.0:
                continue
            if float((near[a][mask] & near[b][mask]).mean()) > 0.55:
                drop.append(c)
                break
    return drop


def quantize(rgb, opaque, k: int, fringe_radius: int = 2):
    """Cluster the opaque pixels into at most ``k`` colours. Returns ``(labels, palette_rgb, mean_error)``."""
    import cv2
    import numpy as np

    h, w = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    idx = np.flatnonzero(opaque.reshape(-1))
    if idx.size == 0:
        raise ImageError("The image is fully transparent: there is nothing to trace.")
    rng = np.random.default_rng(7)
    sample = lab[idx if idx.size <= 60_000 else rng.choice(idx, 60_000, replace=False)]
    distinct = np.unique(sample.astype(np.uint8), axis=0)
    k = max(1, min(k, len(distinct)))
    if k == 1:
        centers = sample.mean(axis=0, keepdims=True)
    else:
        cv2.setRNGSeed(7)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.4)
        _c, _l, centers = cv2.kmeans(sample, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    # Merge clusters that are visually the same colour.
    merged: list[Any] = []
    for c in centers:
        if all(float(np.abs(c - m).max()) > 7.0 for m in merged):
            merged.append(c)
    centers = np.asarray(merged, dtype=np.float32)

    labels = np.full(h * w, -1, dtype=np.int32)
    labels[idx], dist = _nearest(lab[idx], centers)
    labels = labels.reshape(h, w)
    grad = cv2.morphologyEx(rgb, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)).max(axis=2)
    drop = _fringe_colors(labels, centers, grad < 14, fringe_radius)
    if drop and len(centers) - len(drop) >= 2:
        centers = np.asarray([c for i, c in enumerate(centers) if i not in drop], dtype=np.float32)
        flat_labels = np.full(h * w, -1, dtype=np.int32)
        flat_labels[idx], dist = _nearest(lab[idx], centers)
        labels = flat_labels.reshape(h, w)
    palette = cv2.cvtColor(centers.reshape(1, -1, 3).clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return labels, palette, float(dist.mean())


def despeckle(labels, min_area: int):
    """Give regions smaller than ``min_area`` pixels to their nearest larger neighbour."""
    import cv2
    import numpy as np

    small = np.zeros(labels.shape, dtype=bool)
    for lab in range(int(labels.max()) + 1):
        _n, comp, stats, _cent = cv2.connectedComponentsWithStats((labels == lab).astype(np.uint8), connectivity=8)
        tiny = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] < min_area)
        tiny = tiny[tiny != 0]
        if tiny.size:
            small |= np.isin(comp, tiny)
    known = (~small) & (labels >= 0)
    if not small.any() or not known.any():
        return labels
    _dist, nearest = cv2.distanceTransformWithLabels((~known).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.zeros(int(nearest.max()) + 1, dtype=np.int32)
    lut[nearest[known]] = labels[known]
    out = labels.copy()
    fill = small & (labels >= 0)
    out[fill] = lut[nearest[fill]]
    return out


def _edge_lattice(mask):
    """Upsample a mask so that contour coordinates / 2 land exactly on pixel edges.

    ``findContours`` reports the centres of boundary pixels, which would shave
    half a pixel off every side (and erase one-pixel lines). On this lattice a
    source pixel ``x`` occupies indices ``2x .. 2x + 2``, so the traced outline
    runs along the true edge.
    """
    import numpy as np

    h, w = mask.shape
    out = np.zeros((2 * h + 1, 2 * w + 1), dtype=np.uint8)
    m = mask.astype(np.uint8)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out[dy : dy + 2 * h : 2, dx : dx + 2 * w : 2] |= m
    return out


def _signed_area(pts) -> float:
    import numpy as np

    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def polygon_path(pts, smooth: bool = True, eps: float = 1.1, corner_deg: float = 128.0, min_leg: float = 5.0) -> str:
    """Closed path through a polygon: straight runs and real corners are kept, the rest becomes cubic curves.

    * An edge much longer than a neighbour is a *straight run* (the side of a
      rounded box); curves join it tangentially.
    * A vertex is a *corner* when it is an acute turn next to a long edge (the
      end of a stroke), or when rounding it would move the outline by clearly
      more than the tracing tolerance ``eps`` (an octagon's corner). Vertices
      of a simplified arc qualify for neither, so circles come out round.
    * Everything else is an interpolating (Catmull-Rom style) cubic through
      the vertices, with tangents weighted by edge length.
    """
    import numpy as np

    n = len(pts)
    if n < 3:
        return ""
    if not smooth:
        return "M" + " L".join(f"{_f(x)} {_f(y)}" for x, y in pts) + " Z"
    nxt = np.roll(pts, -1, axis=0)
    edge = nxt - pts  # edge i runs from vertex i to vertex i + 1
    length = np.maximum(np.hypot(edge[:, 0], edge[:, 1]), 1e-9)
    unit = edge / length[:, None]
    len_in, len_out = np.roll(length, 1), length
    dir_in, dir_out = np.roll(unit, 1, axis=0), unit
    cos = np.clip((dir_in * dir_out).sum(axis=1), -1.0, 1.0)
    turn = np.arccos(cos)  # 0 = straight on
    corner = (np.degrees(np.pi - turn) < corner_deg) & (np.maximum(len_in, len_out) >= min_leg)
    corner |= np.minimum(len_in, len_out) * turn / 8.0 > 2.5 * eps
    straight = (length >= 3.0 * np.minimum(np.roll(length, 1), np.roll(length, -1))) & (length >= max(8.0, 6.0 * eps))
    straight |= corner & np.roll(corner, -1)
    straight_in = np.roll(straight, 1)

    blend = dir_in * len_out[:, None] + dir_out * len_in[:, None]
    norm = np.maximum(np.hypot(blend[:, 0], blend[:, 1]), 1e-9)
    tan_in = blend / norm[:, None]
    tan_out = tan_in.copy()
    for i in range(n):
        if corner[i] or (straight_in[i] and straight[i]):
            tan_in[i], tan_out[i] = dir_in[i], dir_out[i]
        elif straight_in[i]:
            tan_in[i] = tan_out[i] = dir_in[i]
        elif straight[i]:
            tan_in[i] = tan_out[i] = dir_out[i]

    d = [f"M{_f(pts[0][0])} {_f(pts[0][1])}"]
    for i in range(n):
        j = (i + 1) % n
        if straight[i]:
            if j != 0:
                d.append(f"L{_f(pts[j][0])} {_f(pts[j][1])}")
            continue
        c1 = pts[i] + tan_out[i] * (length[i] / 3.0)
        c2 = pts[j] - tan_in[j] * (length[i] / 3.0)
        d.append(f"C{_f(c1[0])} {_f(c1[1])} {_f(c2[0])} {_f(c2[1])} {_f(pts[j][0])} {_f(pts[j][1])}")
    return " ".join(d) + " Z"


def trace_mask(mask, eps: float, min_area: float, smooth: bool = True) -> list[dict]:
    """Outlines of a binary mask as ``[{"d", "box", "area", "points"}]``, one entry per island (holes included)."""
    import cv2
    import numpy as np

    contours, hierarchy = cv2.findContours(_edge_lattice(mask), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hier = hierarchy[0]
    out: list[dict] = []

    def poly(i: int):
        cnt = contours[i]
        # Thin strokes get a tolerance below their own thickness, or a hairline would collapse to nothing.
        thickness = 2.0 * cv2.contourArea(cnt) / max(1.0, cv2.arcLength(cnt, True))
        tol = min(2.0 * eps, 0.45 * thickness)
        approx = cv2.approxPolyDP(cnt, tol, True)
        if len(approx) < 3:
            approx = cnt
        if len(approx) < 3:
            return None, eps
        return approx[:, 0, :].astype(np.float64) / 2.0, tol / 2.0

    for i, h in enumerate(hier):
        if h[3] >= 0:
            continue  # a hole: handled with its parent
        area = cv2.contourArea(contours[i]) / 4.0
        if area < min_area:
            continue
        outer, tol = poly(i)
        if outer is None:
            continue
        if _signed_area(outer) < 0:
            outer = outer[::-1]
        parts = [polygon_path(outer, smooth, tol)]
        points = len(outer)
        child = h[2]
        while child >= 0:
            if cv2.contourArea(contours[child]) / 4.0 >= min_area:
                hole, tol = poly(child)
                if hole is not None:
                    if _signed_area(hole) > 0:
                        hole = hole[::-1]  # opposite winding: a hole under both fill rules
                    parts.append(polygon_path(hole, smooth, tol))
                    points += len(hole)
            child = hier[child][0]
        x0, y0 = outer.min(axis=0)
        x1, y1 = outer.max(axis=0)
        out.append({"d": " ".join(p for p in parts if p), "box": [float(x0), float(y0), float(x1 - x0), float(y1 - y0)], "area": float(area), "points": points})
    out.sort(key=lambda p: -p["area"])
    return out


def vectorize(data: bytes, colors: int = 6, detail: str = "medium", smooth: bool = True, max_side: int = 1400, despeckle_px: int | None = None) -> dict:
    """Trace a raster image. Returns layers (largest first), a standalone SVG and notes."""
    import cv2
    import numpy as np

    img = open_image(data)
    src_w, src_h = img.size
    arr = np.asarray(img)
    limit = max(64, min(int(max_side), 2400))
    longest = max(src_w, src_h)
    if longest > limit:
        scale = limit / longest
        arr = cv2.resize(arr, (max(1, round(src_w * scale)), max(1, round(src_h * scale))), interpolation=cv2.INTER_AREA)
    elif longest < 0.72 * limit:
        # Small images are enlarged first: the anti-aliased edges then carry sub-pixel detail into the outlines.
        scale = min(3.0, limit / longest)
        arr = cv2.resize(arr, (max(1, round(src_w * scale)), max(1, round(src_h * scale))), interpolation=cv2.INTER_CUBIC)
    else:
        scale = 1.0
    h, w = arr.shape[:2]
    if arr.shape[2] == 4:
        rgb, opaque = np.ascontiguousarray(arr[:, :, :3]), arr[:, :, 3] > 127
    else:
        rgb, opaque = np.ascontiguousarray(arr), np.ones((h, w), dtype=bool)
    # Edge-preserving smoothing: removes JPEG mush before colours are counted.
    rgb = cv2.bilateralFilter(rgb, 5, 28, 28)

    k = max(2, min(MAX_COLORS, int(colors or 6)))
    labels, palette, error = quantize(rgb, opaque, k, fringe_radius=2 + int(round(max(1.0, scale))))
    min_area = int(despeckle_px) if despeckle_px else max(4, round(w * h / 400_000))
    labels = despeckle(labels, min_area)
    eps = DETAIL.get(detail, DETAIL["medium"])

    counts = [(int((labels == i).sum()), i) for i in range(len(palette))]
    order = [i for n, i in sorted(counts, reverse=True) if n > 0]
    rank = np.full(len(palette), -1, dtype=np.int32)
    for r, i in enumerate(order):
        rank[i] = r
    rank_map = np.where(labels >= 0, rank[np.clip(labels, 0, None)], -1)

    layers: list[dict] = []
    total_points = 0
    for r, i in enumerate(order):
        mask = rank_map >= r
        if r == 0 and mask.all():
            paths = [{"d": f"M0 0 L{w} 0 L{w} {h} L0 {h} Z", "box": [0.0, 0.0, float(w), float(h)], "area": float(w * h), "points": 4}]
            full = True
        else:
            paths = trace_mask(mask, eps, float(min_area), smooth)
            full = False
        if not paths:
            continue
        total_points += sum(p["points"] for p in paths)
        layers.append({"fill": _hex(palette[i]), "d": " ".join(p["d"] for p in paths), "paths": paths, "pixels": int((labels == i).sum()), "full": full})

    body = "".join(f'<path d="{layer["d"]}" fill="{layer["fill"]}" fill-rule="evenodd"/>' for layer in layers)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{src_w}" height="{src_h}" viewBox="0 0 {w} {h}">{body}</svg>'
    notes: list[str] = []
    if error > 9.0:
        notes.append("this image has gradients or photographic detail, so the tracing looks posterised; vectorising suits line art, logos and flat-colour diagrams")
    if scale < 1.0:
        notes.append(f"traced at {w} x {h} px (the original is {src_w} x {src_h}); raise max_side for finer detail")
    if not opaque.all():
        notes.append("transparent areas were kept transparent")
    notes.append("text in the image becomes outlines, not editable text: retype labels as text boxes if they must stay editable")
    return {"width": w, "height": h, "source": [src_w, src_h], "layers": layers, "svg": svg, "colors": [layer["fill"] for layer in layers], "points": total_points, "error": round(error, 2), "notes": notes}


def _is_light(color: str) -> bool:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return min(r, g, b) >= 236


def vector_nodes(result: dict, x: float = 40.0, y: float = 40.0, max_width: float = 1000.0, split: bool = False, drop_background: bool = True, group: str = "vector") -> tuple[list[dict], float, float, list[str]]:
    """Scene ``path`` nodes for a tracing. Returns ``(nodes, width, height, notes)``.

    With ``split`` every island becomes its own node (recolour or delete single
    blobs); otherwise there is one node per colour.
    """
    w, h = float(result["width"]), float(result["height"])
    scale = min(1.0, max_width / w) if max_width else 1.0
    notes: list[str] = []
    layers = list(result["layers"])
    if drop_background and layers and layers[0].get("full") and _is_light(layers[0]["fill"]):
        layers = layers[1:]
        notes.append("the white background layer was left out so the figure sits directly on the canvas")
    pieces = sum(len(layer["paths"]) for layer in layers)
    if split and pieces > MAX_SPLIT_NODES:
        split = False
        notes.append(f"{pieces} separate shapes would be unwieldy, so the result is grouped into one layer per colour")
    nodes: list[dict] = []
    for li, layer in enumerate(layers):
        if not split:
            nodes.append({"id": f"{group}_{li + 1}", "type": "path", "x": x, "y": y, "w": round(w * scale, 1), "h": round(h * scale, 1), "d": layer["d"], "vb": [w, h], "fill": layer["fill"], "stroke": "none", "fillRule": "evenodd", "group": group, "name": f"colour {layer['fill']}"})
            continue
        for pi, p in enumerate(layer["paths"]):
            bx, by, bw, bh = p["box"]
            if bw <= 0 or bh <= 0:
                continue
            nodes.append({"id": f"{group}_{li + 1}_{pi + 1}", "type": "path", "x": round(x + bx * scale, 1), "y": round(y + by * scale, 1), "w": round(max(1.0, bw * scale), 1), "h": round(max(1.0, bh * scale), 1), "d": transform_path(p["d"], 1.0, 1.0, -bx, -by), "vb": [bw, bh], "fill": layer["fill"], "stroke": "none", "fillRule": "evenodd", "group": group, "name": f"shape {layer['fill']}"})
    return nodes, round(w * scale, 1), round(h * scale, 1), notes


def vector_scene(result: dict, theme: str | None = None, title: str = "", split: bool = False, max_width: float = 1000.0) -> dict:
    from .scene import new_scene, normalize_scene

    nodes, w, h, notes = vector_nodes(result, 40.0, 40.0, max_width, split)
    scene = new_scene(width=w + 80, height=h + 80, theme=theme, kind="illustration", title=title)
    scene["nodes"] = nodes
    scene = normalize_scene(scene)
    if notes:
        scene.setdefault("meta", {})["warnings"] = notes
    return scene
