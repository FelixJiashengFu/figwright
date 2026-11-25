"""Data plots: a table and a declarative spec in, a publication-style chart out.

The spec is plain data (chart kind, which columns go where, a few options). A
model may write the spec, but no model-written code is ever executed: the
drawing is done by the fixed routines below with Matplotlib.

Statistics follow common practice for small-sample lab data: Welch's t-test or
Mann-Whitney U for two groups, one-way ANOVA with Tukey HSD or Kruskal-Wallis
with Holm-corrected Mann-Whitney tests for more, and every data point is drawn
whenever the groups are small enough to show them.
"""

from __future__ import annotations

import io
import math
import threading
from typing import Any

from .themes import get_theme

KINDS = ("bar", "line", "scatter", "box", "violin", "hist", "heatmap", "pie", "volcano")
ERRORS = ("sd", "sem", "ci95")
PALETTES = ("theme", "okabe", "viridis", "mono")
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 200_000
MAX_COLS = 200

_LOCK = threading.Lock()
_READY = False
_FONTS = ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei", "SimHei"]
_OKABE = ["#0072b2", "#e69f00", "#009e73", "#cc79a7", "#56b4e9", "#d55e00", "#f0e442", "#000000"]
_MONO = ["#1f2937", "#6b7280", "#9ca3af", "#374151", "#d1d5db", "#111827"]


class PlotError(ValueError):
    """The table or the spec cannot be plotted; the message is for the user."""


def _setup() -> None:
    global _READY
    if _READY:
        return
    import logging

    import matplotlib

    matplotlib.use("Agg", force=False)
    # A missing weight of a CJK font is substituted silently; the warning is only noise for users.
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    family = [f for f in _FONTS if f in have] or ["DejaVu Sans"]
    matplotlib.rcParams.update(
        {
            "svg.fonttype": "none",  # keep text as text in SVG so it stays editable
            "font.family": family,
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
        }
    )
    _READY = True


# ----------------------------------------------------------------------------- data
def load_table(filename: str, data: bytes, sheet: str | int | None = None):
    """Read CSV / TSV / Excel / JSON into a DataFrame."""
    import pandas as pd

    if len(data) > MAX_BYTES:
        raise PlotError("The table is larger than 20 MB. Plot a summary or a subset instead.")
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(io.BytesIO(data), sheet_name=sheet if sheet not in (None, "") else 0, engine="openpyxl")
        elif name.endswith(".xls"):
            raise PlotError("Old .xls files are not supported; save the workbook as .xlsx or CSV.")
        elif name.endswith(".json"):
            df = pd.read_json(io.BytesIO(data))
        else:
            df = parse_text_table(decode_text(data))
    except PlotError:
        raise
    except Exception as exc:  # noqa: BLE001 - pandas raises many types for malformed files
        raise PlotError(f"The table could not be read ({type(exc).__name__}: {str(exc)[:160]}).") from exc
    return _clean(df)


def sheet_names(filename: str, data: bytes) -> list[str]:
    """Worksheet names of an Excel workbook (empty for other files)."""
    if not (filename or "").lower().endswith((".xlsx", ".xlsm")) or len(data) > MAX_BYTES:
        return []
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True)
        try:
            return [str(n) for n in wb.sheetnames][:50]
        finally:
            wb.close()
    except Exception:  # noqa: BLE001 - a broken workbook is reported by load_table
        return []


def table_csv(df) -> str:
    """The cleaned table as CSV text (what the browser keeps and sends back for each redraw)."""
    return df.to_csv(index=False)


def decode_text(data: bytes) -> str:
    """Decode a text file: UTF-16 only with a byte-order mark, then UTF-8, then GB18030 (Chinese Excel exports)."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse_text_table(text: str):
    """Parse pasted text: CSV, TSV, semicolon-separated or a Markdown table."""
    import pandas as pd

    text = (text or "").strip()
    if not text:
        raise PlotError("The table is empty.")
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("|"):
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if ln.strip() and not set(ln.strip()) <= set("|-: ")]
        if len(rows) < 2:
            raise PlotError("The table has no data rows.")
        width = len(rows[0])
        return pd.DataFrame([r[:width] + [""] * (width - len(r)) for r in rows[1:]], columns=rows[0])
    head = lines[0]
    sep = max(("\t", ",", ";"), key=lambda s: head.count(s))
    if head.count(sep) == 0:
        sep = r"\s+" if len(head.split()) > 1 else ","
    try:
        return pd.read_csv(io.StringIO(text), sep=sep, engine="python")
    except Exception as exc:  # noqa: BLE001
        raise PlotError(f"The table could not be read ({str(exc)[:160]}).") from exc


def _clean(df):
    import pandas as pd

    if df is None or df.empty or df.shape[1] == 0:
        raise PlotError("The table has no data rows.")
    if df.shape[0] > MAX_ROWS or df.shape[1] > MAX_COLS:
        raise PlotError(f"The table has {df.shape[0]:,} rows and {df.shape[1]} columns; the limit is {MAX_ROWS:,} rows and {MAX_COLS} columns.")
    df = df.copy()
    names: list[str] = []
    for i, c in enumerate(df.columns):
        name = str(c).strip() or f"column{i + 1}"
        if name.startswith("Unnamed:"):
            name = f"column{i + 1}"
        base, k = name, 2
        while name in names:
            name = f"{base}_{k}"
            k += 1
        names.append(name)
    df.columns = names
    df = df.dropna(how="all")
    for c in df.columns:
        if pd.api.types.is_bool_dtype(df[c]):
            df[c] = df[c].map({True: "yes", False: "no"}).astype(object)
        elif pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d").astype(object)
        elif not pd.api.types.is_numeric_dtype(df[c]):
            # Text column: numbers typed with thousands separators or a percent sign still count as numbers.
            present = df[c].notna()
            as_text = df[c].astype(object).where(present, "").astype(str).str.strip()
            filled = present & (as_text != "")
            num = pd.to_numeric(as_text.str.replace(",", "", regex=False).str.rstrip("%"), errors="coerce")
            if filled.sum() and num[filled].notna().mean() >= 0.9:
                df[c] = num.where(filled).astype(float)
            else:
                df[c] = as_text.where(filled, None).astype(object)
    return df.reset_index(drop=True)


def is_number(series) -> bool:
    import pandas as pd

    return bool(pd.api.types.is_numeric_dtype(series)) and not bool(pd.api.types.is_bool_dtype(series))


def describe(df) -> list[dict]:
    """Column summary for the UI and for the spec-writing model (a few example values, never the whole table)."""
    out = []
    for c in df.columns:
        s = df[c].dropna()
        examples = [(round(float(v), 4) if is_number(df[c]) else str(v)[:40]) for v in s.head(4).tolist()]
        out.append({"name": c, "type": "number" if is_number(df[c]) else "text", "unique": int(s.nunique()), "rows": int(len(s)), "examples": examples})
    return out


def normalize_spec(spec: Any, df) -> dict:
    """Validate a spec against the table and fill in defaults."""
    if not isinstance(spec, dict):
        raise PlotError("The chart description must be a JSON object.")
    cols = list(df.columns)
    lower = {c.lower(): c for c in cols}
    # A column name that is not in the table is replaced by a sensible default, so
    # that a near-miss still draws something. It is remembered here and reported as
    # a note: silently charting a different column is how a figure tells a lie.
    unknown: list[str] = []

    def col(value: Any) -> str | None:
        if value is None or value == "":
            return None
        v = str(value)
        if v in cols:
            return v
        found = lower.get(v.lower().strip())
        if found is None and v.strip() and v not in unknown:
            unknown.append(v)
        return found

    kind = str(spec.get("kind") or spec.get("type") or "bar").lower().strip()
    kind = {"boxplot": "box", "histogram": "hist", "column": "bar", "donut": "pie", "violinplot": "violin", "point": "scatter", "heat": "heatmap"}.get(kind, kind)
    if kind not in KINDS:
        raise PlotError(f"Unknown chart kind {kind!r}. Available: {', '.join(KINDS)}.")
    ys_raw = spec.get("y")
    if isinstance(ys_raw, str):
        ys_raw = [ys_raw]
    ys = []
    for v in ys_raw or []:
        c = col(v)
        if c and c not in ys:
            ys.append(c)
    numeric = [c for c in cols if is_number(df[c])]
    text = [c for c in cols if c not in numeric]
    # When the spec does not name a y column, prefer a measurement over a design
    # column: "dose" holding one repeated value is a label, not the thing measured.
    measured = sorted(numeric, key=lambda c: -int(df[c].nunique(dropna=True)))
    # A column holding one repeated value says nothing when charted, so it stays
    # out of the automatic pick unless it is the only numeric column there is.
    varying = [c for c in measured if int(df[c].nunique(dropna=True)) > 1] or measured
    x = col(spec.get("x"))
    group = col(spec.get("group") or spec.get("hue") or spec.get("color"))
    label = col(spec.get("label"))

    if kind in ("bar", "box", "violin", "pie"):
        x = x or (text[0] if text else None)
        ys = [c for c in ys if c in numeric] or [c for c in varying if c != x][: (1 if kind != "bar" else 4)]
        if kind != "bar":
            ys = ys[:1]
        if not ys:
            raise PlotError("This chart needs at least one numeric column.")
    elif kind == "line":
        x = x or cols[0]
        ys = [c for c in ys if c in numeric and c != x] or [c for c in varying if c != x][:6]
        if not ys:
            raise PlotError("A line chart needs at least one numeric column besides x.")
    elif kind == "scatter":
        # A scatter needs two axes, so a constant column is better than no chart.
        pair = varying if len(varying) > 1 else measured
        if x not in numeric:
            x = next((c for c in pair if c not in ys), None)
        ys = [c for c in ys if c in numeric and c != x][:1] or [c for c in pair if c != x][:1]
        if not x or not ys:
            raise PlotError("A scatter plot needs two numeric columns.")
    elif kind == "hist":
        x = x if x in numeric else (ys[0] if ys and ys[0] in numeric else (varying[0] if varying else None))
        ys = []
        if not x:
            raise PlotError("A histogram needs a numeric column.")
    elif kind == "heatmap":
        ys = [c for c in ys if c in numeric] or numeric[:40]
        x = x if x and x not in ys else (text[0] if text else None)
        if len(ys) < 1:
            raise PlotError("A heat map needs numeric columns.")
    elif kind == "volcano":
        if x not in numeric:
            x = next((lower[k] for k in ("log2fc", "log2foldchange", "logfc", "log2_fold_change") if k in lower and lower[k] in numeric), numeric[0] if numeric else None)
        ys = [c for c in ys if c in numeric and c != x][:1]
        if not ys:
            pick = next((lower[k] for k in ("padj", "p.adj", "fdr", "qvalue", "pvalue", "p_value", "p.value", "p") if k in lower and lower[k] in numeric and lower[k] != x), None)
            ys = [pick] if pick else [c for c in numeric if c != x][:1]
        label = label or (text[0] if text else None)
        if not x or not ys:
            raise PlotError("A volcano plot needs a fold-change column and a p-value column.")
    if group in ys or group == x:
        group = None

    def num(key: str, default: float, lo: float, hi: float) -> float:
        try:
            v = float(spec.get(key, default))
        except (TypeError, ValueError):
            v = default
        return max(lo, min(hi, v)) if v == v else default

    # No "error" key: bars and lines get SEM. An explicit null / "none": no error bars.
    error = str(spec.get("error") or "none").lower() if "error" in spec else ("sem" if kind in ("bar", "line") else "none")
    palette = str(spec.get("palette") or "theme").lower()
    test = str(spec.get("test") or "parametric").lower()
    return {
        "kind": kind,
        "x": x,
        "y": ys,
        "group": group,
        "label": label,
        "title": str(spec.get("title") or "")[:200],
        "xlabel": str(spec.get("xlabel") if spec.get("xlabel") is not None else "")[:120],
        "ylabel": str(spec.get("ylabel") if spec.get("ylabel") is not None else "")[:120],
        "error": error if error in ERRORS else None,
        "stats": bool(spec.get("stats")),
        "test": "nonparametric" if test.startswith("non") or test in ("mannwhitney", "kruskal", "rank") else "parametric",
        "fit": bool(spec.get("fit")),
        "points": spec.get("points") is not False,
        "logx": bool(spec.get("logx")),
        "logy": bool(spec.get("logy")),
        "palette": palette if palette in PALETTES else "theme",
        "bins": int(num("bins", 0, 0, 200)),
        "zscore": bool(spec.get("zscore")),
        "fc_threshold": num("fc_threshold", 1.0, 0.0, 20.0),
        "p_threshold": num("p_threshold", 0.05, 1e-300, 1.0),
        "top_labels": int(num("top_labels", 8, 0, 40)),
        "width": num("width", 6.4, 2.0, 20.0),
        "height": num("height", 4.4, 1.5, 20.0),
        "unknown": unknown,
    }


# ---------------------------------------------------------------------------- stats
def stars(p: float) -> str:
    if p != p:
        return "n/a"
    return "****" if p < 1e-4 else "***" if p < 1e-3 else "**" if p < 1e-2 else "*" if p < 0.05 else "ns"


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjustment."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


def group_values(df, x: str, y: str) -> tuple[list[str], list]:
    import numpy as np

    sub = df[[x, y]].dropna()
    names: list[str] = []
    for v in sub[x].tolist():
        s = str(v)
        if s not in names:
            names.append(s)
    values = [np.asarray(sub.loc[sub[x].astype(str) == n, y], dtype=float) for n in names]
    return names, values


def compare_groups(names: list[str], values: list, test: str = "parametric") -> dict:
    """Omnibus and pairwise comparisons between groups of measurements."""
    import numpy as np
    from scipy import stats as st

    out: dict[str, Any] = {"groups": [], "comparisons": [], "omnibus": None, "notes": [], "test": ""}
    for n, v in zip(names, values):
        out["groups"].append({"name": n, "n": int(v.size), "mean": float(np.mean(v)) if v.size else float("nan"), "sd": float(np.std(v, ddof=1)) if v.size > 1 else float("nan"), "median": float(np.median(v)) if v.size else float("nan")})
    usable = [(n, v) for n, v in zip(names, values) if v.size >= 2]
    if len(usable) < 2:
        out["notes"].append("At least two groups with two or more values each are needed for a test.")
        return out
    if any(v.size < 3 for _n, v in usable):
        out["notes"].append("Some groups have fewer than 3 values: treat the p-values as a rough guide only.")
    if len(usable) > 12:
        out["notes"].append("More than 12 groups: pairwise comparisons were skipped.")
    flat = [n for n, v in usable if float(np.ptp(v)) == 0.0]
    if flat:
        out["notes"].append(f"Every value is identical in: {', '.join(flat[:6])}. A test on constant data has no answer, so the p-values are left blank.")
    if test == "parametric":
        skewed = []
        for n, v in usable:
            if 3 <= v.size <= 5000 and np.ptp(v) > 0:
                try:
                    if st.shapiro(v).pvalue < 0.05:
                        skewed.append(n)
                except ValueError:
                    pass
        if skewed:
            out["notes"].append(f"Shapiro-Wilk suggests non-normal data in: {', '.join(skewed[:6])}. Consider the non-parametric test.")

    def pair(a, b) -> float:
        try:
            if test == "parametric":
                return float(st.ttest_ind(a, b, equal_var=False).pvalue)
            return float(st.mannwhitneyu(a, b, alternative="two-sided").pvalue)
        except ValueError:
            return float("nan")

    if len(usable) == 2:
        (na, a), (nb, b) = usable
        p = pair(a, b)
        out["test"] = "Welch's t-test" if test == "parametric" else "Mann-Whitney U test"
        comp = {"a": na, "b": nb, "p": p, "p_adj": p, "stars": stars(p)}
        if test == "parametric":
            pooled = math.sqrt(((a.size - 1) * np.var(a, ddof=1) + (b.size - 1) * np.var(b, ddof=1)) / max(1, a.size + b.size - 2))
            comp["cohen_d"] = float((np.mean(a) - np.mean(b)) / pooled) if pooled > 0 else float("nan")
        out["comparisons"].append(comp)
        return out

    arrays = [v for _n, v in usable]
    try:
        if test == "parametric":
            res = st.f_oneway(*arrays)
            out["omnibus"] = {"test": "one-way ANOVA", "statistic": float(res.statistic), "p": float(res.pvalue)}
        else:
            res = st.kruskal(*arrays)
            out["omnibus"] = {"test": "Kruskal-Wallis", "statistic": float(res.statistic), "p": float(res.pvalue)}
    except ValueError as exc:
        out["notes"].append(f"The overall test could not be run ({exc}).")
    if len(usable) > 12:
        out["test"] = out["omnibus"]["test"] if out["omnibus"] else ""
        return out
    pairs = [(i, j) for i in range(len(usable)) for j in range(i + 1, len(usable))]
    if test == "parametric":
        out["test"] = "one-way ANOVA with Tukey HSD"
        try:
            tk = st.tukey_hsd(*arrays)
            for i, j in pairs:
                p = float(tk.pvalue[i, j])
                out["comparisons"].append({"a": usable[i][0], "b": usable[j][0], "p": p, "p_adj": p, "stars": stars(p)})
        except (ValueError, AttributeError) as exc:
            out["notes"].append(f"Tukey HSD could not be run ({exc}).")
    else:
        out["test"] = "Kruskal-Wallis with Holm-corrected Mann-Whitney U tests"
        raw = [pair(usable[i][1], usable[j][1]) for i, j in pairs]
        adj = holm([1.0 if p != p else p for p in raw])
        for (i, j), p, pa in zip(pairs, raw, adj):
            out["comparisons"].append({"a": usable[i][0], "b": usable[j][0], "p": p, "p_adj": pa, "stars": stars(pa)})
    return out


def spread(values, kind: str | None) -> float:
    import numpy as np
    from scipy import stats as st

    n = values.size
    if not kind or n < 2:
        return 0.0
    sd = float(np.std(values, ddof=1))
    if kind == "sd":
        return sd
    sem = sd / math.sqrt(n)
    if kind == "sem":
        return sem
    return float(st.t.ppf(0.975, n - 1)) * sem


# ----------------------------------------------------------------------- aggregation
def _bar_series(df, spec: dict) -> tuple[Any, str, list[tuple[str, str, str | None]], list[str]]:
    """Resolve what the bars are: ``(table, x column, [(legend label, y column, group value)], categories)``."""
    x = spec["x"]
    ys = spec["y"]
    if x is None:
        df = df.assign(**{"": "all"})
        x = ""
    if spec["kind"] == "bar" and len(ys) > 1:
        series: list[tuple[str, str, str | None]] = [(y, y, None) for y in ys]
    elif spec["group"]:
        gvals = [str(v) for v in dict.fromkeys(df[spec["group"]].dropna().astype(str))][:8]
        series = [(g, ys[0], g) for g in gvals]
    else:
        series = [(ys[0], ys[0], None)]
    cats = [str(v) for v in dict.fromkeys(df[x].dropna().astype(str))][:40]
    return df, x, series, cats


def _line_series(df, spec: dict) -> tuple[bool, list[str], list[dict]]:
    """Mean and spread per x for every line: ``(x is numeric, category order, [{name, x, mean, err}])``.

    With a text x axis every series is placed on the same category order, so a
    series that lacks one category leaves a gap instead of sliding sideways.
    """
    import numpy as np

    x, ys = spec["x"], spec["y"]
    numeric_x = is_number(df[x])
    order = [] if numeric_x else [str(v) for v in dict.fromkeys(df[x].dropna().astype(str))]
    index = {name: i for i, name in enumerate(order)}
    out: list[dict] = []
    for ycol in ys:
        sub = df[[x, ycol]].dropna()
        if numeric_x:
            grouped = sub.groupby(x, sort=True)[ycol]
            xs = np.asarray(list(grouped.groups.keys()), dtype=float)
        else:
            grouped = sub.assign(**{x: sub[x].astype(str)}).groupby(x, sort=False)[ycol]
            xs = np.asarray([index[str(k)] for k in grouped.groups.keys()], dtype=float)
        means = grouped.mean().to_numpy(dtype=float)
        errs = np.asarray([spread(np.asarray(g, dtype=float), spec["error"]) for _k, g in grouped], dtype=float)
        if xs.size:
            keep = np.argsort(xs, kind="stable")
            xs, means, errs = xs[keep], means[keep], errs[keep]
        out.append({"name": ycol, "x": xs, "mean": means, "err": errs})
    return numeric_x, order, out


def _pie_totals(df, spec: dict):
    x, ycol = spec["x"], spec["y"][0]
    sub = df[[x, ycol]].dropna()
    totals = sub.assign(**{x: sub[x].astype(str)}).groupby(x, sort=False)[ycol].sum()
    totals = totals[totals > 0]
    if totals.empty:
        raise PlotError("A pie chart needs positive values.")
    if len(totals) > 10:
        top = totals.sort_values(ascending=False)
        totals = top.iloc[:9]
        totals.loc["other"] = float(top.iloc[9:].sum())
    return totals


def chart_data(df, spec: dict, theme: str | None = None) -> dict | None:
    """The numbers behind a chart, for the kinds an office program can draw natively.

    Returns ``None`` for box, violin, histogram, heat map and volcano plots;
    exporters embed a picture for those. Values are plain floats (``None`` = no data).
    """
    import numpy as np

    spec = normalize_spec(spec, df)
    kind = spec["kind"]
    base = {"kind": kind, "title": spec["title"], "xlabel": spec["xlabel"], "ylabel": spec["ylabel"], "error": None, "logx": spec["logx"], "logy": spec["logy"], "spec": spec}

    def clean(v: float) -> float | None:
        return float(v) if v == v and abs(v) != float("inf") else None

    if kind == "bar":
        table, x, series, cats = _bar_series(df, spec)
        single = len(series) == 1
        rows = []
        any_err = False
        for lab, ycol, gval in series:
            sub = table if gval is None else table[table[spec["group"]].astype(str) == gval]
            lookup = dict(zip(*group_values(sub, x, ycol)))
            means, errs = [], []
            for cat in cats:
                v = lookup.get(cat)
                if v is None or not v.size:
                    means.append(None)
                    errs.append(0.0)
                    continue
                means.append(clean(float(np.mean(v))))
                errs.append(spread(v, spec["error"]))
            any_err = any_err or any(e > 0 for e in errs)
            rows.append({"name": lab, "values": means, "errors": errs})
        base.update(categories=cats, series=rows, colors=_colors(spec, theme, len(cats) if single else len(series)), vary=single, error=spec["error"] if any_err else None)
        base["xlabel"] = base["xlabel"] or x
        base["ylabel"] = base["ylabel"] or (spec["y"][0] if len(spec["y"]) == 1 else "")
        return base
    if kind == "line":
        numeric_x, order, lines = _line_series(df, spec)
        rows = []
        any_err = False
        for ln in lines:
            errs = [float(e) for e in ln["err"]]
            any_err = any_err or any(e > 0 for e in errs)
            if numeric_x:
                rows.append({"name": ln["name"], "x": [float(v) for v in ln["x"]], "values": [clean(float(v)) for v in ln["mean"]], "errors": errs})
            else:
                values: list[float | None] = [None] * len(order)
                errors = [0.0] * len(order)
                for xi, m, e in zip(ln["x"], ln["mean"], errs):
                    values[int(xi)] = clean(float(m))
                    errors[int(xi)] = e
                rows.append({"name": ln["name"], "values": values, "errors": errors})
        base.update(categories=order, numeric_x=numeric_x, series=rows, colors=_colors(spec, theme, len(rows)), vary=False, error=spec["error"] if any_err else None)
        base["xlabel"] = base["xlabel"] or spec["x"]
        base["ylabel"] = base["ylabel"] or (spec["y"][0] if len(spec["y"]) == 1 else "")
        return base
    if kind == "scatter":
        x, ycol = spec["x"], spec["y"][0]
        sub = df[[c for c in (x, ycol, spec["group"]) if c]].dropna()
        groups = [str(v) for v in dict.fromkeys(sub[spec["group"]].astype(str))][:10] if spec["group"] else [None]
        rows = []
        for g in groups:
            part = sub if g is None else sub[sub[spec["group"]].astype(str) == g]
            part = part.iloc[:4000]
            rows.append({"name": g if g is not None else ycol, "x": [float(v) for v in part[x]], "values": [float(v) for v in part[ycol]], "errors": None})
        base.update(categories=[], numeric_x=True, series=rows, colors=_colors(spec, theme, len(rows)), vary=False, fit=bool(spec["fit"]) and len(rows) == 1 and not spec["logx"] and not spec["logy"])
        base["xlabel"] = base["xlabel"] or x
        base["ylabel"] = base["ylabel"] or ycol
        return base
    if kind == "pie":
        totals = _pie_totals(df, spec)
        base.update(categories=[str(k) for k in totals.index], series=[{"name": spec["y"][0], "values": [float(v) for v in totals.to_numpy(dtype=float)], "errors": None}], colors=_colors(spec, theme, len(totals)), vary=True)
        return base
    return None


# -------------------------------------------------------------------------- drawing
def _colors(spec: dict, theme: str | None, n: int) -> list[str]:
    if spec["palette"] == "okabe":
        base = _OKABE
    elif spec["palette"] == "mono":
        base = _MONO
    elif spec["palette"] == "viridis":
        from matplotlib import colormaps
        from matplotlib.colors import to_hex

        cm = colormaps["viridis"]
        return [to_hex(cm(0.08 + 0.84 * (i / max(1, n - 1)))) for i in range(max(1, n))]
    else:
        base = get_theme(theme)["strong"]
    return [base[i % len(base)] for i in range(max(1, n))]


def _style_axes(ax, ink: str) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(1.0)
        ax.spines[side].set_color(ink)
    ax.tick_params(direction="out", length=4, width=1.0, colors=ink, labelsize=9)
    ax.xaxis.label.set_color(ink)
    ax.yaxis.label.set_color(ink)
    ax.xaxis.label.set_size(10)
    ax.yaxis.label.set_size(10)


def _jitter(n: int, width: float, seed: int):
    import numpy as np

    return (np.random.default_rng(seed).random(n) - 0.5) * width


def _brackets(ax, positions: dict[str, float], tops: dict[str, float], comparisons: list[dict], ink: str, limit: int = 6) -> None:
    """Significance brackets above groups, shortest spans first, stacked without overlap."""
    shown = [c for c in comparisons if c["stars"] not in ("ns", "n/a")] if len(comparisons) > 1 else list(comparisons)
    shown = [c for c in shown if c["a"] in positions and c["b"] in positions]
    shown.sort(key=lambda c: (abs(positions[c["a"]] - positions[c["b"]]), c["p_adj"]))
    shown = shown[:limit]
    if not shown:
        return
    y0, y1 = ax.get_ylim()
    step = (y1 - y0) * 0.085
    levels: list[tuple[float, float, float]] = []
    top = y1
    for c in shown:
        a, b = sorted((positions[c["a"]], positions[c["b"]]))
        base = max(tops[n] for n, p in positions.items() if a - 1e-9 <= p <= b + 1e-9) + step * 0.5
        for la, lb, ly in levels:
            if not (b < la or a > lb) and base < ly + step:
                base = ly + step
        levels.append((a, b, base))
        ax.plot([a, a, b, b], [base, base + step * 0.25, base + step * 0.25, base], color=ink, linewidth=1.0, clip_on=False)
        ax.text((a + b) / 2, base + step * 0.28, c["stars"], ha="center", va="bottom", fontsize=10 if c["stars"] != "ns" else 9, color=ink)
        top = max(top, base + step * 0.95)
    ax.set_ylim(y0, top)


def _draw(fig, ax, df, spec: dict, theme: str | None) -> dict:
    import numpy as np

    t = get_theme(theme)
    ink = t["ink"]
    kind = spec["kind"]
    info: dict[str, Any] = {}
    _style_axes(ax, ink)
    xlabel, ylabel = spec["xlabel"], spec["ylabel"]

    if kind in ("bar", "box", "violin"):
        ys = spec["y"]
        df, x, series, cats = _bar_series(df, spec)
        k = len(series)
        single = k == 1
        colors = _colors(spec, theme, len(cats) if single else k)
        width = 0.72 / k
        positions: dict[str, float] = {}
        tops: dict[str, float] = {}
        for si, (lab, ycol, gval) in enumerate(series):
            sub = df if gval is None else df[df[spec["group"]].astype(str) == gval]
            names, values = group_values(sub, x, ycol)
            lookup = dict(zip(names, values))
            for ci, cat in enumerate(cats):
                v = lookup.get(cat, np.asarray([], dtype=float))
                pos = ci + (si - (k - 1) / 2) * width
                color = colors[ci] if single else colors[si]
                if not v.size:
                    continue
                if kind == "bar":
                    mean = float(np.mean(v))
                    err = spread(v, spec["error"])
                    ax.bar(pos, mean, width=width * 0.92, color=color, alpha=0.86, edgecolor=ink, linewidth=0.8, label=lab if (not single and ci == 0) else None, zorder=2)
                    if err > 0:
                        ax.errorbar(pos, mean, yerr=err, color=ink, capsize=3, linewidth=1.0, zorder=4)
                    hi = mean + err
                elif kind == "box":
                    bp = ax.boxplot([v], positions=[pos], widths=width * 0.8, patch_artist=True, showfliers=False, zorder=2, manage_ticks=False)
                    for patch in bp["boxes"]:
                        patch.set(facecolor=color, alpha=0.55, edgecolor=ink, linewidth=1.0)
                    for part in ("whiskers", "caps", "medians"):
                        for line in bp[part]:
                            line.set(color=ink, linewidth=1.0)
                    if not single and ci == 0:
                        ax.bar(pos, 0, color=color, alpha=0.55, edgecolor=ink, label=lab)
                    hi = float(np.max(v))
                else:
                    if v.size >= 3 and np.ptp(v) > 0:
                        vp = ax.violinplot([v], positions=[pos], widths=width * 0.9, showextrema=False)
                        for body in vp["bodies"]:
                            body.set(facecolor=color, alpha=0.5, edgecolor=ink, linewidth=1.0)
                    ax.plot([pos - width * 0.18, pos + width * 0.18], [np.median(v)] * 2, color=ink, linewidth=1.6, zorder=4)
                    if not single and ci == 0:
                        ax.bar(pos, 0, color=color, alpha=0.5, edgecolor=ink, label=lab)
                    hi = float(np.max(v))
                if spec["points"] and v.size <= 60:
                    ax.scatter(pos + _jitter(v.size, width * 0.45, ci * 31 + si), v, s=13, color=ink if kind == "bar" else color, alpha=0.7, edgecolors=ink if kind != "bar" else "none", linewidths=0.4, zorder=5)
                    hi = max(hi, float(np.max(v)))
                if single:
                    positions[cat] = pos
                    tops[cat] = hi
        ax.set_xticks(range(len(cats)))
        long = max((len(c) for c in cats), default=0) > 8 or len(cats) > 8
        ax.set_xticklabels(cats, rotation=35 if long else 0, ha="right" if long else "center")
        ax.set_xlim(-0.6, len(cats) - 0.4)
        if kind == "bar" and not spec["logy"]:
            lo, hi = ax.get_ylim()
            if lo >= 0:
                ax.set_ylim(0, hi)
        ax.set_xlabel(xlabel if xlabel else (x or ""))
        ax.set_ylabel(ylabel if ylabel else (ys[0] if len(ys) == 1 else ""))
        if not single:
            ax.legend(frameon=False, fontsize=9)
        if spec["stats"] and single:
            names, values = group_values(df, x, ys[0])
            res = compare_groups(names, values, spec["test"])
            info["stats"] = res
            _brackets(ax, positions, tops, res["comparisons"], ink)
        elif spec["stats"]:
            info["stats"] = {"notes": ["Statistical brackets are drawn for a single series only; remove the grouping to compare categories."], "groups": [], "comparisons": [], "omnibus": None, "test": ""}
        if kind == "bar" and spec["error"]:
            info["error"] = spec["error"]

    elif kind == "line":
        x, ys = spec["x"], spec["y"]
        colors = _colors(spec, theme, len(ys))
        numeric_x, order, lines = _line_series(df, spec)
        for i, ln in enumerate(lines):
            xs, means, errs = ln["x"], ln["mean"], ln["err"]
            ax.plot(xs, means, marker="o", markersize=4.5, linewidth=1.8, color=colors[i], label=ln["name"], zorder=3)
            if np.any(errs > 0):
                ax.fill_between(xs, means - errs, means + errs, color=colors[i], alpha=0.18, linewidth=0, zorder=2)
                info["error"] = spec["error"]
        if not numeric_x:
            ax.set_xticks(range(len(order)))
            ax.set_xticklabels(order, rotation=35 if len(order) > 8 else 0, ha="right" if len(order) > 8 else "center")
        ax.set_xlabel(xlabel if xlabel else x)
        ax.set_ylabel(ylabel if ylabel else (ys[0] if len(ys) == 1 else ""))
        if len(ys) > 1:
            ax.legend(frameon=False, fontsize=9)

    elif kind == "scatter":
        from scipy import stats as st

        x, ycol = spec["x"], spec["y"][0]
        sub = df[[c for c in (x, ycol, spec["group"]) if c]].dropna()
        groups = [str(v) for v in dict.fromkeys(sub[spec["group"]].astype(str))][:10] if spec["group"] else [None]
        colors = _colors(spec, theme, len(groups))
        for i, g in enumerate(groups):
            part = sub if g is None else sub[sub[spec["group"]].astype(str) == g]
            ax.scatter(part[x], part[ycol], s=26, color=colors[i], alpha=0.8, edgecolors="white", linewidths=0.5, label=g, zorder=3)
        if spec["fit"] and len(sub) >= 3 and sub[x].nunique() > 1:
            fit_x = np.log10(sub[x]) if spec["logx"] and (sub[x] > 0).all() else sub[x]
            fit_y = np.log10(sub[ycol]) if spec["logy"] and (sub[ycol] > 0).all() else sub[ycol]
            lr = st.linregress(fit_x.astype(float), fit_y.astype(float))
            xs = np.linspace(float(fit_x.min()), float(fit_x.max()), 60)
            line = lr.intercept + lr.slope * xs
            ax.plot(10**xs if spec["logx"] and (sub[x] > 0).all() else xs, 10**line if spec["logy"] and (sub[ycol] > 0).all() else line, color=ink, linewidth=1.4, linestyle="--", zorder=4)
            ptxt = "p < 0.0001" if lr.pvalue < 1e-4 else f"p = {lr.pvalue:.3g}"
            ax.text(0.03, 0.97, f"r = {lr.rvalue:.3f}, R² = {lr.rvalue**2:.3f}\n{ptxt}, n = {len(sub)}", transform=ax.transAxes, ha="left", va="top", fontsize=9, color=ink)
            info["fit"] = {"slope": float(lr.slope), "intercept": float(lr.intercept), "r": float(lr.rvalue), "r2": float(lr.rvalue**2), "p": float(lr.pvalue), "n": int(len(sub))}
        ax.set_xlabel(xlabel if xlabel else x)
        ax.set_ylabel(ylabel if ylabel else ycol)
        if spec["group"]:
            ax.legend(frameon=False, fontsize=9, title=spec["group"], title_fontsize=9)

    elif kind == "hist":
        x = spec["x"]
        sub = df[[c for c in (x, spec["group"]) if c]].dropna()
        groups = [str(v) for v in dict.fromkeys(sub[spec["group"]].astype(str))][:6] if spec["group"] else [None]
        colors = _colors(spec, theme, len(groups))
        allv = sub[x].to_numpy(dtype=float)
        if spec["bins"]:
            bins: Any = spec["bins"]
        else:
            edges = np.histogram_bin_edges(allv, bins="fd") if allv.size > 1 and np.ptp(allv) > 0 else np.histogram_bin_edges(allv, bins=10)
            bins = edges if 5 <= len(edges) - 1 <= 60 else min(60, max(5, int(math.sqrt(max(1, allv.size)))))
        if not isinstance(bins, int):
            edges_all = bins
        else:
            edges_all = np.histogram_bin_edges(allv, bins=bins)
        for i, g in enumerate(groups):
            part = sub if g is None else sub[sub[spec["group"]].astype(str) == g]
            ax.hist(part[x].to_numpy(dtype=float), bins=edges_all, color=colors[i], alpha=0.8 if g is None else 0.55, edgecolor="white", linewidth=0.6, label=g, zorder=2)
        ax.set_xlabel(xlabel if xlabel else x)
        ax.set_ylabel(ylabel if ylabel else "Count")
        if spec["group"]:
            ax.legend(frameon=False, fontsize=9)

    elif kind == "heatmap":
        ys = spec["y"]
        sub = df[ys + ([spec["x"]] if spec["x"] else [])].dropna(subset=ys, how="all").head(200)
        mat = sub[ys].to_numpy(dtype=float)
        if spec["zscore"]:
            mu = np.nanmean(mat, axis=1, keepdims=True)
            sd = np.nanstd(mat, axis=1, keepdims=True)
            mat = (mat - mu) / np.where(sd > 0, sd, 1.0)
        finite = mat[np.isfinite(mat)]
        diverging = finite.size > 0 and finite.min() < 0 < finite.max()
        vmax = float(np.nanmax(np.abs(finite))) if finite.size else 1.0
        im = ax.imshow(mat, aspect="auto", cmap="RdBu_r" if diverging else "viridis", vmin=-vmax if diverging else None, vmax=vmax if diverging else None, interpolation="nearest")
        ax.set_xticks(range(len(ys)))
        ax.set_xticklabels(ys, rotation=40, ha="right")
        rows = sub[spec["x"]].astype(str).tolist() if spec["x"] else [str(i + 1) for i in range(mat.shape[0])]
        if mat.shape[0] <= 45:
            ax.set_yticks(range(mat.shape[0]))
            ax.set_yticklabels(rows, fontsize=8 if mat.shape[0] > 22 else 9)
        else:
            ax.set_yticks([])
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0)
        if mat.shape[0] <= 12 and mat.shape[1] <= 12:
            lo, hi = (float(np.nanmin(finite)), float(np.nanmax(finite))) if finite.size else (0.0, 1.0)
            for r in range(mat.shape[0]):
                for cidx in range(mat.shape[1]):
                    v = mat[r, cidx]
                    if np.isfinite(v):
                        rel = abs(v) / vmax if diverging and vmax else ((v - lo) / (hi - lo) if hi > lo else 0.5)
                        ax.text(cidx, r, f"{v:.2g}", ha="center", va="center", fontsize=8, color="white" if (rel > 0.6 if diverging else rel < 0.45) else "#111111")
        cbar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03)
        cbar.ax.tick_params(labelsize=8, length=2)
        cbar.outline.set_visible(False)
        if spec["zscore"]:
            cbar.set_label("row z-score", fontsize=9)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

    elif kind == "pie":
        totals = _pie_totals(df, spec)
        colors = _colors(spec, theme, len(totals))
        ax.pie(totals.to_numpy(dtype=float), labels=list(totals.index), colors=colors, autopct=lambda p: f"{p:.1f}%" if p >= 3 else "", startangle=90, counterclock=False, pctdistance=0.78, wedgeprops={"width": 0.45, "edgecolor": "white", "linewidth": 1.5}, textprops={"fontsize": 9, "color": ink})
        ax.set_aspect("equal")

    elif kind == "volcano":
        x, pcol = spec["x"], spec["y"][0]
        cols = [x, pcol] + ([spec["label"]] if spec["label"] else [])
        sub = df[cols].dropna(subset=[x, pcol])
        p = sub[pcol].to_numpy(dtype=float)
        fc = sub[x].to_numpy(dtype=float)
        ok = (p > 0) & (p <= 1) & np.isfinite(fc)
        if not ok.any():
            raise PlotError("The p-value column has no values between 0 and 1.")
        dropped = int((~ok).sum())
        if dropped:
            info["dropped"] = dropped
        p, fc = p[ok], fc[ok]
        logp = -np.log10(p)
        sig = p < spec["p_threshold"]
        up = sig & (fc >= spec["fc_threshold"])
        down = sig & (fc <= -spec["fc_threshold"])
        ns = ~(up | down)
        c_up, c_down = "#d1495b", "#2f6fb7"
        ax.scatter(fc[ns], logp[ns], s=9, color="#b8bec9", alpha=0.7, linewidths=0, zorder=2, label=f"n.s. ({int(ns.sum())})")
        ax.scatter(fc[down], logp[down], s=13, color=c_down, alpha=0.85, linewidths=0, zorder=3, label=f"down ({int(down.sum())})")
        ax.scatter(fc[up], logp[up], s=13, color=c_up, alpha=0.85, linewidths=0, zorder=3, label=f"up ({int(up.sum())})")
        ax.axhline(-math.log10(spec["p_threshold"]), color=ink, linewidth=0.8, linestyle=":", zorder=1)
        if spec["fc_threshold"] > 0:
            for v in (-spec["fc_threshold"], spec["fc_threshold"]):
                ax.axvline(v, color=ink, linewidth=0.8, linestyle=":", zorder=1)
        if spec["label"] and spec["top_labels"]:
            labels = sub[spec["label"]].astype(str).to_numpy()[ok]
            hits = np.nonzero(up | down)[0]
            for i in hits[np.argsort(-logp[hits])][: spec["top_labels"]]:
                ax.annotate(labels[i], (fc[i], logp[i]), xytext=(4, 3), textcoords="offset points", fontsize=8, color=ink)
        ax.set_xlabel(xlabel if xlabel else x)
        ax.set_ylabel(ylabel if ylabel else f"-log10({pcol})")
        ax.legend(frameon=False, fontsize=8, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.12))
        info["counts"] = {"up": int(up.sum()), "down": int(down.sum()), "not_significant": int(ns.sum())}

    if spec["logx"] and kind in ("scatter", "line", "hist"):
        ax.set_xscale("log")
        _log_warning(info, df, [x] if x else [], "x")
    if spec["logy"] and kind in ("scatter", "line", "bar", "box", "violin", "hist"):
        ax.set_yscale("log")
        _log_warning(info, df, list(spec["y"]), "y")
    if spec["title"]:
        ax.set_title(spec["title"], fontsize=11, color=ink, pad=22 if kind == "volcano" else 8, fontweight="bold")
    return info


def _log_warning(info: dict, df, columns: list[str], axis: str) -> None:
    """A log axis cannot show zero or a negative number, and silently drops it.

    A bar that disappears is worse than an ugly chart, so say so.
    """
    import pandas as pd

    bad = 0
    for c in columns:
        if c and c in df.columns and is_number(df[c]):
            values = pd.to_numeric(df[c], errors="coerce")
            bad += int((values <= 0).sum())
    if bad:
        info.setdefault("notes", []).append(
            f"{bad} value(s) are zero or negative and cannot be drawn on a log {axis} axis; they are missing from the chart"
        )


def render_plot(df, spec: dict, theme: str | None = None, fmt: str = "svg", dpi: int = 300) -> tuple[bytes, dict]:
    """Draw the chart. Returns ``(image bytes, info)`` where info carries statistics and notes."""
    spec = normalize_spec(spec, df)
    if fmt not in ("svg", "png", "pdf"):
        raise PlotError("Charts can be saved as svg, png or pdf.")
    with _LOCK:
        _setup()
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        fig = Figure(figsize=(spec["width"], spec["height"]), dpi=100, facecolor="white")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        try:
            info = _draw(fig, ax, df, spec, theme)
        except PlotError:
            raise
        except Exception as exc:  # noqa: BLE001 - turn numeric edge cases into a readable message
            raise PlotError(f"The chart could not be drawn ({type(exc).__name__}: {str(exc)[:160]}).") from exc
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format=fmt, dpi=dpi if fmt == "png" else 100, facecolor="white", metadata={"Date": None} if fmt == "svg" else None)
    for name in spec.get("unknown") or []:
        info.setdefault("notes", []).append(
            f"There is no column called '{name}' in this table, so the chart was drawn with another one; the columns are: {', '.join(str(c) for c in df.columns)}"
        )
    info["spec"] = spec
    return buf.getvalue(), info


def caption(info: dict, lang: str = "en") -> str:
    """A methods sentence describing the statistics actually computed, ready for a figure legend."""
    spec = info.get("spec") or {}
    parts: list[str] = []
    err = {"sd": "SD", "sem": "SEM", "ci95": "95% CI"}.get(info.get("error") or "")
    if lang == "zh":
        if err:
            parts.append(f"数据以均值 ± {err} 表示。")
        st = info.get("stats") or {}
        if st.get("test"):
            ns = "、".join(f"{g['name']} n = {g['n']}" for g in st.get("groups", []))
            parts.append(f"统计检验：{st['test']}（{ns}）。")
            om = st.get("omnibus")
            if om:
                parts.append(f"整体检验 {om['test']}：p = {om['p']:.3g}。")
            parts.append("ns 不显著，* p < 0.05，** p < 0.01，*** p < 0.001，**** p < 0.0001。")
        if info.get("fit"):
            f = info["fit"]
            parts.append(f"线性回归：r = {f['r']:.3f}，R² = {f['r2']:.3f}，p = {f['p']:.3g}，n = {f['n']}。")
        if info.get("counts") is not None and spec.get("kind") == "volcano":
            parts.append(f"阈值：|log2FC| ≥ {spec['fc_threshold']:g} 且 p < {spec['p_threshold']:g}。")
    else:
        if err:
            parts.append(f"Data are shown as mean ± {err}.")
        st = info.get("stats") or {}
        if st.get("test"):
            ns = ", ".join(f"{g['name']} n = {g['n']}" for g in st.get("groups", []))
            parts.append(f"Statistics: {st['test']} ({ns}).")
            om = st.get("omnibus")
            if om:
                parts.append(f"Overall {om['test']}: p = {om['p']:.3g}.")
            parts.append("ns, not significant; * p < 0.05; ** p < 0.01; *** p < 0.001; **** p < 0.0001.")
        if info.get("fit"):
            f = info["fit"]
            parts.append(f"Linear regression: r = {f['r']:.3f}, R² = {f['r2']:.3f}, p = {f['p']:.3g}, n = {f['n']}.")
        if info.get("counts") is not None and spec.get("kind") == "volcano":
            parts.append(f"Thresholds: |log2FC| ≥ {spec['fc_threshold']:g} and p < {spec['p_threshold']:g}.")
    return " ".join(parts)
