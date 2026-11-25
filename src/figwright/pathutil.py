"""SVG path data: parse, normalise, flatten and measure.

Supports every path command (M L H V C S Q T A Z, absolute and relative).
``parse_path`` normalises to absolute M / L / C / Q / Z segments, which keeps
every consumer (bounding boxes, PowerPoint freeforms, rasterising in tests)
simple.
"""

from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}

Point = tuple[float, float]
Segment = tuple  # ("M", x, y) | ("L", x, y) | ("C", x1, y1, x2, y2, x, y) | ("Q", x1, y1, x, y) | ("Z",)


def _arc_to_cubics(x0: float, y0: float, rx: float, ry: float, phi_deg: float, large: bool, sweep: bool, x: float, y: float) -> list[Segment]:
    """Convert an elliptical arc (endpoint form) to cubic Bezier segments."""
    if rx == 0 or ry == 0 or (x0 == x and y0 == y):
        return [("L", x, y)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg % 360.0)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x0 - x) / 2.0, (y0 - y) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * (rx * y1p / ry)
    cyp = coef * -(ry * x1p / rx)
    cx = cos_p * cxp - sin_p * cyp + (x0 + x) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (y0 + y) / 2.0

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        ln = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / ln))) if ln else 0.0
        return -a if ux * vy - uy * vx < 0 else a

    th1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    n = max(1, int(math.ceil(abs(dth) / (math.pi / 2) - 1e-9)))
    step = dth / n
    t = 4.0 / 3.0 * math.tan(step / 4.0)
    out: list[Segment] = []
    a = th1
    for _ in range(n):
        b = a + step
        ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
        p1 = (ca - t * sa, sa + t * ca)
        p2 = (cb + t * sb, sb - t * cb)
        p3 = (cb, sb)

        def tr(p: Point) -> Point:
            px, py = p[0] * rx, p[1] * ry
            return (cos_p * px - sin_p * py + cx, sin_p * px + cos_p * py + cy)

        q1, q2, q3 = tr(p1), tr(p2), tr(p3)
        out.append(("C", q1[0], q1[1], q2[0], q2[1], q3[0], q3[1]))
        a = b
    # Snap the final point exactly onto the requested endpoint.
    last = out[-1]
    out[-1] = ("C", last[1], last[2], last[3], last[4], x, y)
    return out


def parse_path(d: str) -> list[Segment]:
    """Parse path data into absolute M / L / C / Q / Z segments."""
    if not d:
        return []
    tokens = [(m.group(1), m.group(2)) for m in _TOKEN.finditer(d)]
    segs: list[Segment] = []
    i = 0
    cmd = ""
    cx = cy = 0.0  # current point
    sx = sy = 0.0  # subpath start
    last_ctrl: Point | None = None
    last_kind = ""
    n = len(tokens)

    def take(k: int) -> list[float] | None:
        nonlocal i
        vals: list[float] = []
        while len(vals) < k:
            if i >= n or tokens[i][1] is None:
                return None
            vals.append(float(tokens[i][1]))
            i += 1
        return vals

    while i < n:
        letter, number = tokens[i]
        if letter is not None:
            cmd = letter
            i += 1
            if cmd in "Zz":
                segs.append(("Z",))
                cx, cy = sx, sy
                last_kind = "Z"
                continue
        elif not cmd:
            i += 1
            continue
        up = cmd.upper()
        rel = cmd != up
        if up == "Z":
            # Stray numbers after Z: ignore them.
            i += 1
            continue
        args = take(_ARGS[up])
        if args is None:
            break
        if up == "M":
            x, y = args
            if rel:
                x, y = cx + x, cy + y
            segs.append(("M", x, y))
            cx, cy, sx, sy = x, y, x, y
            cmd = "l" if rel else "L"  # subsequent pairs are implicit line-tos
            last_kind = "M"
        elif up == "L":
            x, y = args
            if rel:
                x, y = cx + x, cy + y
            segs.append(("L", x, y))
            cx, cy = x, y
            last_kind = "L"
        elif up == "H":
            x = args[0] + (cx if rel else 0.0)
            segs.append(("L", x, cy))
            cx = x
            last_kind = "L"
        elif up == "V":
            y = args[0] + (cy if rel else 0.0)
            segs.append(("L", cx, y))
            cy = y
            last_kind = "L"
        elif up == "C":
            x1, y1, x2, y2, x, y = args
            if rel:
                x1, y1, x2, y2, x, y = cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y
            segs.append(("C", x1, y1, x2, y2, x, y))
            last_ctrl = (x2, y2)
            cx, cy = x, y
            last_kind = "C"
        elif up == "S":
            x2, y2, x, y = args
            if rel:
                x2, y2, x, y = cx + x2, cy + y2, cx + x, cy + y
            if last_kind == "C" and last_ctrl:
                x1, y1 = 2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]
            else:
                x1, y1 = cx, cy
            segs.append(("C", x1, y1, x2, y2, x, y))
            last_ctrl = (x2, y2)
            cx, cy = x, y
            last_kind = "C"
        elif up == "Q":
            x1, y1, x, y = args
            if rel:
                x1, y1, x, y = cx + x1, cy + y1, cx + x, cy + y
            segs.append(("Q", x1, y1, x, y))
            last_ctrl = (x1, y1)
            cx, cy = x, y
            last_kind = "Q"
        elif up == "T":
            x, y = args
            if rel:
                x, y = cx + x, cy + y
            if last_kind == "Q" and last_ctrl:
                x1, y1 = 2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]
            else:
                x1, y1 = cx, cy
            segs.append(("Q", x1, y1, x, y))
            last_ctrl = (x1, y1)
            cx, cy = x, y
            last_kind = "Q"
        elif up == "A":
            rx, ry, phi, large, sweep, x, y = args
            if rel:
                x, y = cx + x, cy + y
            segs.extend(_arc_to_cubics(cx, cy, rx, ry, phi, bool(large), bool(sweep), x, y))
            cx, cy = x, y
            last_kind = "A"
    return segs


def flatten_path(d: str | list[Segment], tolerance: float = 0.5) -> list[tuple[list[Point], bool]]:
    """Flatten to polylines: a list of ``(points, closed)`` subpaths."""
    segs = parse_path(d) if isinstance(d, str) else d
    out: list[tuple[list[Point], bool]] = []
    pts: list[Point] = []
    cur: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)

    def flush(closed: bool) -> None:
        nonlocal pts
        if len(pts) >= 2:
            out.append((pts, closed))
        pts = []

    def steps(*ctrl: Point) -> int:
        length = sum(math.dist(ctrl[k], ctrl[k + 1]) for k in range(len(ctrl) - 1))
        return max(2, min(64, int(math.ceil(math.sqrt(max(length, 1e-9) / max(tolerance, 1e-3)) * 1.6))))

    for seg in segs:
        k = seg[0]
        if k == "M":
            flush(False)
            cur = start = (seg[1], seg[2])
            pts = [cur]
        elif k == "L":
            if not pts:
                pts = [cur]
            cur = (seg[1], seg[2])
            pts.append(cur)
        elif k == "C":
            if not pts:
                pts = [cur]
            p0, p1, p2, p3 = cur, (seg[1], seg[2]), (seg[3], seg[4]), (seg[5], seg[6])
            m = steps(p0, p1, p2, p3)
            for j in range(1, m + 1):
                t = j / m
                u = 1 - t
                pts.append(
                    (
                        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                    )
                )
            cur = p3
        elif k == "Q":
            if not pts:
                pts = [cur]
            p0, p1, p2 = cur, (seg[1], seg[2]), (seg[3], seg[4])
            m = steps(p0, p1, p2)
            for j in range(1, m + 1):
                t = j / m
                u = 1 - t
                pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
            cur = p2
        elif k == "Z":
            flush(True)
            cur = start
            pts = []
    flush(False)
    return out


def path_bbox(d: str | list[Segment]) -> tuple[float, float, float, float] | None:
    """Bounding box ``(x, y, w, h)`` of a path, or ``None`` if it is empty."""
    xs: list[float] = []
    ys: list[float] = []
    for pts, _closed in flatten_path(d, tolerance=0.25):
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def segments_to_d(segs: list[Segment]) -> str:
    parts: list[str] = []
    for seg in segs:
        parts.append(seg[0] + " ".join(_fmt(v) for v in seg[1:]))
    return " ".join(parts)


def transform_path(d: str, sx: float = 1.0, sy: float = 1.0, tx: float = 0.0, ty: float = 0.0) -> str:
    """Scale then translate a path, returning new path data."""
    out: list[Segment] = []
    for seg in parse_path(d):
        if seg[0] == "Z":
            out.append(seg)
            continue
        vals = list(seg[1:])
        for j in range(0, len(vals), 2):
            vals[j] = vals[j] * sx + tx
            vals[j + 1] = vals[j + 1] * sy + ty
        out.append((seg[0], *vals))
    return segments_to_d(out)
