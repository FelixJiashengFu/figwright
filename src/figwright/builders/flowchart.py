"""Flowchart: semantic nodes and edges in, tidy layered diagram out."""

from __future__ import annotations

from typing import Any

from ..layout import layered_layout
from .common import MARGIN, Canvas, as_list, clean, slug

# kind -> (node type, soft colour slot)
KINDS = {
    "start": ("pill", 2),
    "end": ("pill", 1),
    "process": ("rect", 0),
    "subprocess": ("rect", 4),
    "decision": ("diamond", 5),
    "io": ("parallelogram", 3),
    "data": ("cylinder", 3),
    "note": ("rect", -1),
}
LOOP_ROOM = 100.0  # space reserved beside the diagram for loop-back connectors

_KIND_ALIASES = {
    "terminator": "start",
    "begin": "start",
    "stop": "end",
    "finish": "end",
    "action": "process",
    "step": "process",
    "task": "process",
    "rect": "process",
    "condition": "decision",
    "branch": "decision",
    "diamond": "decision",
    "input": "io",
    "output": "io",
    "database": "data",
    "storage": "data",
    "comment": "note",
}


def _node_size(c: Canvas, kind: str, text: str, fs: float) -> tuple[float, float]:
    if kind == "decision":
        tw, th = c.text_size(text, 150, fs)
        return max(150.0, min(300.0, tw / 0.6 + 16)), max(84.0, th / 0.6 + 14)
    if kind in ("start", "end"):
        tw, th = c.text_size(text, 200, fs)
        return max(120.0, tw + 60), max(46.0, th + 22)
    if kind == "io":
        tw, th = c.text_size(text, 200, fs)
        return max(150.0, tw + 80), max(54.0, th + 26)
    if kind == "data":
        tw, th = c.text_size(text, 180, fs)
        return max(130.0, tw + 40), max(78.0, th + 60)
    tw, th = c.text_size(text, 210, fs)
    return max(140.0, tw + 44), max(54.0, th + 28)


def build_flowchart(content: dict, theme: str | None = None) -> dict:
    """Build a flowchart scene from ``{"nodes": [...], "edges": [...], "direction": "TB"}``."""
    direction = str(content.get("direction") or "TB").upper()
    if direction not in ("TB", "LR"):
        direction = "TB"
    c = Canvas(theme, "flowchart", clean(content.get("title"), 160))
    fs = float(c.style["fontSize"])

    specs: list[dict] = []
    used: set[str] = set()
    alias: dict[str, str] = {}
    for i, raw in enumerate(as_list(content.get("nodes"))):
        if not isinstance(raw, dict):
            raw = {"text": raw}
        text = clean(raw.get("text") or raw.get("label") or raw.get("title"), 240)
        if not text:
            continue
        kind = str(raw.get("kind") or raw.get("type") or "process").strip().lower()
        kind = _KIND_ALIASES.get(kind, kind)
        if kind not in KINDS:
            kind = "process"
        orig = str(raw.get("id") if raw.get("id") is not None else f"n{i + 1}")
        nid = slug(orig, f"n{i + 1}")
        while nid in used:
            nid += "_"
        used.add(nid)
        alias[orig] = nid
        w, h = _node_size(c, kind, text, fs)
        specs.append({"id": nid, "text": text, "kind": kind, "w": w, "h": h})
    if not specs:
        raise ValueError("The flowchart has no nodes.")
    specs_by_id = {s["id"]: s for s in specs}

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in as_list(content.get("edges")):
        if not isinstance(raw, dict):
            continue
        a = alias.get(str(raw.get("from", raw.get("source"))))
        b = alias.get(str(raw.get("to", raw.get("target"))))
        if not a or not b or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        edges.append({"from": a, "to": b, "label": clean(raw.get("label") or raw.get("text"), 60), "dash": bool(raw.get("dash"))})

    lay = layered_layout(specs, [(e["from"], e["to"]) for e in edges], direction=direction, layer_gap=62 if direction == "TB" else 84, node_gap=44 if direction == "TB" else 30)
    tb = direction == "TB"

    # Decide how each connector travels. Loop-backs go around the outside, so
    # reserve room on the side(s) they use.
    cross_mid = lay["size"][0 if tb else 1] / 2.0
    routes: list[dict[str, Any]] = []
    room = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    def outside(nid: str) -> str:
        """Which flank of the diagram this node sits closest to."""
        pos, spec = lay["pos"][nid], specs_by_id[nid]
        centre = (pos[0] + spec["w"] / 2.0) if tb else (pos[1] + spec["h"] / 2.0)
        if tb:
            return "right" if centre >= cross_mid else "left"
        return "bottom" if centre >= cross_mid else "top"

    occupied: dict[int, list[tuple[float, float]]] = {}
    for nid, rank in lay["rank"].items():
        pos, spec = lay["pos"][nid], specs_by_id[nid]
        lo, hi = (pos[0], pos[0] + spec["w"]) if tb else (pos[1], pos[1] + spec["h"])
        occupied.setdefault(rank, []).append((lo, hi))

    for e in edges:
        ra, rb = lay["rank"][e["from"]], lay["rank"][e["to"]]
        props: dict[str, Any] = {"label": e["label"], "dash": e["dash"]}
        if rb > ra:
            props["routing"] = "elbow"
            props["fromSide"], props["toSide"] = ("bottom", "top") if tb else ("right", "left")
            if rb - ra > 1:
                # A connector that skips a rank would run straight over whatever sits
                # in between, so send it out of the side and back in.
                pa, pb = lay["pos"][e["from"]], lay["pos"][e["to"]]
                sa, sb = specs_by_id[e["from"]], specs_by_id[e["to"]]
                lo = min(pa[0], pb[0]) if tb else min(pa[1], pb[1])
                hi = max(pa[0] + sa["w"], pb[0] + sb["w"]) if tb else max(pa[1] + sa["h"], pb[1] + sb["h"])
                blocked = any(b_hi > lo and b_lo < hi for r in range(ra + 1, rb) for b_lo, b_hi in occupied.get(r, []))
                if blocked:
                    side = outside(e["from"])
                    props["fromSide"] = props["toSide"] = side
                    room[side] = max(room[side], LOOP_ROOM)
        elif rb < ra:
            side = outside(e["from"])
            props["routing"] = "curve"
            props["fromSide"] = props["toSide"] = side
            room[side] = LOOP_ROOM
        routes.append(props)

    inner_w = lay["size"][0] + room["left"] + room["right"]
    width = max(inner_w + 2 * MARGIN, 440.0 if c.scene["title"] else 0.0)
    top = (c.title(c.scene["title"], width) if c.scene["title"] else MARGIN) + room["top"]
    off_x = (width - inner_w) / 2.0 + room["left"]

    for s in specs:
        ntype, slot = KINDS[s["kind"]]
        x, y = lay["pos"][s["id"]]
        node_props: dict[str, Any] = {"text": s["text"], "role": s["kind"]}
        if slot < 0:
            node_props.update(fill=c.panel, stroke=c.muted, dash=True, strokeWidth=1.5)
        else:
            node_props.update(fill=c.soft(slot), stroke=c.strong(slot))
        if s["kind"] in ("start", "end"):
            node_props["fontWeight"] = "bold"
        c.add(ntype, x + off_x, y + top, s["w"], s["h"], id=s["id"], **node_props)

    for e, props in zip(edges, routes):
        c.edge(e["from"], e["to"], **props)

    return c.finish(width, top + lay["size"][1] + room["bottom"] + MARGIN)
