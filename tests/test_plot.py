"""Charts and the statistics printed beside them.

A figure in a paper carries claims, so the numbers are checked against scipy
rather than against themselves, and the chart has to come out of matplotlib as
a real SVG, PNG and PDF.
"""

from __future__ import annotations

import io
import math
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp

from figwright import plot


def frame(csv: str) -> pd.DataFrame:
    return plot.load_table("t.csv", csv.encode("utf-8"))


# ------------------------------------------------------------------ reading tables


def test_a_csv_is_read_with_its_types(table_csv):
    df = frame(table_csv)
    assert list(df.columns) == ["group", "dose", "value"] and len(df) == 12
    assert plot.is_number(df["value"]) and not plot.is_number(df["group"])


def test_a_tab_separated_file_is_read_too(table_csv):
    df = plot.load_table("t.tsv", table_csv.replace(",", "\t").encode("utf-8"))
    assert list(df.columns) == ["group", "dose", "value"]


def test_pasted_text_is_read(table_csv):
    assert len(plot.parse_text_table(table_csv.replace(",", "\t"))) == 12
    assert len(plot.parse_text_table(table_csv)) == 12  # commas work too


def test_an_excel_file_is_read_by_sheet(tmp_path, table_csv):
    df = frame(table_csv)
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        df.to_excel(writer, sheet_name="first", index=False)
        df.head(3).to_excel(writer, sheet_name="second", index=False)
    data = path.read_bytes()
    assert plot.sheet_names("book.xlsx", data) == ["first", "second"]
    assert len(plot.load_table("book.xlsx", data, sheet="second")) == 3


def test_a_utf8_bom_and_gbk_file_both_decode():
    assert "组" in plot.decode_text("组,值\na,1\n".encode("utf-8-sig"))
    assert "组" in plot.decode_text("组,值\na,1\n".encode("gbk"))


def test_a_file_that_is_not_a_table_is_refused():
    with pytest.raises(plot.PlotError):
        plot.load_table("x.csv", b"\x00\x01\x02binary nonsense")


def test_an_empty_table_is_refused():
    with pytest.raises(plot.PlotError):
        plot.load_table("x.csv", b"")


def test_describe_reports_type_and_spread(table_csv):
    cols = {c["name"]: c for c in plot.describe(frame(table_csv))}
    assert cols["value"]["type"] == "number" and cols["value"]["unique"] == 12
    assert cols["group"]["type"] == "text" and cols["group"]["unique"] == 3
    assert cols["dose"]["unique"] == 1


def test_table_csv_round_trips(table_csv):
    df = frame(table_csv)
    assert plot.table_csv(df).strip().splitlines()[0] == "group,dose,value"


# ------------------------------------------------------------------ choosing a chart


def test_a_column_that_never_changes_is_not_charted(table_csv):
    """"dose" is 1 in every row: it is a label, not the measurement."""
    spec = plot.normalize_spec({}, frame(table_csv))
    assert spec["y"] == ["value"] and spec["x"] == "group"


def test_the_constant_column_is_still_used_when_asked_for(table_csv):
    spec = plot.normalize_spec({"y": ["dose"]}, frame(table_csv))
    assert spec["y"] == ["dose"]


def test_a_table_of_only_constants_still_charts():
    spec = plot.normalize_spec({}, pd.DataFrame({"g": ["a", "b"], "v": [1, 1]}))
    assert spec["y"] == ["v"]


@pytest.mark.parametrize("kind", ["bar", "box", "violin", "line", "scatter", "hist", "pie", "heatmap"])
def test_every_chart_kind_normalises(kind, wide_csv):
    spec = plot.normalize_spec({"kind": kind}, frame(wide_csv))
    assert spec["kind"] == kind


def test_aliases_are_accepted(table_csv):
    assert plot.normalize_spec({"kind": "boxplot"}, frame(table_csv))["kind"] == "box"
    assert plot.normalize_spec({"type": "column"}, frame(table_csv))["kind"] == "bar"


def test_an_unknown_kind_says_what_is_available(table_csv):
    with pytest.raises(plot.PlotError) as err:
        plot.normalize_spec({"kind": "sankey"}, frame(table_csv))
    assert "bar" in str(err.value)


def test_a_column_name_that_does_not_exist_is_replaced_and_reported(table_csv):
    """A near-miss still draws a chart, but the figure must not quietly change meaning."""
    spec = plot.normalize_spec({"x": "nope", "y": ["also nope"]}, frame(table_csv))
    assert spec["x"] == "group" and spec["y"] == ["value"]
    assert sorted(spec["unknown"]) == ["also nope", "nope"]
    _svg, info = plot.render_plot(frame(table_csv), {"x": "nope"})
    assert any("no column called 'nope'" in n for n in info["notes"])
    assert any("group" in n for n in info["notes"])


def test_numbers_outside_their_range_are_clamped(table_csv):
    spec = plot.normalize_spec({"width": 900, "height": -4, "bins": 10**6}, frame(table_csv))
    assert 1 <= spec["width"] <= 40 and spec["height"] > 0 and spec["bins"] <= 400


# ------------------------------------------------------------------ statistics


def test_two_groups_get_a_t_test(table_csv):
    df = frame(table_csv)
    df = df[df["group"] != "high"]
    names, values = plot.group_values(df, "group", "value")
    out = plot.compare_groups(names, values)
    a, b = values
    expect = sp.ttest_ind(a, b, equal_var=False)
    assert "t" in out["test"].lower()
    assert out["comparisons"][0]["p"] == pytest.approx(float(expect.pvalue), rel=1e-9)


def test_three_groups_get_an_anova_and_pairwise_tests(table_csv):
    names, values = plot.group_values(frame(table_csv), "group", "value")
    out = plot.compare_groups(names, values)
    assert out["omnibus"]["test"].lower().startswith("one-way")
    assert out["omnibus"]["p"] == pytest.approx(float(sp.f_oneway(*values).pvalue), rel=1e-9)
    assert len(out["comparisons"]) == 3
    assert all(c["p_adj"] >= c["p"] - 1e-12 for c in out["comparisons"])


def test_the_nonparametric_option_uses_rank_tests(table_csv):
    names, values = plot.group_values(frame(table_csv), "group", "value")
    out = plot.compare_groups(names, values, test="nonparametric")
    assert "kruskal" in out["omnibus"]["test"].lower()
    assert out["omnibus"]["p"] == pytest.approx(float(sp.kruskal(*values).pvalue), rel=1e-9)
    assert "whitney" in out["test"].lower() or "wilcoxon" in out["test"].lower()
    a, b = values[0], values[1]
    expect = sp.mannwhitneyu(a, b, alternative="two-sided").pvalue
    first = next(c for c in out["comparisons"] if {c["a"], c["b"]} == {names[0], names[1]})
    assert first["p"] == pytest.approx(float(expect), rel=1e-9)


def test_holm_correction_steps_down_and_stays_monotonic():
    # 0.01*3 = 0.03; 0.03*2 = 0.06; 0.04*1 = 0.04 but cannot fall below 0.06.
    assert plot.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert plot.holm([0.2]) == pytest.approx([0.2])
    assert plot.holm([]) == []
    assert all(0 <= v <= 1 for v in plot.holm([0.4, 0.5, 0.6]))


@pytest.mark.parametrize("p,mark", [(0.2, "ns"), (0.04, "*"), (0.004, "**"), (0.0004, "***"), (0.00004, "****")])
def test_stars_follow_the_usual_thresholds(p, mark):
    assert plot.stars(p) == mark


def test_a_group_with_one_value_is_reported_not_tested():
    out = plot.compare_groups(["a", "b"], [np.array([1.0]), np.array([2.0, 3.0])])
    assert out["notes"]
    assert not out.get("comparisons") or out["comparisons"][0].get("p") is None


def test_identical_values_are_called_out_rather_than_giving_nan():
    out = plot.compare_groups(["a", "b"], [np.array([2.0, 2.0, 2.0]), np.array([2.0, 2.0, 2.0])])
    assert any("identical" in n for n in out["notes"])


def test_means_and_spread_are_right(table_csv):
    names, values = plot.group_values(frame(table_csv), "group", "value")
    out = plot.compare_groups(names, values)
    first = out["groups"][0]
    assert first["mean"] == pytest.approx(float(np.mean(values[0])))
    assert first["sd"] == pytest.approx(float(np.std(values[0], ddof=1)))
    assert plot.spread(values[0], "sem") == pytest.approx(float(sp.sem(values[0])))
    assert plot.spread(values[0], None) == 0


# ------------------------------------------------------------------ drawing


def test_a_chart_comes_out_as_valid_svg(table_csv):
    svg, info = plot.render_plot(frame(table_csv), plot.normalize_spec({"stats": True}, frame(table_csv)))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert info["stats"]["comparisons"]


@pytest.mark.parametrize("fmt,magic", [("png", b"\x89PNG"), ("pdf", b"%PDF"), ("svg", b"<?xml")])
def test_every_export_format_is_what_it_claims(fmt, magic, table_csv):
    data, _info = plot.render_plot(frame(table_csv), plot.normalize_spec({}, frame(table_csv)), fmt=fmt, dpi=150)
    assert data[:5].startswith(magic)


def test_a_regression_line_reports_r_and_p(wide_csv):
    df = frame(wide_csv)
    spec = plot.normalize_spec({"kind": "scatter", "x": "conc", "y": ["signal"], "fit": True}, df)
    _svg, info = plot.render_plot(df, spec)
    fit = info["fit"]
    expect = sp.linregress(df["conc"], df["signal"])
    assert fit["r"] == pytest.approx(float(expect.rvalue), rel=1e-9)
    assert fit["p"] == pytest.approx(float(expect.pvalue), rel=1e-9)
    assert fit["r2"] == pytest.approx(float(expect.rvalue) ** 2, rel=1e-9)


def test_a_log_axis_says_which_values_it_cannot_show():
    """A bar that silently disappears is worse than an ugly chart."""
    df = pd.DataFrame({"g": ["a", "b", "c"], "v": [0.0, 1.0, 10.0]})
    _svg, info = plot.render_plot(df, plot.normalize_spec({"logy": True}, df))
    assert info["notes"] and "log y axis" in info["notes"][0]
    _svg, info = plot.render_plot(df, plot.normalize_spec({}, df))
    assert not info.get("notes")


def test_a_caption_is_written_in_both_languages(table_csv):
    df = frame(table_csv)
    _svg, info = plot.render_plot(df, plot.normalize_spec({"stats": True, "error": "sem"}, df))
    zh, en = plot.caption(info, "zh"), plot.caption(info, "en")
    assert zh and en and zh != en
    assert "n =" in en or "n=" in en


def test_chart_data_can_be_read_back_as_numbers(table_csv):
    df = frame(table_csv)
    data = plot.chart_data(df, plot.normalize_spec({}, df))
    assert data and data["series"]
    assert len(data["series"][0]["values"]) == 3  # one bar per group


def test_a_very_wide_table_is_charted_without_drawing_every_column():
    df = pd.DataFrame({f"c{i}": np.arange(5.0) + i for i in range(60)})
    spec = plot.normalize_spec({"kind": "heatmap"}, df)
    assert len(spec["y"]) <= 40
    svg, _ = plot.render_plot(df, spec)
    assert svg


def test_a_big_table_is_still_charted():
    df = pd.DataFrame({"g": np.repeat(list("abcd"), 5000), "v": np.random.default_rng(1).normal(size=20000)})
    svg, info = plot.render_plot(df, plot.normalize_spec({}, df))
    assert svg and info["spec"]["y"] == ["v"]


def test_missing_values_are_dropped_not_plotted_as_zero():
    df = pd.DataFrame({"g": ["a", "a", "b", "b"], "v": [1.0, math.nan, 3.0, 5.0]})
    data = plot.chart_data(df, plot.normalize_spec({}, df))
    first = data["series"][0]["values"]
    assert first[0] == pytest.approx(1.0) and first[1] == pytest.approx(4.0)
