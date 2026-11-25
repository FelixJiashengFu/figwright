"""The six diagram builders. Each takes structured content and must produce a
figure that passes its own layout check: no overlaps, no clipped text, no
connector drawn across a box.
"""

from __future__ import annotations

import pytest

from figwright import lint, offline, render, scene as S
from figwright.builders import BUILDERS
from figwright.builders.flowchart import build_flowchart
from figwright.builders.prisma import build_prisma, prisma_check

from conftest import FLOW_CONTENT

SERIOUS = {"overlap", "text_overflow", "edge_crosses", "off_canvas"}


def complaints(scene):
    return {i["code"] for i in lint.lint(S.normalize_scene(scene))} & SERIOUS


def test_every_builder_is_registered():
    assert set(BUILDERS) == {"flowchart", "workflow", "pathway", "abstract", "poster", "prisma"}


PROMPTS = {
    "flowchart": "样本采集，DNA 提取，质检，如果合格则建库测序，否则重新提取，数据分析",
    "workflow": "取材、提取 RNA、建库、测序、比对、差异表达分析",
    "pathway": "EGF 激活 EGFR，EGFR 磷酸化 RAS，RAS 激活 MEK，MEK 激活 ERK，雷帕霉素抑制 mTOR",
    "abstract": "标题：肠道菌群与免疫\n背景：菌群失衡与炎症相关\n方法：16S 测序\n结果：Treg 下降\n结论：菌群调节免疫",
    "poster": "题目：单细胞测序揭示肿瘤异质性\n背景：差异大\n方法：10x 单细胞\n结果：三个亚群\n结论：亚群决定耐药",
    "prisma": "检索到 1200 条记录，去重后 900 条，筛选排除 700 条，全文评估 200 条，纳入 20 项研究",
}


@pytest.mark.parametrize("kind", sorted(PROMPTS))
def test_each_builder_lays_out_a_clean_figure(kind):
    content = offline.content_for(kind, PROMPTS[kind])
    scene = BUILDERS[kind](content, "ink")
    assert scene["nodes"], kind
    assert not complaints(scene), (kind, complaints(scene))
    render.render_svg(S.normalize_scene(scene))  # must not raise


@pytest.mark.parametrize("kind", sorted(PROMPTS))
def test_each_builder_works_in_english_too(kind):
    prompts = {
        "flowchart": "Collect sample, extract DNA, run QC; if it passes, prepare the library, otherwise extract again",
        "workflow": "Dissect, extract RNA, prepare library, sequence, align, differential expression",
        "pathway": "EGF activates EGFR, EGFR phosphorylates RAS, RAS activates MEK, rapamycin inhibits mTOR",
        "abstract": "Title: gut flora and immunity\nBackground: imbalance drives inflammation\nMethods: 16S\nResults: fewer Treg\nConclusion: flora tunes immunity",
        "poster": "Title: single-cell sequencing of tumour heterogeneity\nBackground: tumours differ inside\nMethods: 10x\nResults: three subtypes\nConclusion: subtype drives resistance",
        "prisma": "1200 records identified, 900 after duplicates removed, 700 excluded by screening, 200 full texts assessed, 180 reports excluded, 20 studies included",
    }
    scene = BUILDERS[kind](offline.content_for(kind, prompts[kind]), "mono")
    assert scene["nodes"] and not complaints(scene)


@pytest.mark.parametrize("kind", ["flowchart", "workflow", "pathway", "abstract", "poster"])
def test_a_builder_says_so_rather_than_drawing_nothing(kind):
    with pytest.raises(ValueError):
        BUILDERS[kind]({}, None)


def test_an_empty_prisma_is_the_blank_form_to_fill_in():
    """PRISMA is the one template that is useful empty: every box, all "?"."""
    scene = build_prisma({}, None)
    assert len(scene["nodes"]) >= 10
    assert "?" in " ".join(n.get("text", "") for n in scene["nodes"])


def test_flowchart_decision_labels_sit_on_the_right_branches():
    scene = build_flowchart(FLOW_CONTENT, "ink")
    labels = {(e.get("label") or "") for e in scene["edges"]}
    assert {"yes", "no"} <= labels


def test_a_loop_back_connector_does_not_cross_a_box():
    scene = build_flowchart(FLOW_CONTENT, "ink")
    assert "edge_crosses" not in {i["code"] for i in lint.lint(S.normalize_scene(scene))}


def test_flowchart_direction_changes_the_layout():
    tb = build_flowchart(FLOW_CONTENT, "ink")
    lr = build_flowchart({**FLOW_CONTENT, "direction": "LR"}, "ink")
    assert lr["width"] > tb["width"] and lr["height"] < tb["height"]


def test_an_unknown_node_kind_becomes_a_plain_step():
    scene = build_flowchart({"nodes": [{"id": "a", "text": "x", "kind": "wormhole"}], "edges": []}, None)
    assert scene["nodes"][0]["type"] == "rect"


def test_a_very_long_flowchart_still_fits_its_canvas():
    content = {"nodes": [{"id": f"n{i}", "text": f"Step {i}"} for i in range(24)],
               "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(23)]}
    scene = build_flowchart(content, None)
    assert not complaints(scene)


def test_prisma_adds_up_the_numbers_and_complains_when_they_do_not():
    good = {"databases": 1200, "duplicates": 300, "screened": 900, "excluded": 700,
            "assessed": 200, "excluded_reports_total": 180, "included_studies": 20}
    numbers, notes = prisma_check(good)
    assert notes == []
    assert numbers["identified_total"] == 1200 and numbers["sought"] == 200
    # 900 screened minus 700 excluded leaves 200, not 50.
    _, notes = prisma_check(dict(good, sought=50))
    assert notes and "expected" in notes[0]


def test_prisma_fills_in_what_it_can_work_out():
    numbers, notes = prisma_check({"databases": 500, "duplicates": 100, "excluded": 300})
    assert numbers["screened"] == 400 and numbers["sought"] == 100 and notes == []


def test_prisma_flags_an_impossible_subtraction():
    _, notes = prisma_check({"databases": 100, "duplicates": 10, "excluded": 400})
    assert notes and "negative" in notes[0]


def test_the_parser_reads_what_is_left_after_de_duplication_not_the_duplicates():
    """"去重后 900" is 900 remaining, not 900 duplicates."""
    content = offline.prisma_content("检索到 1200 条记录，去重后 900 条，纳入 20 项研究")
    assert content["duplicates"] == 300 and content["screened"] == 900
    english = offline.prisma_content("1200 records identified, 900 after duplicates removed, 20 studies included")
    assert english["duplicates"] == 300 and english["screened"] == 900


def test_an_n_equals_number_is_not_mistaken_for_a_reason():
    content = offline.prisma_content("reports excluded (n = 180); studies included (n = 20)")
    assert not content.get("excluded_reports")
    assert content.get("excluded_reports_total") == 180


def test_prisma_builds_the_standard_two_column_shape():
    content = offline.content_for("prisma", PROMPTS["prisma"])
    scene = build_prisma(content, "ink")
    texts = " ".join(n.get("text", "") for n in scene["nodes"])
    assert "1,200" in texts and "20" in texts
    assert not complaints(scene)


def test_the_title_reaches_the_figure():
    scene = BUILDERS["flowchart"]({**FLOW_CONTENT, "title": "Figure 1. Workflow"}, None)
    assert "Figure 1. Workflow" in " ".join(n.get("text", "") for n in scene["nodes"])
    assert scene["title"] == "Figure 1. Workflow"
