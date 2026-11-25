"""Demo mode: turning a sentence into a figure with no model at all.

This is what runs with no API key, and what a refusal falls back to, so the
text rules get the same scrutiny as the rest.
"""

from __future__ import annotations

import pytest

from figwright import offline, scene as S


def texts(content):
    return [n["text"] for n in content["nodes"]]


def labelled(content):
    return {(e.get("label") or "").lower(): e for e in content["edges"]}


# ------------------------------------------------------------------ language and kind


@pytest.mark.parametrize("text,lang", [
    ("请画一个流程图", "zh"), ("draw me a flowchart", "en"), ("样本 sample 混合", "zh"), ("", "en"),
])
def test_guess_lang(text, lang):
    assert offline.guess_lang(text) == lang


@pytest.mark.parametrize("prompt,kind", [
    ("画一个实验流程图", "flowchart"),
    ("draw a flow chart of the protocol", "flowchart"),
    ("EGF 激活 EGFR 的信号通路图", "pathway"),
    ("a signalling pathway for MAPK", "pathway"),
    ("做一张 graphical abstract", "abstract"),
    ("帮我排一张学术海报", "poster"),
    ("PRISMA 文献筛选流程", "prisma"),
    ("实验步骤：取材、固定、切片", "workflow"),
])
def test_guess_kind(prompt, kind):
    assert offline.guess_kind(prompt) == kind


def test_an_instruction_is_stripped_from_the_content():
    out = offline.strip_instruction("请帮我画一个流程图：采样、提取、测序")
    assert "请帮我画" not in out and "采样" in out


def test_an_explicit_title_is_pulled_out():
    title, rest = offline.explicit_title("标题：图1 实验流程\n采样、提取、测序")
    assert title == "图1 实验流程" and "标题" not in rest
    title, rest = offline.explicit_title("Title: Figure 1 workflow\nsample, extract")
    assert title == "Figure 1 workflow"


def test_no_title_means_no_guessing():
    title, rest = offline.explicit_title("采样、提取、测序")
    assert title == "" and rest.strip() == "采样、提取、测序"


# ------------------------------------------------------------------ splitting steps


@pytest.mark.parametrize("text,count", [
    ("采样、提取、测序", 3),
    ("采样，提取，测序", 3),
    ("采样 → 提取 → 测序", 3),
    ("1. 采样 2. 提取 3. 测序", 3),
    ("sample, extract, sequence", 3),
    ("sample -> extract -> sequence", 3),
    ("sample; extract; sequence", 3),
    ("- sample\n- extract\n- sequence", 3),
])
def test_split_steps_handles_the_usual_separators(text, count):
    assert len(offline.split_steps(text)) == count


def test_split_steps_keeps_a_decimal_number_whole():
    steps = offline.split_steps("离心 1,500 g 5 分钟、重悬、测序")
    assert len(steps) == 3 and "1,500" in steps[0]


def test_title_and_detail_are_separated():
    title, detail = offline.title_detail("DNA 提取：使用柱式试剂盒，洗脱 50 µL")
    assert title == "DNA 提取" and "柱式" in detail


# ------------------------------------------------------------------ flowchart clauses


CONDITIONALS = [
    ("采样、提取、质检，如果合格则建库测序，否则重新提取", "zh"),
    ("采样、提取、质检，若合格则建库测序，不合格则重新提取", "zh"),
    ("采样、提取、质检；合格的话就建库测序，否则重新提取", "zh"),
    ("Collect, extract, QC; if it passes, prepare the library, otherwise extract again", "en"),
    ("Collect, extract, QC: when the sample passes go to library prep, else re-extract", "en"),
]


@pytest.mark.parametrize("prompt,lang", CONDITIONALS)
def test_a_conditional_becomes_a_decision_with_two_branches(prompt, lang):
    content = offline.flowchart_content(prompt)
    kinds = [n.get("kind") for n in content["nodes"]]
    assert "decision" in kinds, texts(content)
    labels = labelled(content)
    assert ("是" in labels or "yes" in labels) and ("否" in labels or "no" in labels)
    assert offline.guess_lang(prompt) == lang


def test_a_negated_condition_puts_the_action_on_the_no_branch():
    """"若不合格则重新提取" asks "passed?" and loops back on no."""
    content = offline.flowchart_content("采样、提取、质检，若不合格则重新提取、建库测序")
    decision = next(n for n in content["nodes"] if n.get("kind") == "decision")
    assert "不" not in decision["text"]  # the question is asked in the positive
    no_edge = next(e for e in content["edges"] if (e.get("label") or "") in ("否", "no"))
    target = next(n for n in content["nodes"] if n["id"] == no_edge["to"])
    assert "提取" in target["text"]


def test_a_condition_with_no_otherwise_skips_straight_on():
    """"如果浑浊则过滤" means: filter when cloudy, carry on when not."""
    content = offline.flowchart_content("采样、提取、如果浑浊则过滤、测序")
    decision = next(n for n in content["nodes"] if n.get("kind") == "decision")
    no_edge = next(e for e in content["edges"] if e["from"] == decision["id"] and e.get("label") == "否")
    target = next(n for n in content["nodes"] if n["id"] == no_edge["to"])
    assert "测序" in target["text"]


def test_an_english_decision_is_phrased_as_a_question():
    content = offline.flowchart_content("Collect, extract, QC; if it passes, prepare the library, otherwise extract again")
    decision = next(n for n in content["nodes"] if n.get("kind") == "decision")
    assert decision["text"].endswith("?") and not decision["text"].lower().startswith("if")


def test_a_plain_chain_has_no_decision():
    content = offline.flowchart_content("采样、提取、建库、测序")
    assert not [n for n in content["nodes"] if n.get("kind") == "decision"]
    assert len(content["edges"]) == len(content["nodes"]) - 1


def test_the_first_and_last_steps_are_marked_as_start_and_end():
    content = offline.flowchart_content("采样、提取、建库、测序")
    assert content["nodes"][0].get("kind") == "start"
    assert content["nodes"][-1].get("kind") == "end"


def test_a_long_prompt_is_capped_rather_than_exploding():
    content = offline.flowchart_content("、".join(f"第{i}步" for i in range(60)))
    assert len(content["nodes"]) <= 16


# ------------------------------------------------------------------ pathway


def test_pathway_reads_activation_and_inhibition():
    content = offline.pathway_content("EGF 激活 EGFR，EGFR 磷酸化 RAS，雷帕霉素抑制 mTOR")
    names = {e["name"] for e in content["entities"]}
    assert {"EGF", "EGFR", "RAS", "mTOR"} <= names
    kinds = {r["type"] for r in content["relations"]}
    assert "inhibit" in kinds and "activate" in kinds


def test_pathway_works_in_english():
    content = offline.pathway_content("EGF activates EGFR, EGFR phosphorylates RAS, rapamycin inhibits mTOR")
    assert {"EGF", "EGFR", "RAS", "mTOR"} <= {e["name"] for e in content["entities"]}
    assert "inhibit" in {r["type"] for r in content["relations"]}


@pytest.mark.parametrize("name,kind", [
    ("EGFR", "receptor"), ("miR-21", "rna"), ("细胞核", "compartment"),
    ("雷帕霉素", "drug"), ("MEK", "kinase"), ("EGF", "ligand"), ("ATP", "molecule"),
])
def test_pathway_guesses_what_each_thing_is(name, kind):
    assert offline.guess_entity_type(name) == kind


@pytest.mark.parametrize("text,name,kind", [
    ("MEK inhibitor -| MEK", "MEK inhibitor", "drug"),
    ("IL-6 receptor binds IL-6", "IL-6 receptor", "receptor"),
    ("the EGF receptor activates RAS", "EGF receptor", "receptor"),
])
def test_a_role_word_stays_with_the_name_in_front_of_it(text, name, kind):
    """"MEK inhibitor" is one thing. Split in two, the drug disappears from the figure."""
    content = offline.pathway_content(text)
    entity = next((e for e in content["entities"] if e["name"] == name), None)
    assert entity and entity["type"] == kind, [e["name"] for e in content["entities"]]
    assert content["relations"], "the relation went missing with the name"


def test_a_verb_is_not_swallowed_into_the_name_before_it():
    content = offline.pathway_content("RAS activates RAF. RAF activates MEK")
    assert [e["name"] for e in content["entities"]] == ["RAS", "RAF", "MEK"]
    assert len(content["relations"]) == 2


def test_a_role_word_does_not_reach_across_a_line_break():
    """A new line starts a new statement: joining the two loses the boundary."""
    content = offline.pathway_content("EGF activates EGFR\nreceptor activates RAS")
    assert [e["name"] for e in content["entities"]] == ["EGF", "EGFR", "RAS"]


# ------------------------------------------------------------------ abstract / poster


def test_an_abstract_keeps_the_sections_it_was_given():
    content = offline.abstract_content("背景：菌群失衡\n方法：16S 测序\n结果：Treg 下降\n结论：菌群调节免疫")
    joined = " ".join(str(p) for p in content["panels"])
    assert "16S" in joined and "Treg" in joined
    assert len(content["panels"]) == 3  # the conclusion becomes the takeaway line
    assert "菌群调节免疫" in content["takeaway"]


def test_a_poster_without_headings_still_gets_sections():
    """One paragraph of prose is the poster's content, not its title."""
    content = offline.poster_content("我们用单细胞测序研究了肿瘤异质性，发现三个亚群，其中一个与耐药相关。")
    assert content["sections"] and "单细胞" in content["sections"][0]["body"]


def test_a_poster_keeps_the_title_authors_and_headings():
    content = offline.poster_content("题目：单细胞测序\n张三、李四\n多伦多大学\n背景：异质性\n方法：10x\n结果：三亚群")
    assert content["title"] == "单细胞测序"
    assert "张三" in content["authors"] and "多伦多" in content["affiliations"]
    assert [s["heading"] for s in content["sections"]] == ["背景", "方法", "结果"]


def test_source_text_reaches_the_poster():
    content = offline.poster_content("题目：XX 研究", source="方法：我们做了 10x 单细胞测序。结果：发现三个亚群。")
    assert "单细胞" in str(content)


# ------------------------------------------------------------------ refine ops


@pytest.mark.parametrize("instruction,op", [
    ("把 Input 改成蓝色", "update"),
    ("换成珊瑚配色主题", "set_theme"),
    ("用色盲友好配色", "set_theme"),
    ("make the text bigger", "set_style"),
    ("字号改为 20", "set_style"),
    ("线条加粗", "set_style"),
    ("标题改成 图1 流程", "set_title"),
    ("把 Input 改成 样本", "replace_text"),
    ("背景改成浅灰", "set_canvas"),
])
def test_refine_ops_understands_simple_instructions(tiny_scene, instruction, op):
    ops = offline.refine_ops(tiny_scene, instruction)
    assert ops and any(o.get("op") == op for o in ops), ops


def test_a_refine_op_round_trips_through_the_engine(tiny_scene):
    from figwright.ops import apply_ops

    ops = offline.refine_ops(tiny_scene, "字号改为 20")
    out, applied, errors = apply_ops(tiny_scene, ops)
    assert not errors and out["style"]["fontSize"] == 20


def test_refine_ops_is_empty_when_it_does_not_understand(tiny_scene):
    assert offline.refine_ops(tiny_scene, "请把这张图变得更有哲学意味") == []


def test_refine_ops_only_touches_nodes_that_exist(tiny_scene):
    ops = offline.refine_ops(tiny_scene, "把 Input 改成红色")
    ids = {o.get("id") for o in ops if "id" in o}
    assert ids <= {n["id"] for n in tiny_scene["nodes"]}


# ------------------------------------------------------------------ content_for


@pytest.mark.parametrize("kind", ["flowchart", "workflow", "pathway", "abstract", "poster", "prisma"])
def test_content_for_always_returns_something_buildable(kind):
    content = offline.content_for(kind, "采样、提取、测序")
    assert isinstance(content, dict) and content


def test_an_unknown_kind_falls_back_to_a_concept_map():
    sc = offline.concept_map("光合作用包括光反应和暗反应")
    assert S.normalize_scene(sc)["nodes"]
