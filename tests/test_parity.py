"""The canvas in the browser and the exporter must draw the same picture.

The editor renders a scene in JavaScript; every export renders it in Python.
Both read the same scene JSON, so the only way to be sure that what you see is
what you get is to run them over the same scenes and diff the output.

Needs node on PATH; skipped when it is missing.
"""

from __future__ import annotations

import difflib
import json
import math
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from figwright import offline, render
from figwright.builders import BUILDERS
from figwright.geometry import fmt
from figwright.icons import icon_catalog
from figwright.scene import normalize_scene

HERE = Path(__file__).parent
SCRIPT = HERE / "parity" / "render_scenes.mjs"
node = shutil.which("node")
pytestmark = pytest.mark.skipif(not node, reason="node is not installed")

PROMPTS = {
    "flowchart": "样本采集 → DNA 提取 → 质检，如果合格则建库测序，否则重新提取 → 数据分析",
    "workflow": "取材、提取 RNA、建库、测序、比对、差异表达分析",
    "pathway": "EGF 激活 EGFR，EGFR 磷酸化 RAS，RAS 激活 MEK，MEK 激活 ERK，雷帕霉素抑制 mTOR",
    "abstract": "标题：肠道菌群与免疫\n背景：菌群失衡与炎症相关\n方法：16S 测序与流式\n结果：Treg 下降\n结论：菌群调节免疫",
    "poster": "题目：单细胞测序揭示肿瘤异质性\n背景：肿瘤内部差异大\n方法：10x 单细胞\n结果：三个亚群\n结论：亚群决定耐药",
    "prisma": "检索到 1200 条记录，去重后 900 条，筛选排除 700 条，全文评估 200 条，排除 180 条，纳入 20 项研究",
}


def every_shape_scene() -> dict:
    """One scene holding every node type, every routing and every arrow head."""
    return normalize_scene(
        {
            "width": 420,
            "height": 260,
            "nodes": [
                {"id": "a", "type": "rect", "x": 20, "y": 20, "w": 150, "h": 60, "text": "测试 Hello world wrapping here"},
                {"id": "b", "type": "diamond", "x": 230, "y": 100, "w": 150, "h": 80, "text": "决策？"},
                {"id": "c", "type": "icon", "x": 20, "y": 120, "w": 70, "h": 80, "icon": "dna", "text": "DNA"},
                {"id": "d", "type": "cylinder", "x": 110, "y": 120, "w": 90, "h": 70, "text": "DB"},
                {"id": "f", "type": "bilayer", "x": 220, "y": 20, "w": 180, "h": 34},
                {"id": "g", "type": "note", "x": 300, "y": 190, "w": 100, "h": 40, "text": "note here"},
                {"id": "t", "type": "triangle", "x": 20, "y": 200, "w": 80, "h": 40, "text": "T", "rotation": 12},
                {"id": "h", "type": "hexagon", "x": 120, "y": 200, "w": 90, "h": 44, "text": "hex"},
                {"id": "p", "type": "pill", "x": 230, "y": 200, "w": 60, "h": 30, "text": "pill"},
                {"id": "par", "type": "parallelogram", "x": 300, "y": 120, "w": 100, "h": 50, "text": "io"},
                {"id": "fr", "type": "frame", "x": 10, "y": 10, "w": 400, "h": 240, "text": "Panel a"},
                {"id": "pa", "type": "path", "x": 0, "y": 0, "w": 100, "h": 60, "d": "M0 0 L40 40 C60 10 80 50 100 0"},
            ],
            "edges": [
                {"id": "e1", "from": "a", "to": "b", "routing": "elbow", "label": "是"},
                {"id": "e2", "from": "d", "to": "b", "routing": "curve", "head": "inhibit"},
                {"id": "e3", "from": "c", "to": "a", "head": "both"},
                {"id": "e4", "from": "b", "to": "d", "routing": "elbow", "fromSide": "right", "toSide": "right"},
                {"id": "e5", "from": "p", "to": "par", "head": "circle", "dash": True},
                {"id": "e6", "from": "h", "to": [400, 250], "routing": "straight", "head": "none"},
            ],
        }
    )


def scenes() -> list[dict]:
    out = [every_shape_scene()]
    for kind, prompt in PROMPTS.items():
        out.append(normalize_scene(BUILDERS[kind](offline.content_for(kind, prompt), None)))
    return out


def run_js(payload: dict, tmp_path: Path) -> dict:
    src = tmp_path / "in.json"
    dst = tmp_path / "out.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run([node, str(SCRIPT), str(src), str(dst)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(dst.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def js_output(tmp_path_factory):
    random.seed(20261125)
    values = [0.0, -0.0, 1.0, 1.05, -1.25, 2.25, 1.75, 0.04, 1e-9, -1e-9, 123456.789, 1 / 3, math.pi, 2**31 + 0.5]
    values += [round(random.uniform(-5000, 5000), 4) for _ in range(4000)]
    values += [round(random.uniform(-10, 10), 2) for _ in range(4000)]
    values += [i / 4 for i in range(-2000, 2000)]  # every exact .25 / .5 / .75
    payload = {"icons": icon_catalog()["icons"], "scenes": scenes(), "values": values}
    out = run_js(payload, tmp_path_factory.mktemp("parity"))
    return values, out


def test_the_number_formatter_matches_python(js_output):
    values, out = js_output
    wrong = [(v, fmt(v), got) for v, got in zip(values, out["formatted"]) if fmt(v) != got]
    assert not wrong, f"{len(wrong)} of {len(values)} differ, e.g. {wrong[:5]}"


def test_every_scene_renders_identically(js_output):
    _, out = js_output
    for i, (sc, got) in enumerate(zip(scenes(), out["svgs"])):
        want = render.render_svg(sc, embed_scene=False)
        if want != got:
            diff = "\n".join(list(difflib.unified_diff(want.split(">"), got.split(">"), "python", "javascript", n=1))[:40])
            pytest.fail(f"scene {i} differs:\n{diff}")


def test_the_browser_module_exports_what_the_editor_imports():
    """A missing export shows up as a blank canvas, so check the list here."""
    text = (HERE.parent / "src" / "figwright" / "web" / "scene.js").read_text("utf-8")
    for name in ("renderSvg", "renderNode", "renderEdge", "sceneBounds", "pointInNode",
                 "distanceToEdge", "edgeGeometry", "visualBox", "setIcons", "fmt"):
        assert f"export function {name}" in text, name
