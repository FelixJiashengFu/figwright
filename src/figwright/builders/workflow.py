"""Experimental workflow: a row (or serpentine) of numbered icon cards."""

from __future__ import annotations

import math

from .common import MARGIN, Canvas, as_list, clean, pick_icon

CARD_W = 190.0
ICON = 64.0
GAP_X = 58.0
GAP_Y = 62.0
MAX_STEPS = 12


def _per_row(n: int) -> int:
    if n <= 5:
        return n
    if n <= 8:
        return math.ceil(n / 2)
    return 4


def build_workflow(content: dict, theme: str | None = None) -> dict:
    """Build from ``{"title": ..., "steps": [{"title", "detail", "icon"}]}``."""
    c = Canvas(theme, "workflow", clean(content.get("title"), 160))
    steps = []
    for raw in as_list(content.get("steps"))[:MAX_STEPS]:
        if not isinstance(raw, dict):
            raw = {"title": raw}
        title = clean(raw.get("title") or raw.get("name") or raw.get("text"), 80)
        detail = clean(raw.get("detail") or raw.get("description"), 160)
        if not title:
            continue
        steps.append({"title": title, "detail": detail, "icon": pick_icon(raw.get("icon"), f"{title} {detail}")})
    if not steps:
        raise ValueError("The workflow has no steps.")

    fs = float(c.style["fontSize"])
    fs_detail = 13.0
    inner = CARD_W - 24
    title_h = max(c.text_size(s["title"], inner, fs, True)[1] for s in steps)
    detail_h = max((c.text_size(s["detail"], inner, fs_detail)[1] for s in steps if s["detail"]), default=0.0)
    card_h = 18 + ICON + 12 + title_h + ((6 + detail_h) if detail_h else 0) + 16

    n = len(steps)
    per_row = _per_row(n)
    rows = math.ceil(n / per_row)
    width = 2 * MARGIN + per_row * CARD_W + (per_row - 1) * GAP_X
    width = max(width, 460.0 if c.scene["title"] else 0.0)
    top = c.title(c.scene["title"], width) if c.scene["title"] else MARGIN
    left = (width - (per_row * CARD_W + (per_row - 1) * GAP_X)) / 2.0

    for i, s in enumerate(steps):
        r, col = divmod(i, per_row)
        if r % 2 == 1:
            col = per_row - 1 - col
        x = left + col * (CARD_W + GAP_X)
        y = top + r * (card_h + GAP_Y)
        k = i
        g = f"s{i + 1}"
        c.add("rect", x, y, CARD_W, card_h, id=g, fill="#ffffff", stroke=c.strong(k), rx=14, group=g, role="card")
        c.add("icon", x + (CARD_W - ICON) / 2, y + 18, ICON, ICON, icon=s["icon"], fill=c.soft(k), accent=c.strong(k), group=g)
        c.add("ellipse", x + 10, y + 10, 28, 28, fill=c.strong(k), stroke="none", text=str(i + 1), color="#ffffff", fontWeight="bold", fontSize=14, group=g)
        ty = y + 18 + ICON + 12
        c.add("text", x + 12, ty, inner, title_h, text=s["title"], fontWeight="bold", valign="top", group=g)
        if s["detail"]:
            c.add("text", x + 12, ty + title_h + 6, inner, detail_h, text=s["detail"], fontSize=fs_detail, color=c.muted, valign="top", group=g)

    for i in range(n - 1):
        same_row = i // per_row == (i + 1) // per_row
        props = {"width": 2.5}
        if not same_row:
            props.update(routing="elbow", fromSide="bottom", toSide="top")
        c.edge(f"s{i + 1}", f"s{i + 2}", **props)

    height = top + rows * card_h + (rows - 1) * GAP_Y + MARGIN
    return c.finish(width, height)
