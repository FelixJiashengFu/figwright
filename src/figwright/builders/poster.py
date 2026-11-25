"""Academic poster: header band and sections flowed into columns (A-series portrait)."""

from __future__ import annotations

from typing import Any

from .common import Canvas, as_list, clean

WIDTH = 1000.0
MIN_HEIGHT = 1414.0  # A-series aspect ratio (1 : sqrt 2)
SIDE = 30.0
COL_GAP = 24.0
SEC_GAP = 22.0
HEAD_H = 40.0
FIG_H = 190.0


def _figure(value: Any) -> dict | None:
    """A section's figure slot: ``true`` (empty placeholder), a caption, or ``{"href", "caption"}``."""
    if value in (None, False, ""):
        return None
    if isinstance(value, dict):
        href = value.get("href") if isinstance(value.get("href"), str) else ""
        return {"href": href, "caption": clean(value.get("caption"), 200)}
    if isinstance(value, str):
        if value.startswith("data:image/") or value.startswith("http"):
            return {"href": value, "caption": ""}
        return {"href": "", "caption": clean(value, 200)}
    return {"href": "", "caption": ""}


def build_poster(content: dict, theme: str | None = None) -> dict:
    """Build from ``{"title", "authors", "affiliations", "sections": [{"heading", "body", "figure"}], "columns", "contact"}``."""
    c = Canvas(theme, "poster", clean(content.get("title"), 240))
    sections = []
    for raw in as_list(content.get("sections")):
        if not isinstance(raw, dict):
            continue
        heading = clean(raw.get("heading") or raw.get("title"), 80)
        body = clean(raw.get("body") or raw.get("text") or raw.get("content"), 2400)
        figure = _figure(raw.get("figure"))
        if heading or body or figure:
            sections.append({"heading": heading or "", "body": body, "figure": figure})
    if not sections:
        raise ValueError("The poster has no sections.")
    try:
        ncol = int(content.get("columns") or 0)
    except (TypeError, ValueError):
        ncol = 0
    if ncol not in (1, 2, 3):
        ncol = 2 if len(sections) <= 4 else 3

    title = c.scene["title"] or "Untitled poster"
    authors = clean(content.get("authors"), 300)
    affiliations = clean(content.get("affiliations") or content.get("affiliation"), 300)

    # ---- header ------------------------------------------------------------------
    tw = WIDTH - 2 * 60
    _w, title_h = c.text_size(title, tw, 34, True)
    _w, auth_h = c.text_size(authors, tw, 18) if authors else (0, 0.0)
    _w, aff_h = c.text_size(affiliations, tw, 14) if affiliations else (0, 0.0)
    header_h = 34 + title_h + (10 + auth_h if authors else 0) + (6 + aff_h if affiliations else 0) + 30
    c.add("rect", 0, 0, WIDTH, header_h, id="header", fill=c.strong(0), stroke="none", rx=0, role="header")
    y = 34.0
    c.add("text", 60, y, tw, title_h, id="title", text=title, fontSize=34, fontWeight="bold", color="#ffffff", valign="top", role="title")
    y += title_h
    if authors:
        y += 10
        c.add("text", 60, y, tw, auth_h, id="authors", text=authors, fontSize=18, color="#ffffff", valign="top")
        y += auth_h
    if affiliations:
        y += 6
        c.add("text", 60, y, tw, aff_h, id="affiliations", text=affiliations, fontSize=14, color="#ffffff", opacity=0.85, valign="top")

    # ---- sections ------------------------------------------------------------------
    col_w = (WIDTH - 2 * SIDE - (ncol - 1) * COL_GAP) / ncol
    body_top = header_h + 30
    avail = MIN_HEIGHT - body_top - 70

    def flow(fs_body: float) -> tuple[list[list[dict]], float]:
        """Measure every section at this font size and pour them into columns."""
        for s in sections:
            _w, s["body_h"] = c.text_size(s["body"], col_w - 32, fs_body) if s["body"] else (0, 0.0)
            s["fig_h"] = FIG_H if s["figure"] is not None else 0.0
            s["h"] = HEAD_H + 12 + s["body_h"] + (s["fig_h"] + 12 if s["fig_h"] else 0) + 18
        total = sum(s["h"] for s in sections) + SEC_GAP * (len(sections) - 1)
        target = total / ncol
        cols: list[list[dict]] = [[] for _ in range(ncol)]
        ci, run = 0, 0.0
        for idx, s in enumerate(sections):
            remaining_cols = ncol - ci - 1
            remaining_secs = len(sections) - idx
            # Move on once the column is full enough, but never strand later columns empty-handed.
            if cols[ci] and remaining_cols > 0 and (run + s["h"] / 2 > target or remaining_secs <= remaining_cols):
                ci += 1
                run = 0.0
            cols[ci].append(s)
            run += s["h"] + SEC_GAP
        tallest = max(sum(s["h"] for s in col) + SEC_GAP * max(0, len(col) - 1) for col in cols)
        return cols, tallest

    # Use the largest body size (up to 21 px) that still fits one A-series page.
    fs_body = 21.0
    columns, tallest = flow(fs_body)
    while tallest > avail and fs_body > 14.0:
        fs_body -= 1.0
        columns, tallest = flow(fs_body)
    column_h = max(tallest, min(avail, tallest * 1.6))

    k = 0
    for ci, col in enumerate(columns):
        x = SIDE + ci * (col_w + COL_GAP)
        y = body_top
        used = sum(s["h"] for s in col) + SEC_GAP * max(0, len(col) - 1)
        # Spread the slack so that every column ends on the same line; figures get most of it.
        slack = max(0.0, column_h - used)
        figs = sum(1 for s in col if s["fig_h"])
        for s in col:
            extra = (slack / figs if s["fig_h"] else 0.0) if figs else slack / max(1, len(col))
            h = s["h"] + extra
            g = f"sec{k + 1}"
            c.add("rect", x, y, col_w, h, id=g, fill="#ffffff", stroke=c.soft(k), strokeWidth=2, rx=10, group=g, role="section")
            c.add("rect", x, y, col_w, HEAD_H, fill=c.soft(k), stroke="none", rx=10, text=s["heading"], fontSize=18, fontWeight="bold", align="left", color=c.ink, group=g)
            cy = y + HEAD_H + 12
            if s["body"]:
                c.add("text", x + 16, cy, col_w - 32, s["body_h"], text=s["body"], fontSize=fs_body, align="left", valign="top", group=g)
                cy += s["body_h"] + 12
            if s["fig_h"]:
                fh = s["fig_h"] + extra
                fig = s["figure"]
                cap_h = 0.0
                if fig["caption"]:
                    cap_h = c.text_size(fig["caption"], col_w - 32, 13)[1] + 6
                c.add("image", x + 16, cy, col_w - 32, max(40.0, fh - cap_h), href=fig["href"], name=fig["caption"] or s["heading"], group=g, role="figure")
                if fig["caption"]:
                    c.add("text", x + 16, cy + fh - cap_h + 4, col_w - 32, cap_h - 4, text=fig["caption"], fontSize=13, color=c.muted, valign="top", group=g)
            y += h + SEC_GAP
            k += 1

    height = max(MIN_HEIGHT, body_top + column_h + 70)
    contact = clean(content.get("contact"), 200)
    c.add("rect", SIDE, height - 46, WIDTH - 2 * SIDE, 2, fill=c.soft(0), stroke="none", rx=0, role="rule")
    if contact:
        c.add("text", SIDE, height - 38, WIDTH - 2 * SIDE, 22, id="contact", text=contact, fontSize=13, color=c.muted)
    return c.finish(WIDTH, height)
