"""PRISMA 2020 flow diagram for systematic reviews.

The box structure and wording follow the PRISMA 2020 flow diagram for new
systematic reviews that searched databases and registers (Page MJ et al.,
"The PRISMA 2020 statement", BMJ 2021;372:n71, CC BY 4.0). The Chinese labels
are our own translation.

Besides drawing, :func:`prisma_check` does the arithmetic reviewers do by hand:
it fills in numbers that follow from the others and reports any that do not add up.
"""

from __future__ import annotations

from typing import Any

from ..text import text_width
from .common import MARGIN, Canvas, as_list, clean, has_cjk

BOX_W = 310.0
COL_GAP = 64.0
ROW_GAP = 34.0
PHASE_W = 30.0
PHASE_GAP = 16.0

_T = {
    "en": {
        "identification": "Identification",
        "screening": "Screening",
        "included": "Included",
        "identified": "Records identified from:",
        "databases": "Databases",
        "registers": "Registers",
        "removed": "Records removed before screening:",
        "duplicates": "Duplicate records removed",
        "automation": "Records marked as ineligible by automation tools",
        "other_removed": "Records removed for other reasons",
        "screened": "Records screened",
        "excluded": "Records excluded",
        "sought": "Reports sought for retrieval",
        "not_retrieved": "Reports not retrieved",
        "assessed": "Reports assessed for eligibility",
        "excluded_reports": "Reports excluded:",
        "included_studies": "Studies included in review",
        "included_reports": "Reports of included studies",
        "n": "(n = {})",
    },
    "zh": {
        "identification": "识别",
        "screening": "筛选",
        "included": "纳入",
        "identified": "检索获得的记录：",
        "databases": "数据库",
        "registers": "注册库",
        "removed": "筛选前剔除的记录：",
        "duplicates": "重复记录",
        "automation": "自动化工具判定为不合格的记录",
        "other_removed": "因其他原因剔除的记录",
        "screened": "筛选的记录",
        "excluded": "排除的记录",
        "sought": "尝试获取全文的报告",
        "not_retrieved": "未能获取的报告",
        "assessed": "评估是否合格的报告",
        "excluded_reports": "排除的报告：",
        "included_studies": "纳入综述的研究",
        "included_reports": "纳入研究的报告",
        "n": "（n = {}）",
    },
}


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value == value and value >= 0 else None
    if isinstance(value, str):
        digits = value.replace(",", "").replace(" ", "").replace("，", "")
        if digits.isdigit():
            return int(digits)
    return None


def _pairs(value: Any, name_keys: tuple[str, ...]) -> list[tuple[str, int | None]]:
    out: list[tuple[str, int | None]] = []
    if isinstance(value, dict):
        value = [{"name": k, "n": v} for k, v in value.items()]
    for raw in as_list(value):
        if isinstance(raw, dict):
            name = ""
            for k in name_keys:
                if raw.get(k):
                    name = clean(raw[k], 80)
                    break
            n = _int(raw.get("n", raw.get("count", raw.get("value"))))
            if name:
                out.append((name, n))
        elif isinstance(raw, str) and raw.strip():
            out.append((clean(raw, 80), None))
    return out[:12]


def prisma_check(content: dict) -> tuple[dict, list[str]]:
    """Return ``(numbers, warnings)``: derived values filled in, inconsistencies listed."""
    d: dict[str, Any] = {}
    for key in ("databases", "registers", "duplicates", "automation", "other_removed", "screened", "excluded", "sought", "not_retrieved", "assessed", "included_studies", "included_reports"):
        d[key] = _int(content.get(key))
    if d["included_studies"] is None:
        d["included_studies"] = _int(content.get("included"))
    d["sources"] = _pairs(content.get("identified") or content.get("sources"), ("name", "source", "database"))
    d["reasons"] = _pairs(content.get("excluded_reports") or content.get("reasons"), ("reason", "name"))
    warnings: list[str] = []

    if d["sources"]:
        identified = sum(n for _name, n in d["sources"] if n is not None) if all(n is not None for _name, n in d["sources"]) else None
    elif d["databases"] is not None or d["registers"] is not None:
        identified = (d["databases"] or 0) + (d["registers"] or 0)
    else:
        identified = _int(content.get("identified_total"))
    d["identified_total"] = identified
    removed_parts = [d["duplicates"], d["automation"], d["other_removed"]]
    removed = sum(v or 0 for v in removed_parts) if any(v is not None for v in removed_parts) else None
    d["removed_total"] = removed
    reasons_total = sum(n for _r, n in d["reasons"] if n is not None) if d["reasons"] and all(n is not None for _r, n in d["reasons"]) else _int(content.get("excluded_reports_total"))
    d["reasons_total"] = reasons_total

    def derive(key: str, a: int | None, b: int | None, what: str) -> None:
        if a is None or b is None:
            return
        expect = a - b
        if d[key] is None:
            if expect >= 0:
                d[key] = expect
            else:
                warnings.append(f"{what}: {a} - {b} is negative; check the numbers.")
        elif d[key] != expect:
            warnings.append(f"{what}: expected {a} - {b} = {expect}, but {d[key]} was given.")

    derive("screened", identified, removed if removed is not None else (0 if identified is not None and d["screened"] is None else None), "Records screened")
    derive("sought", d["screened"], d["excluded"], "Reports sought for retrieval")
    derive("assessed", d["sought"], d["not_retrieved"] if d["not_retrieved"] is not None else (0 if d["assessed"] is None and d["sought"] is not None else None), "Reports assessed for eligibility")
    if d["assessed"] is not None and reasons_total is not None:
        expect = d["assessed"] - reasons_total
        if d["included_reports"] is not None:
            if d["included_reports"] != expect:
                warnings.append(f"Reports of included studies: expected {d['assessed']} - {reasons_total} = {expect}, but {d['included_reports']} was given.")
        elif d["included_studies"] is None:
            if expect >= 0:
                d["included_studies"] = expect
            else:
                warnings.append(f"Included: {d['assessed']} - {reasons_total} is negative; check the numbers.")
        elif d["included_studies"] != expect:
            if d["included_studies"] < expect:
                d["included_reports"] = expect  # several reports can describe one study
            else:
                warnings.append(f"Studies included: {d['included_studies']} is more than the {expect} reports left after exclusions.")
    return d, warnings


def _fmt(n: int | None) -> str:
    return "?" if n is None else f"{n:,}"


def build_prisma(content: dict, theme: str | None = None) -> dict:
    """Build a PRISMA 2020 flow diagram. See :func:`prisma_check` for the accepted numbers."""
    d, warnings = prisma_check(content)
    lang = str(content.get("lang") or "").lower()
    title = clean(content.get("title"), 160)
    if lang not in ("zh", "en"):
        lang = "zh" if has_cjk(title, *(name for name, _n in d["sources"] + d["reasons"])) else "en"
    T = _T[lang]
    c = Canvas(theme, "prisma", title)
    fs = 14.0

    def n(v: int | None) -> str:
        return T["n"].format(_fmt(v))

    def line(label: str, v: int | None) -> str:
        return f"{label} {n(v)}"

    if d["sources"]:
        src_lines = [line(name, v) for name, v in d["sources"]]
    elif d["databases"] is None and d["registers"] is None and d["identified_total"] is not None:
        # Only the total is known: say that, rather than two boxes of "?".
        src_lines = [n(d["identified_total"])]
    else:
        src_lines = [line(T["databases"], d["databases"]), line(T["registers"], d["registers"])]
    removed_lines = [line(T["duplicates"], d["duplicates"]), line(T["automation"], d["automation"]), line(T["other_removed"], d["other_removed"])]
    reason_lines = [line(name, v) for name, v in d["reasons"]] or [n(d["reasons_total"])]
    included = f"{T['included_studies']}\n{n(d['included_studies'])}"
    if d["included_reports"] is not None:
        included += f"\n{T['included_reports']}\n{n(d['included_reports'])}"

    rows: list[tuple[str, str, str, str | None, str]] = [
        # (phase, id, left text, right text, right alignment)
        ("identification", "identified", T["identified"] + "\n" + "\n".join(src_lines), T["removed"] + "\n" + "\n".join(removed_lines), "left"),
        ("screening", "screened", f"{T['screened']}\n{n(d['screened'])}", f"{T['excluded']}\n{n(d['excluded'])}", "center"),
        ("screening", "sought", f"{T['sought']}\n{n(d['sought'])}", f"{T['not_retrieved']}\n{n(d['not_retrieved'])}", "center"),
        ("screening", "assessed", f"{T['assessed']}\n{n(d['assessed'])}", T["excluded_reports"] + "\n" + "\n".join(reason_lines), "left"),
        ("included", "included", included, None, "center"),
    ]

    width = 2 * MARGIN + PHASE_W + PHASE_GAP + 2 * BOX_W + COL_GAP
    top = c.title(title, width, fs=22) if title else MARGIN
    x_left = MARGIN + PHASE_W + PHASE_GAP
    x_right = x_left + BOX_W + COL_GAP
    inner = BOX_W - 24

    y = top
    spans: dict[str, list[float]] = {}
    for i, (phase, rid, left, right, ralign) in enumerate(rows):
        lh = c.text_size(left, inner, fs)[1] + 24
        rh = c.text_size(right, inner, fs)[1] + 24 if right else 0.0
        h = max(lh, rh, 58.0)
        lalign = "left" if (i == 0) else "center"
        c.add("rect", x_left, y + (h - lh) / 2, BOX_W, lh, id=rid, text=left, fontSize=fs, align=lalign, fill="#ffffff", stroke=c.line, strokeWidth=1.5, rx=4, role="prisma-box")
        if right:
            c.add("rect", x_right, y + (h - rh) / 2, BOX_W, rh, id=f"{rid}_out", text=right, fontSize=fs, align=ralign, fill="#ffffff", stroke=c.line, strokeWidth=1.5, rx=4, role="prisma-side")
            c.edge(rid, f"{rid}_out", fromSide="right", toSide="left", width=1.5)
        spans.setdefault(phase, [y, y + h])[1] = y + h
        y += h + ROW_GAP
    for a, b in zip(rows, rows[1:]):
        c.edge(a[1], b[1], fromSide="bottom", toSide="top", width=1.5)

    # Rotated phase labels down the left edge.
    for k, phase in enumerate(("identification", "screening", "included")):
        y0, y1 = spans[phase]
        length = y1 - y0
        cx, cy = MARGIN + PHASE_W / 2, (y0 + y1) / 2
        # A short phase (one row of boxes) needs a smaller label, or the word would wrap.
        label_fs = max(8.0, min(float(fs), (length - 24) / max(0.1, text_width(T[phase], 1.0, True))))
        c.add("rect", cx - length / 2, cy - PHASE_W / 2, length, PHASE_W, id=f"phase_{phase}", text=T[phase], rotation=-90, fill=c.soft(0), stroke=c.strong(0), strokeWidth=1.5, rx=8, fontSize=round(label_fs, 1), fontWeight="bold", role="phase")

    scene = c.finish(width, y - ROW_GAP + MARGIN)
    if warnings:
        scene["meta"]["warnings"] = warnings
    return scene
