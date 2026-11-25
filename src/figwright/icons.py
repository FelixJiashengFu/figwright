"""Built-in icon library.

Every icon is original artwork drawn for Figwright on a 64 x 64 grid from a few
primitives (circle, ellipse, rounded rectangle, polyline/polygon, path). Using
primitives instead of opaque bitmaps keeps icons recolourable from the theme
and lets the PowerPoint exporter rebuild them as native, editable shapes.

Primitive encodings (JSON friendly, shared with ``web/scene.js``)::

    ["c", cx, cy, r, role]            circle
    ["e", cx, cy, rx, ry, role]       ellipse
    ["r", x, y, w, h, radius, role]   rectangle
    ["p", [x1, y1, x2, y2, ...], closed, role]   polyline / polygon
    ["d", "path data", role]          arbitrary path

Roles decide the paint:

    f   node fill + outline          a   accent fill, no outline
    A   accent fill + outline        w   white fill + outline
    s   solid outline colour         l   outline only
    la  accent-coloured line
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

ICON_BOX = 64.0


def C(cx, cy, r, role="f"):
    return ["c", cx, cy, r, role]


def E(cx, cy, rx, ry, role="f"):
    return ["e", cx, cy, rx, ry, role]


def R(x, y, w, h, rx=0, role="f"):
    return ["r", x, y, w, h, rx, role]


def P(pts, closed=1, role="f"):
    return ["p", [float(v) for v in pts], int(closed), role]


def L(x1, y1, x2, y2, role="l"):
    return ["p", [float(x1), float(y1), float(x2), float(y2)], 0, role]


def D(d, role="f"):
    return ["d", d, role]


def _ring(cx, cy, r, n, start_deg=0.0):
    return [(cx + r * math.cos(math.radians(start_deg + 360.0 * i / n)), cy + r * math.sin(math.radians(start_deg + 360.0 * i / n))) for i in range(n)]


def _r2(v: float) -> float:
    return round(v, 2)


def _gear():
    pts: list[float] = []
    teeth = 8
    for i in range(teeth):
        base = 360.0 * i / teeth
        for off, rad in ((-13, 19), (-8, 26), (8, 26), (13, 19)):
            a = math.radians(base + off)
            pts += [_r2(32 + rad * math.cos(a)), _r2(32 + rad * math.sin(a))]
    return [P(pts, 1, "f"), C(32, 32, 8.5, "w")]


def _star():
    pts: list[float] = []
    for i in range(10):
        rad = 27 if i % 2 == 0 else 11.5
        a = math.radians(-90 + 36 * i)
        pts += [_r2(32 + rad * math.cos(a)), _r2(33 + rad * math.sin(a))]
    return [P(pts, 1, "A")]


def _virus():
    prims = []
    for x, y in _ring(32, 32, 1, 8):
        dx, dy = x - 32, y - 32
        prims.append(L(_r2(32 + 16 * dx), _r2(32 + 16 * dy), _r2(32 + 23 * dx), _r2(32 + 23 * dy)))
        prims.append(C(_r2(32 + 25.5 * dx), _r2(32 + 25.5 * dy), 3.6, "a"))
    prims += [C(32, 32, 16, "f"), C(32, 32, 6, "a")]
    return prims


def _sun():
    prims = []
    for x, y in _ring(32, 32, 1, 8):
        dx, dy = x - 32, y - 32
        prims.append(L(_r2(32 + 17 * dx), _r2(32 + 17 * dy), _r2(32 + 27 * dx), _r2(32 + 27 * dy), "la"))
    prims.append(C(32, 32, 11.5, "A"))
    return prims


def _membrane():
    prims = []
    for x in (8, 20, 32, 44, 56):
        prims += [L(x, 23.5, x, 31), L(x, 40.5, x, 33), C(x, 18, 5.5, "f"), C(x, 46, 5.5, "f")]
    return prims


def _plate():
    prims = [R(4, 13, 56, 38, 5, "f")]
    hot = {(0, 1), (1, 3), (2, 0), (2, 2), (0, 4)}
    for ri, y in enumerate((23, 32, 41)):
        for ci, x in enumerate((13, 22.5, 32, 41.5, 51)):
            prims.append(C(x, y, 3.4, "a" if (ri, ci) in hot else "w"))
    return prims


def _crystal():
    corners = [(12, 24), (40, 24), (40, 52), (12, 52), (24, 12), (52, 12), (52, 40), (24, 40)]
    prims = [
        P([24, 12, 52, 12, 52, 40, 24, 40], 1, "l"),
        L(12, 24, 24, 12),
        L(40, 24, 52, 12),
        L(40, 52, 52, 40),
        L(12, 52, 24, 40),
        P([12, 24, 40, 24, 40, 52, 12, 52], 1, "l"),
    ]
    prims += [C(x, y, 3.6, "a") for x, y in corners]
    return prims


def _chip():
    prims = []
    for v in (22, 32, 42):
        prims += [L(v, 16, v, 7), L(v, 48, v, 57), L(16, v, 7, v), L(48, v, 57, v)]
    prims += [R(16, 16, 32, 32, 3, "f"), R(24, 24, 16, 16, 2, "a")]
    return prims


def _neuralnet():
    layers = [[(10, 16), (10, 32), (10, 48)], [(32, 12), (32, 32), (32, 52)], [(54, 23), (54, 41)]]
    prims = []
    for a, b in zip(layers, layers[1:]):
        for p in a:
            for q in b:
                prims.append(L(p[0], p[1], q[0], q[1]))
    for li, layer in enumerate(layers):
        prims += [C(x, y, 5.2, "a" if li == 1 else "f") for x, y in layer]
    return prims


def _heatmap():
    roles = [["a", "f", "w"], ["f", "a", "f"], ["w", "f", "a"]]
    return [R(8 + 16 * c, 8 + 16 * r, 16, 16, 0, roles[r][c]) for r in range(3) for c in range(3)]


def _tcell():
    prims = []
    for deg in (-90, -35, -145):
        a = math.radians(deg)
        dx, dy = math.cos(a), math.sin(a)
        prims.append(L(_r2(32 + 17 * dx), _r2(35 + 17 * dy), _r2(32 + 26 * dx), _r2(35 + 26 * dy)))
        prims.append(C(_r2(32 + 27.5 * dx), _r2(35 + 27.5 * dy), 3, "a"))
    prims += [C(32, 35, 18, "f"), C(32, 35, 8, "a")]
    return prims


_AXES = P([7, 6, 7, 57, 59, 57], 0, "l")

ICONS: dict[str, list] = {
    # ---- biology and medicine -------------------------------------------------
    "cell": [E(32, 32, 27, 23), C(37, 34, 9, "a"), E(19, 26, 5, 3, "w"), C(23, 43, 3, "w"), C(46, 22, 2.5, "w")],
    "cells": [C(21, 24, 13), C(43, 26, 12), C(31, 45, 13), C(21, 24, 4, "a"), C(43, 26, 4, "a"), C(31, 45, 4, "a")],
    "nucleus": [C(32, 32, 25), C(38, 38, 7, "a"), D("M17 30 C21 22 26 36 31 26 C34 20 40 24 43 19", "l")],
    "mitochondrion": [R(5, 18, 54, 28, 14), D("M13 32 L19 24 L25 40 L31 24 L37 40 L43 24 L49 40 L52 33", "l")],
    "dna": [
        L(26, 10, 38, 10),
        L(22, 24, 42, 24),
        L(22, 44, 42, 44),
        L(25, 57, 39, 57),
        D("M20 4 C20 12 44 16 44 24 C44 32 20 36 20 44 C20 52 44 54 44 60", "l"),
        D("M44 4 C44 12 20 16 20 24 C20 32 44 36 44 44 C44 52 20 54 20 60", "la"),
    ],
    "chromosome": [
        D(
            "M22 6 C16 6 14 12 18 18 L28 32 L18 46 C14 52 16 58 22 58 C26 58 28 54 30 50 L32 46 L34 50 "
            "C36 54 38 58 42 58 C48 58 50 52 46 46 L36 32 L46 18 C50 12 48 6 42 6 C38 6 36 10 34 14 L32 18 L30 14 C28 10 26 6 22 6 Z"
        )
    ],
    "gene": [L(3, 46, 61, 46), R(24, 38, 30, 16, 2), P([12, 46, 12, 26, 26, 26], 0, "l"), P([25, 21, 34, 26, 25, 31], 1, "s")],
    "protein": [
        D("M14 30 C10 16 28 8 38 14 C50 10 58 24 50 34 C58 46 42 58 30 50 C16 56 8 42 14 30 Z"),
        D("M24 28 C28 22 34 30 40 24", "l"),
        D("M24 40 C30 36 34 44 42 38", "l"),
    ],
    "enzyme": [D("M32 32 L52.8 20 A24 24 0 1 0 52.8 44 Z"), C(51, 32, 5.5, "a")],
    "receptor": [R(3, 34, 58, 11, 4, "w"), P([27, 58, 27, 26, 13, 10, 20, 6, 32, 19, 44, 6, 51, 10, 37, 26, 37, 58], 1, "A")],
    "antibody": [
        P([28, 58, 28, 34, 12, 14, 18, 9, 32, 27, 46, 9, 52, 14, 36, 34, 36, 58], 1, "f"),
        P([9, 24, 2, 15, 7, 11, 14, 20], 1, "a"),
        P([55, 24, 62, 15, 57, 11, 50, 20], 1, "a"),
    ],
    "membrane": _membrane(),
    "vesicle": [C(32, 32, 24), C(32, 32, 17, "w"), C(26, 29, 3.2, "a"), C(37, 27, 3.2, "a"), C(33, 38, 3.2, "a")],
    "virus": _virus(),
    "bacterium": [D("M46 32 C50 22 55 42 61 30", "l"), R(5, 21, 42, 22, 11), C(17, 32, 2.2, "a"), C(27, 29, 2.2, "a"), C(35, 35, 2.2, "a")],
    "tcell": _tcell(),
    "neuron": [
        L(14, 22, 6, 11),
        L(11, 31, 2, 31),
        L(14, 39, 6, 50),
        L(22, 19, 22, 7),
        L(30, 22, 37, 11),
        D("M32 35 C42 38 46 46 55 46", "l"),
        L(55, 46, 62, 40),
        L(55, 46, 62, 52),
        C(22, 30, 11),
        C(22, 30, 4, "a"),
    ],
    "mouse": [
        D("M11 41 C2 40 1 29 8 25", "l"),
        L(21, 51, 21, 57),
        L(37, 51, 37, 57),
        E(29, 39, 20, 13),
        C(45, 23, 6.5, "w"),
        C(49, 32, 9.5),
        C(53, 31, 1.6, "s"),
        C(58.5, 34, 2.2, "a"),
    ],
    "fish": [P([47, 32, 60, 20, 60, 44], 1, "f"), D("M6 32 C17 15 40 15 49 32 C40 49 17 49 6 32 Z"), C(17, 29, 2, "s"), D("M27 22 C31 28 31 36 27 42", "l")],
    "plant": [L(32, 59, 32, 29), D("M32 36 C19 36 13 28 13 19 C24 19 32 25 32 36 Z"), D("M32 30 C45 30 51 22 51 11 C40 11 32 19 32 30 Z"), L(18, 59, 46, 59)],
    "leaf": [D("M9 55 C9 25 29 8 57 8 C57 35 40 55 9 55 Z"), L(9, 55, 43, 21)],
    "human": [D("M16 60 L16 42 C16 31 23 26 32 26 C41 26 48 31 48 42 L48 60 Z"), C(32, 14, 9)],
    "users": [
        D("M36 56 L36 42 C36 34 40 30 46 30 C52 30 58 34 58 42 L58 56 Z", "w"),
        C(46, 20, 7, "w"),
        D("M6 60 L6 44 C6 34 13 29 22 29 C31 29 38 34 38 44 L38 60 Z"),
        C(22, 18, 8.5),
    ],
    "heart": [D("M32 55 C6 38 8 14 22 13 C28 12.5 32 17 32 22 C32 17 36 12.5 42 13 C56 14 58 38 32 55 Z", "A")],
    "brain": [
        D("M30 10 C14 7 5 21 11 32 C5 43 14 57 30 54 Z"),
        D("M34 10 C50 7 59 21 53 32 C59 43 50 57 34 54 Z"),
        D("M13 27 C19 25 21 31 27 29", "l"),
        D("M37 29 C43 31 45 25 51 27", "l"),
        D("M15 42 C20 40 22 44 27 42", "l"),
        D("M37 42 C42 44 44 40 49 42", "l"),
    ],
    "lung": [
        D("M27 16 L27 45 C27 53 19 57 11 55 C5 53 5 40 9 29 C13 19 21 13 27 16 Z"),
        D("M37 16 L37 45 C37 53 45 57 53 55 C59 53 59 40 55 29 C51 19 43 13 37 16 Z"),
        L(32, 4, 32, 18),
        L(32, 18, 26, 25),
        L(32, 18, 38, 25),
    ],
    "kidney": [
        D("M38 7 C55 8 59 32 51 47 C45 58 30 58 26 48 C23 41 33 38 33 32 C33 26 23 23 25 14 C27 8 32 6.5 38 7 Z"),
        D("M32 32 C24 34 20 42 20 57", "l"),
    ],
    "eye": [D("M3 32 C15 12 49 12 61 32 C49 52 15 52 3 32 Z", "w"), C(32, 32, 9.5, "A"), C(32, 32, 4, "s")],
    "drop": [D("M32 5 C22 21 14 30 14 40 C14 51 22 59 32 59 C42 59 50 51 50 40 C50 30 42 21 32 5 Z"), D("M21 41 C21 47 25 51 30 52", "la")],
    "pill": [R(6, 21, 52, 22, 11), D("M32 21 L47 21 C53 21 58 26 58 32 C58 38 53 43 47 43 L32 43 Z", "a"), R(6, 21, 52, 22, 11, "l"), L(32, 21, 32, 43)],
    "syringe": [L(3, 24, 3, 40), L(3, 32, 14, 32), R(14, 24, 32, 16, 2, "w"), R(26, 26, 18, 12, 0, "a"), R(46, 28, 5, 8, 1), L(51, 32, 62, 32), L(20, 24, 20, 29)],
    "hospital": [R(7, 7, 50, 50, 9, "w"), P([26, 15, 38, 15, 38, 26, 49, 26, 49, 38, 38, 38, 38, 49, 26, 49, 26, 38, 15, 38, 15, 26, 26, 26], 1, "a")],
    # ---- wet lab ----------------------------------------------------------------
    "petri": [E(32, 37, 27, 15), E(32, 34, 22, 11, "w"), C(24, 33, 3, "a"), C(37, 31, 2.6, "a"), C(41, 37, 2, "a"), C(29, 38.5, 2, "a")],
    "tube": [D("M22 15 L42 15 L42 38 L32 58 L22 38 Z", "w"), D("M24 34 L40 34 L40 37.5 L32 53.5 L24 37.5 Z", "a"), R(18, 8, 28, 7, 2)],
    "flask": [
        D("M26 6 L38 6 L38 24 L54 54 C55 57 53 58 51 58 L13 58 C11 58 9 57 10 54 L26 24 Z", "w"),
        P([18.3, 40, 45.7, 40, 52.4, 53.6, 50.6, 56, 13.4, 56, 11.6, 53.6], 1, "a"),
        L(23, 6, 41, 6),
    ],
    "beaker": [
        D("M14 8 L50 8 L50 54 C50 56 48 58 46 58 L18 58 C16 58 14 56 14 54 Z", "w"),
        D("M16 30 L48 30 L48 54 C48 55 47 56 46 56 L18 56 C17 56 16 55 16 54 Z", "a"),
        L(14, 8, 9, 5),
        L(40, 16, 46, 16),
        L(40, 23, 46, 23),
    ],
    "microscope": [
        R(12, 54, 40, 5, 2, "s"),
        P([40, 54, 40, 26, 46, 26, 46, 54], 1, "f"),
        P([34, 20, 46, 25, 46, 31, 36, 27], 1, "f"),
        P([20, 12, 29, 7, 41, 29, 32, 34], 1, "f"),
        P([17, 8, 26, 3, 28, 7, 19, 12], 1, "a"),
        P([33, 35, 40, 31, 43, 37, 37, 41], 1, "a"),
        R(18, 45, 26, 4, 1, "s"),
    ],
    "pipette": [P([44, 8, 52, 16, 26, 42, 18, 34], 1, "f"), P([50, 2, 58, 10, 54, 14, 46, 6], 1, "a"), P([18, 34, 26, 42, 8, 56], 1, "w"), C(6.5, 60, 2.4, "a")],
    "plate": _plate(),
    "gel": [
        R(8, 5, 48, 54, 3, "w"),
        R(13, 10, 9, 3, 0, "s"),
        R(27.5, 10, 9, 3, 0, "s"),
        R(42, 10, 9, 3, 0, "s"),
        R(13, 22, 9, 3, 1, "a"),
        R(13, 36, 9, 3, 1, "a"),
        R(27.5, 28, 9, 3, 1, "a"),
        R(27.5, 46, 9, 3, 1, "a"),
        R(42, 20, 9, 3, 1, "a"),
        R(42, 40, 9, 3, 1, "a"),
    ],
    "scissors": [L(21, 41, 58, 13), L(21, 23, 58, 51), C(15, 46, 7.5, "w"), C(15, 18, 7.5, "w")],
    "funnel": [P([5, 9, 59, 9, 38, 34, 38, 56, 26, 49, 26, 34], 1, "f")],
    # ---- chemistry and physics --------------------------------------------------
    "atom": [
        D("M58 32 A26 10 0 1 0 6 32 A26 10 0 1 0 58 32 Z", "l"),
        D("M45 54.5 A26 10 60 1 0 19 9.5 A26 10 60 1 0 45 54.5 Z", "l"),
        D("M19 54.5 A26 10 120 1 0 45 9.5 A26 10 120 1 0 19 54.5 Z", "l"),
        C(32, 32, 5, "a"),
    ],
    "molecule": [L(20, 40, 42, 24), L(20, 40, 46, 49), C(20, 40, 9.5), C(42, 24, 7.5, "a"), C(46, 49, 6, "w")],
    "benzene": [P([32, 7, 53.7, 19.5, 53.7, 44.5, 32, 57, 10.3, 44.5, 10.3, 19.5], 1, "f"), C(32, 32, 13, "l")],
    "crystal": _crystal(),
    "magnet": [D("M12 8 L24 8 L24 34 A8 8 0 0 0 40 34 L40 8 L52 8 L52 34 A20 20 0 0 1 12 34 Z"), R(12, 8, 12, 10, 0, "a"), R(40, 8, 12, 10, 0, "a")],
    "lightning": [P([37, 3, 13, 36, 29, 36, 25, 61, 51, 26, 35, 26], 1, "A")],
    "thermometer": [R(26.5, 5, 11, 38, 5.5, "w"), C(32, 48, 10.5, "A"), R(30, 20, 4, 24, 0, "a"), L(42, 14, 48, 14), L(42, 22, 48, 22), L(42, 30, 48, 30)],
    "wave": [L(3, 32, 61, 32), D("M3 32 Q13 4 23 32 Q33 60 43 32 Q53 4 61 26", "la")],
    "peak": [_AXES, D("M10 54 C20 54 21 14 27 14 C33 14 33 54 38 54 C42 54 43 36 47 36 C51 36 51 54 57 54", "la")],
    "battery": [R(5, 20, 48, 24, 4, "w"), R(53, 27, 6, 10, 1, "s"), R(10, 25, 10, 14, 1, "a"), R(23, 25, 10, 14, 1, "a"), R(36, 25, 10, 14, 1, "f")],
    "sun": _sun(),
    # ---- computing and data -----------------------------------------------------
    "database": [D("M10 16 L10 48 C10 54 20 58 32 58 C44 58 54 54 54 48 L54 16 Z"), E(32, 16, 22, 8, "w"), D("M10 32 C10 38 20 42 32 42 C44 42 54 38 54 32", "l")],
    "server": [
        R(9, 7, 46, 14, 3),
        R(9, 25, 46, 14, 3),
        R(9, 43, 46, 14, 3),
        C(17, 14, 2.4, "a"),
        C(17, 32, 2.4, "a"),
        C(17, 50, 2.4, "a"),
        L(38, 14, 48, 14),
        L(38, 32, 48, 32),
        L(38, 50, 48, 50),
    ],
    "chip": _chip(),
    "computer": [R(5, 8, 54, 36, 3), R(9, 12, 46, 28, 1, "w"), P([26, 44, 38, 44, 40, 53, 24, 53], 1, "s"), R(17, 53, 30, 4, 2, "s")],
    "cloud": [D("M18 49 C7 49 3 40 8 33 C6 23 16 17 23 22 C26 11 43 9 46 22 C57 19 63 31 57 38 C60 45 54 49 48 49 Z")],
    "document": [D("M13 5 L39 5 L52 18 L52 59 L13 59 Z", "w"), P([39, 5, 39, 18, 52, 18], 1, "f"), L(20, 29, 45, 29), L(20, 37, 45, 37), L(20, 45, 37, 45)],
    "book": [D("M32 14 C24 8 12 8 6 12 L6 52 C12 48 24 48 32 54 Z"), D("M32 14 C40 8 52 8 58 12 L58 52 C52 48 40 48 32 54 Z", "w")],
    "table": [R(6, 10, 52, 44, 3, "w"), R(6, 10, 52, 11, 3, "f"), L(6, 21, 58, 21), L(6, 32, 58, 32), L(6, 43, 58, 43), L(24, 10, 24, 54), L(41, 10, 41, 54)],
    "image": [R(5, 9, 54, 46, 4, "w"), C(20, 23, 5, "a"), P([9, 51, 26, 32, 36, 42, 44, 34, 55, 47, 55, 51], 1, "f")],
    "camera": [R(22, 10, 20, 9, 2), R(5, 17, 54, 36, 5), C(32, 35, 11, "w"), C(32, 35, 5, "a")],
    "chart": [_AXES, R(14, 36, 10, 21, 0, "a"), R(28, 22, 10, 35, 0, "f"), R(42, 12, 10, 45, 0, "a")],
    "linechart": [_AXES, P([12, 46, 23, 33, 33, 40, 45, 17, 56, 23], 0, "la"), C(12, 46, 2.6, "a"), C(23, 33, 2.6, "a"), C(33, 40, 2.6, "a"), C(45, 17, 2.6, "a"), C(56, 23, 2.6, "a")],
    "scatter": [_AXES] + [C(x, y, 2.8, "a") for x, y in ((16, 44), (22, 36), (28, 40), (33, 28), (40, 31), (45, 19), (52, 22))],
    "heatmap": _heatmap(),
    "network": [L(32, 34, 32, 12), L(32, 34, 12, 48), L(32, 34, 52, 48), L(12, 48, 52, 48), C(32, 12, 6.5), C(12, 48, 6.5), C(52, 48, 6.5), C(32, 34, 6.5, "a")],
    "neuralnet": _neuralnet(),
    "robot": [L(32, 18, 32, 9), C(32, 6.5, 3.2, "a"), R(5, 28, 7, 12, 2, "s"), R(52, 28, 7, 12, 2, "s"), R(12, 18, 40, 34, 7), C(24, 32, 4.2, "a"), C(40, 32, 4.2, "a"), L(24, 43, 40, 43)],
    "code": [P([22, 16, 7, 32, 22, 48], 0, "l"), P([42, 16, 57, 32, 42, 48], 0, "l"), L(36, 11, 28, 53, "la")],
    "gear": _gear(),
    "layers": [P([6, 43, 32, 56, 58, 43], 0, "l"), P([6, 31, 32, 44, 58, 31], 0, "l"), P([32, 6, 58, 19, 32, 32, 6, 19], 1, "A")],
    # ---- general ----------------------------------------------------------------
    "lightbulb": [
        D("M32 5 C20 5 14 14 14 24 C14 32 20 36 22 43 L42 43 C44 36 50 32 50 24 C50 14 44 5 32 5 Z"),
        R(24, 46, 16, 4, 2, "s"),
        R(26, 52, 12, 4, 2, "s"),
        P([27, 31, 32, 24, 37, 31], 0, "l"),
    ],
    "magnifier": [P([36, 40, 40, 36, 59, 55, 55, 59], 1, "s"), C(26, 26, 17, "w"), D("M17 26 C17 21 21 17 26 17", "la")],
    "target": [C(32, 32, 26), C(32, 32, 17, "w"), C(32, 32, 8, "a")],
    "star": _star(),
    "flag": [L(13, 5, 13, 60), D("M13 8 C23 2 33 16 51 10 L51 32 C33 38 23 24 13 30 Z", "A")],
    "clock": [C(32, 32, 26, "w"), L(32, 32, 32, 16), L(32, 32, 43, 38), C(32, 32, 2.2, "s")],
    "globe": [C(32, 32, 26), E(32, 32, 11, 26, "l"), L(6, 32, 58, 32), D("M10 19 C22 25 42 25 54 19", "l"), D("M10 45 C22 39 42 39 54 45", "l")],
    "scale": [
        L(32, 8, 32, 54),
        L(12, 16, 52, 16),
        L(12, 16, 4, 34),
        L(12, 16, 20, 34),
        L(52, 16, 44, 34),
        L(52, 16, 60, 34),
        D("M4 34 C4 41 20 41 20 34 Z"),
        D("M44 34 C44 41 60 41 60 34 Z"),
        R(22, 54, 20, 4, 2, "s"),
    ],
    "arrow": [P([4, 23, 36, 23, 36, 11, 60, 32, 36, 53, 36, 41, 4, 41], 1, "A")],
    "cycle": [D("M50 32 A18 18 0 1 1 44.7 19.3", "l"), P([51.5, 26, 49, 12, 37.5, 22.5], 1, "s")],
    "check": [C(32, 32, 26), P([19, 33, 28, 42, 45, 23], 0, "l")],
    "cross": [C(32, 32, 26), L(22, 22, 42, 42), L(42, 22, 22, 42)],
    "plus": [C(32, 32, 26), L(32, 18, 32, 46), L(18, 32, 46, 32)],
    "minus": [C(32, 32, 26), L(18, 32, 46, 32)],
    "question": [C(32, 32, 26), D("M24 25 C24 14 41 14 41 24 C41 31 32 31 32 39", "l"), C(32, 47, 2.4, "s")],
}

# name -> (Chinese label, category, search keywords). The keywords drive the
# icon picker's search box, the offline draft generator and the fallback used
# when a model asks for an icon that does not exist.
ICON_META: dict[str, tuple[str, str, list[str]]] = {
    "cell": ("细胞", "bio", ["cell", "细胞", "cellular", "cancer cell", "肿瘤细胞", "culture", "培养"]),
    "cells": ("细胞群", "bio", ["cells", "tissue", "组织", "organoid", "类器官", "cluster", "tumor", "肿瘤", "colony"]),
    "nucleus": ("细胞核", "bio", ["nucleus", "细胞核", "nuclear", "核内", "chromatin", "染色质"]),
    "mitochondrion": ("线粒体", "bio", ["mitochondri", "线粒体", "atp", "respiration", "呼吸"]),
    "dna": ("DNA", "bio", ["dna", "genome", "基因组", "sequenc", "测序", "rna", "转录", "transcri", "helix", "核酸", "crispr", "pcr", "plasmid", "质粒"]),
    "chromosome": ("染色体", "bio", ["chromosome", "染色体", "karyotype", "mitosis", "有丝分裂"]),
    "gene": ("基因", "bio", ["gene", "基因", "promoter", "启动子", "expression", "表达", "locus"]),
    "protein": ("蛋白质", "bio", ["protein", "蛋白", "peptide", "肽", "fold", "折叠", "aggregate", "聚集", "tau", "amyloid"]),
    "enzyme": ("酶", "bio", ["enzyme", "酶", "kinase", "激酶", "catalys", "催化", "substrate", "底物", "protease"]),
    "receptor": ("受体", "bio", ["receptor", "受体", "gpcr", "channel", "通道", "transporter", "转运体"]),
    "antibody": ("抗体", "bio", ["antibody", "抗体", "igg", "immun", "免疫", "elisa", "western", "blot", "stain", "染色"]),
    "membrane": ("细胞膜", "bio", ["membrane", "膜", "bilayer", "lipid", "脂质", "磷脂"]),
    "vesicle": ("囊泡", "bio", ["vesicle", "囊泡", "exosome", "外泌体", "liposome", "脂质体", "endosome", "lysosome", "溶酶体", "nanoparticle", "纳米颗粒"]),
    "virus": ("病毒", "bio", ["virus", "病毒", "viral", "infect", "感染", "aav", "lentivirus", "vector", "phage"]),
    "bacterium": ("细菌", "bio", ["bacteri", "细菌", "microb", "微生物", "e. coli", "大肠杆菌", "probiotic", "菌"]),
    "tcell": ("免疫细胞", "bio", ["t cell", "t细胞", "immune cell", "免疫细胞", "lymphocyte", "淋巴", "macrophage", "巨噬", "car-t"]),
    "neuron": ("神经元", "bio", ["neuron", "神经元", "neural", "神经", "synap", "突触", "axon", "轴突"]),
    "mouse": ("小鼠", "bio", ["mouse", "mice", "小鼠", "rat", "大鼠", "animal", "动物", "in vivo", "体内", "rodent"]),
    "fish": ("斑马鱼", "bio", ["fish", "鱼", "zebrafish", "斑马鱼"]),
    "plant": ("植物", "bio", ["plant", "植物", "seedling", "幼苗", "arabidopsis", "拟南芥", "crop", "作物"]),
    "leaf": ("叶片", "bio", ["leaf", "叶", "photosynth", "光合", "green", "绿色", "eco", "生态"]),
    "human": ("受试者", "bio", ["patient", "患者", "病人", "human", "人", "participant", "受试者", "subject", "volunteer", "志愿者", "person"]),
    "users": ("人群", "bio", ["cohort", "队列", "population", "人群", "group", "组", "team", "participants", "recruit", "招募", "users"]),
    "heart": ("心脏", "bio", ["heart", "心", "cardiac", "cardio", "心血管"]),
    "brain": ("大脑", "bio", ["brain", "脑", "cognit", "认知", "cortex", "皮层", "alzheimer", "阿尔茨海默"]),
    "lung": ("肺", "bio", ["lung", "肺", "respirat", "呼吸道", "pulmon"]),
    "kidney": ("肾", "bio", ["kidney", "肾", "renal"]),
    "eye": ("眼", "bio", ["eye", "眼", "vision", "视觉", "retina", "视网膜", "observe", "观察"]),
    "drop": ("液滴", "bio", ["blood", "血", "serum", "血清", "plasma", "血浆", "drop", "液滴", "sample", "样本", "water", "水", "solvent", "溶剂"]),
    "pill": ("药物", "bio", ["drug", "药", "pill", "tablet", "treatment", "治疗", "therapy", "疗法", "compound", "化合物", "inhibitor", "抑制剂", "dose", "剂量"]),
    "syringe": ("注射", "bio", ["inject", "注射", "syringe", "vaccin", "疫苗", "administ", "给药"]),
    "hospital": ("临床", "bio", ["hospital", "医院", "clinic", "临床", "medical", "医疗", "trial", "试验"]),
    "petri": ("培养皿", "lab", ["petri", "培养皿", "dish", "culture dish", "plating", "涂板", "agar"]),
    "tube": ("离心管", "lab", ["tube", "管", "centrifug", "离心", "extract", "提取", "lysate", "裂解", "pellet", "supernatant", "上清"]),
    "flask": ("锥形瓶", "lab", ["flask", "瓶", "reaction", "反应", "synthesis", "合成", "solution", "溶液", "chemistry", "化学"]),
    "beaker": ("烧杯", "lab", ["beaker", "烧杯", "mix", "混合", "buffer", "缓冲", "dissolve", "溶解", "wash", "洗"]),
    "microscope": ("显微镜", "lab", ["microscop", "显微", "imaging", "成像", "confocal", "共聚焦", "fluorescen", "荧光", "histolog", "组织学"]),
    "pipette": ("移液器", "lab", ["pipett", "移液", "aliquot", "分装", "add", "加样", "transfect", "转染"]),
    "plate": ("孔板", "lab", ["plate", "孔板", "96-well", "96孔", "assay", "检测", "screen", "筛选", "high-throughput", "高通量"]),
    "gel": ("电泳", "lab", ["gel", "电泳", "electrophoresis", "band", "条带", "sds-page"]),
    "scissors": ("剪切", "lab", ["cut", "切", "cleav", "切割", "edit", "编辑", "knockout", "敲除", "scissors", "digest", "酶切"]),
    "funnel": ("过滤", "lab", ["filter", "过滤", "筛", "funnel", "purif", "纯化", "select", "exclude", "排除", "quality control", "质控"]),
    "atom": ("原子", "sci", ["atom", "原子", "quantum", "量子", "physics", "物理", "nuclear", "electron", "电子"]),
    "molecule": ("分子", "sci", ["molecule", "分子", "ligand", "配体", "small molecule", "小分子", "metabolite", "代谢物", "bond", "键"]),
    "benzene": ("苯环", "sci", ["benzene", "苯", "aromatic", "芳香", "organic", "有机"]),
    "crystal": ("晶体", "sci", ["crystal", "晶体", "lattice", "晶格", "material", "材料", "structure", "结构", "xrd", "mof"]),
    "magnet": ("磁体", "sci", ["magnet", "磁", "nmr", "mri", "核磁", "field", "场"]),
    "lightning": ("能量", "sci", ["energy", "能量", "electric", "电", "power", "stimul", "刺激", "activation", "激活", "voltage", "电压"]),
    "thermometer": ("温度", "sci", ["temperature", "温度", "heat", "加热", "thermal", "热", "incubat", "孵育", "cool", "冷"]),
    "wave": ("波", "sci", ["wave", "波", "signal", "信号", "oscillat", "振荡", "frequency", "频率", "light", "光"]),
    "peak": ("谱图", "sci", ["spectr", "谱", "chromatogra", "色谱", "peak", "峰", "mass spec", "质谱", "hplc", "lc-ms"]),
    "battery": ("电池", "sci", ["battery", "电池", "storage", "储能", "charge", "充电", "electrode", "电极"]),
    "sun": ("光照", "sci", ["sun", "太阳", "solar", "uv", "紫外", "irradiat", "照射", "photo", "光"]),
    "database": ("数据库", "data", ["database", "数据库", "dataset", "数据集", "data", "数据", "storage", "repository", "corpus", "语料"]),
    "server": ("服务器", "data", ["server", "服务器", "cluster", "集群", "hpc", "compute", "计算", "gpu"]),
    "chip": ("芯片", "data", ["chip", "芯片", "cpu", "processor", "处理器", "hardware", "硬件", "sensor", "传感器", "microfluid", "微流控"]),
    "computer": ("电脑", "data", ["computer", "电脑", "software", "软件", "simulation", "模拟", "in silico", "program", "程序", "interface", "界面"]),
    "cloud": ("云", "data", ["cloud", "云", "online", "在线", "api", "service", "服务", "web", "网络"]),
    "document": ("文档", "data", ["document", "文档", "paper", "论文", "report", "报告", "record", "记录", "text", "文本", "protocol", "方案", "questionnaire", "问卷"]),
    "book": ("文献", "data", ["literature", "文献", "book", "书", "review", "综述", "knowledge", "知识", "reference"]),
    "table": ("表格", "data", ["table", "表", "spreadsheet", "excel", "matrix", "矩阵", "feature", "特征"]),
    "image": ("图像", "data", ["image", "图像", "图片", "picture", "photo", "照片", "pixel"]),
    "camera": ("拍摄", "data", ["camera", "相机", "摄像", "record video", "capture", "采集", "拍"]),
    "chart": ("柱状图", "data", ["statistic", "统计", "analysis", "分析", "bar", "柱", "result", "结果", "quantif", "定量", "compare", "比较", "evaluate", "评估"]),
    "linechart": ("折线图", "data", ["trend", "趋势", "curve", "曲线", "time course", "时间", "growth", "增长", "monitor", "监测", "loss", "训练曲线"]),
    "scatter": ("散点图", "data", ["scatter", "散点", "correlat", "相关", "regress", "回归", "cluster plot", "umap", "pca", "降维"]),
    "heatmap": ("热图", "data", ["heatmap", "热图", "expression matrix", "表达谱", "attention", "注意力"]),
    "network": ("网络", "data", ["network", "网络", "graph", "图谱", "interact", "互作", "pathway", "通路", "connect", "连接"]),
    "neuralnet": ("神经网络", "data", ["neural net", "神经网络", "deep learning", "深度学习", "model", "模型", "train", "训练", "machine learning", "机器学习", "predict", "预测", "classif", "分类", "transformer", "llm"]),
    "robot": ("智能体", "data", ["robot", "机器人", "agent", "智能体", "automat", "自动", "ai", "人工智能", "assistant", "助手"]),
    "code": ("代码", "data", ["code", "代码", "script", "脚本", "algorithm", "算法", "pipeline", "流程", "program"]),
    "gear": ("处理", "data", ["process", "处理", "preprocess", "预处理", "config", "配置", "optimi", "优化", "engineer", "工程", "mechanism", "机制", "step"]),
    "layers": ("层", "data", ["layer", "层", "stack", "堆叠", "multi-omics", "多组学", "integrat", "整合", "fusion", "融合"]),
    "lightbulb": ("想法", "general", ["idea", "想法", "hypothes", "假设", "insight", "发现", "innovation", "创新", "conclusion", "结论", "finding"]),
    "magnifier": ("检索", "general", ["search", "检索", "搜索", "identif", "鉴定", "detect", "检测", "inspect", "检查", "screening", "discover", "explore", "探索"]),
    "target": ("目标", "general", ["target", "靶", "目标", "goal", "aim", "objective", "目的", "specific", "特异"]),
    "star": ("亮点", "general", ["highlight", "亮点", "key", "关键", "best", "最佳", "novel", "新颖", "important", "重要"]),
    "flag": ("里程碑", "general", ["milestone", "里程碑", "endpoint", "终点", "finish", "完成", "outcome", "结局"]),
    "clock": ("时间", "general", ["time", "时间", "hour", "小时", "day", "天", "week", "周", "duration", "wait", "等待", "follow-up", "随访", "longitudinal"]),
    "globe": ("全球", "general", ["global", "全球", "world", "世界", "environment", "环境", "geograph", "地理", "international"]),
    "scale": ("权衡", "general", ["balance", "平衡", "weigh", "称量", "ethic", "伦理", "trade-off", "权衡", "random", "随机"]),
    "arrow": ("箭头", "general", ["arrow", "箭头", "next", "下一步", "output", "输出", "input", "输入", "flow"]),
    "cycle": ("循环", "general", ["cycle", "循环", "repeat", "重复", "iterat", "迭代", "feedback", "反馈", "loop", "recycle", "refine"]),
    "check": ("通过", "general", ["valid", "验证", "confirm", "确认", "pass", "通过", "included", "纳入", "success", "成功", "approve"]),
    "cross": ("排除", "general", ["reject", "拒绝", "fail", "失败", "error", "错误", "excluded", "剔除", "negative", "阴性", "block"]),
    "plus": ("增加", "general", ["add", "加", "increase", "增加", "positive", "阳性", "upregulat", "上调", "gain"]),
    "minus": ("减少", "general", ["remove", "去除", "decrease", "减少", "downregulat", "下调", "loss", "缺失", "deplet"]),
    "question": ("未知", "general", ["unknown", "未知", "question", "问题", "uncertain", "不确定", "open problem", "why"]),
}

CATEGORIES = {
    "bio": {"zh": "生物医学", "en": "Biology & medicine"},
    "lab": {"zh": "实验室", "en": "Wet lab"},
    "sci": {"zh": "理化", "en": "Chemistry & physics"},
    "data": {"zh": "数据与计算", "en": "Data & computing"},
    "general": {"zh": "通用", "en": "General"},
}

assert set(ICONS) == set(ICON_META), sorted(set(ICONS) ^ set(ICON_META))


def icon_names() -> list[str]:
    return list(ICONS)


def match_icon(text: str, default: str | None = None) -> str | None:
    """Pick the icon whose keywords best match ``text`` (case-insensitive)."""
    if not text:
        return default
    low = text.lower().strip()
    if low in ICONS:
        return low
    best, best_score = default, 0
    for name, (_zh, _cat, kws) in ICON_META.items():
        score = 0
        for kw in kws:
            if kw in low:
                # Longer keywords are more specific, so they count for more.
                score = max(score, len(kw) + (2 if low.startswith(kw) else 0))
        if name in low:
            score = max(score, len(name) + 3)
        if score > best_score:
            best, best_score = name, score
    return best


def icon_catalog() -> dict:
    """Icon data for the web client."""
    return {
        "box": ICON_BOX,
        "icons": ICONS,
        "meta": {name: {"zh": zh, "cat": cat, "kw": kws} for name, (zh, cat, kws) in ICON_META.items()},
        "categories": CATEGORIES,
    }


def _num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def icon_stroke_units(size: float, stroke_width: float) -> float:
    """Outline width in icon units so that it is roughly ``stroke_width`` px on screen."""
    if size <= 0:
        return 2.0
    return max(1.2, min(3.6, stroke_width * ICON_BOX / size))


def role_paint(role: str, fill: str, stroke: str, accent: str, sw: float) -> dict[str, str]:
    """SVG presentation attributes for a role."""
    if role == "f":
        return {"fill": fill, "stroke": stroke, "stroke-width": _num(sw)}
    if role == "a":
        return {"fill": accent, "stroke": "none"}
    if role == "A":
        return {"fill": accent, "stroke": stroke, "stroke-width": _num(sw)}
    if role == "w":
        return {"fill": "#ffffff", "stroke": stroke, "stroke-width": _num(sw)}
    if role == "s":
        return {"fill": stroke, "stroke": "none"}
    if role == "la":
        return {"fill": "none", "stroke": accent, "stroke-width": _num(sw * 1.15)}
    return {"fill": "none", "stroke": stroke, "stroke-width": _num(sw)}


def icon_svg(name: str, x: float, y: float, size: float, fill: str, stroke: str, accent: str, stroke_width: float = 2.0) -> str:
    """Render an icon as an SVG ``<g>`` scaled into a ``size`` square at (x, y)."""
    prims = ICONS.get(name)
    if not prims:
        return ""
    scale = size / ICON_BOX
    sw = icon_stroke_units(size, stroke_width)
    parts = [f'<g transform="translate({_num(x)} {_num(y)}) scale({_num(scale)})" stroke-linecap="round" stroke-linejoin="round">']
    for prim in prims:
        kind, role = prim[0], prim[-1]
        attrs = " ".join(f'{k}="{v}"' for k, v in role_paint(role, fill, stroke, accent, sw).items())
        if kind == "c":
            parts.append(f'<circle cx="{_num(prim[1])}" cy="{_num(prim[2])}" r="{_num(prim[3])}" {attrs}/>')
        elif kind == "e":
            parts.append(f'<ellipse cx="{_num(prim[1])}" cy="{_num(prim[2])}" rx="{_num(prim[3])}" ry="{_num(prim[4])}" {attrs}/>')
        elif kind == "r":
            rx = f' rx="{_num(prim[5])}"' if prim[5] else ""
            parts.append(f'<rect x="{_num(prim[1])}" y="{_num(prim[2])}" width="{_num(prim[3])}" height="{_num(prim[4])}"{rx} {attrs}/>')
        elif kind == "p":
            pts = prim[1]
            coords = " ".join(f"{_num(pts[i])},{_num(pts[i + 1])}" for i in range(0, len(pts), 2))
            tag = "polygon" if prim[2] else "polyline"
            parts.append(f'<{tag} points="{coords}" {attrs}/>')
        elif kind == "d":
            parts.append(f'<path d="{escape(prim[1])}" {attrs}/>')
    parts.append("</g>")
    return "".join(parts)
