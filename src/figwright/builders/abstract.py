"""Graphical abstract: a title, two to four illustrated panels and a take-home banner."""

from __future__ import annotations

from .common import MARGIN, Canvas, as_list, clean, pick_icon

WIDTH = 1200.0
GAP = 66.0
ICON = 108.0


def build_abstract(content: dict, theme: str | None = None) -> dict:
    """Build from ``{"title", "panels": [{"heading", "icon", "bullets"}], "takeaway"}``."""
    c = Canvas(theme, "abstract", clean(content.get("title"), 200))
    panels = []
    for raw in as_list(content.get("panels"))[:4]:
        if not isinstance(raw, dict):
            continue
        heading = clean(raw.get("heading") or raw.get("title"), 60)
        bullets = [clean(b, 110) for b in as_list(raw.get("bullets") or raw.get("points") or raw.get("text"))][:4]
        bullets = [b for b in bullets if b]
        if not heading and not bullets:
            continue
        panels.append({"heading": heading, "bullets": bullets, "icon": pick_icon(raw.get("icon"), f"{heading} {' '.join(bullets)}", default="lightbulb")})
    if not panels:
        raise ValueError("The graphical abstract has no panels.")

    n = len(panels)
    fs = float(c.style["fontSize"])
    pw = (WIDTH - 2 * MARGIN - (n - 1) * GAP) / n
    inner = pw - 36
    top = c.title(c.scene["title"], WIDTH, fs=26) if c.scene["title"] else MARGIN

    head_h = max((c.text_size(p["heading"], inner, 19, True)[1] for p in panels if p["heading"]), default=0.0)
    bullet_texts = ["\n".join(f"• {b}" for b in p["bullets"]) for p in panels]
    body_h = max((c.text_size(t, inner, fs - 1)[1] for t in bullet_texts if t), default=0.0)
    card_h = 22 + head_h + 14 + ICON + 16 + body_h + 24

    for i, p in enumerate(panels):
        x = MARGIN + i * (pw + GAP)
        g = f"p{i + 1}"
        c.add("rect", x, top, pw, card_h, id=g, fill=c.soft(i), stroke="none", rx=20, group=g, role="panel")
        y = top + 22
        if p["heading"]:
            c.add("text", x + 18, y, inner, head_h, text=p["heading"], fontSize=19, fontWeight="bold", color=c.ink, valign="top", group=g)
        y += head_h + 14
        c.add("icon", x + (pw - ICON) / 2, y, ICON, ICON, icon=p["icon"], fill="#ffffff", accent=c.strong(i), group=g)
        y += ICON + 16
        if bullet_texts[i]:
            c.add("text", x + 18, y, inner, body_h, text=bullet_texts[i], fontSize=fs - 1, align="left", valign="top", color=c.ink, group=g)
    for i in range(n - 1):
        c.edge(f"p{i + 1}", f"p{i + 2}", width=4, color=c.muted)

    y = top + card_h + 26
    takeaway = clean(content.get("takeaway") or content.get("conclusion"), 260)
    if takeaway:
        _tw, th = c.text_size(takeaway, WIDTH - 2 * MARGIN - 60, 18, True)
        c.add("rect", MARGIN, y, WIDTH - 2 * MARGIN, th + 30, id="takeaway", fill=c.strong(0), stroke="none", rx=14, text=takeaway, color="#ffffff", fontSize=18, fontWeight="bold", role="takeaway")
        y += th + 30 + 10
    return c.finish(WIDTH, y + MARGIN - 10)
