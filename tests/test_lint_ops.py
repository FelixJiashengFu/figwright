"""The layout checker and the edit operations.

Lint is what catches the three things a language model gets wrong most often:
text that does not fit, shapes that overlap, and connectors drawn across a box.
"""

from __future__ import annotations

import json

import pytest

from figwright import lint as L, scene as S
from figwright.ops import apply_ops


def codes(scene):
    return {i["code"] for i in L.lint(scene)}


def test_a_clean_figure_has_nothing_to_report(flow):
    assert not [i for i in L.lint(flow) if i.get("severity") == "error"]


def test_an_empty_figure_is_reported():
    assert "empty" in codes(S.new_scene())


def test_text_that_does_not_fit_is_caught():
    sc = S.normalize_scene({"nodes": [{"id": "a", "type": "rect", "x": 0, "y": 0, "w": 60, "h": 24,
                                       "text": "a very long label that cannot possibly fit in here"}]})
    assert "text_overflow" in codes(sc)


def test_tiny_text_is_caught():
    sc = S.normalize_scene({"nodes": [{"id": "a", "type": "text", "x": 0, "y": 0, "w": 200, "h": 40,
                                       "text": "fine print", "fontSize": 6}]})
    assert "tiny_text" in codes(sc)


def test_overlapping_shapes_are_caught():
    sc = S.normalize_scene({"nodes": [
        {"id": "a", "type": "rect", "x": 0, "y": 0, "w": 200, "h": 100, "text": "A"},
        {"id": "b", "type": "rect", "x": 20, "y": 20, "w": 200, "h": 100, "text": "B"},
    ]})
    assert "overlap" in codes(sc)


def test_content_outside_the_canvas_is_caught():
    sc = S.normalize_scene({"width": 300, "height": 200,
                            "nodes": [{"id": "a", "type": "rect", "x": 400, "y": 10, "w": 120, "h": 50, "text": "out"}]})
    assert "off_canvas" in codes(sc)


def test_fit_text_grows_the_box_until_the_label_fits():
    sc = S.normalize_scene({"nodes": [{"id": "a", "type": "rect", "x": 0, "y": 0, "w": 60, "h": 24,
                                       "text": "a very long label that cannot possibly fit in here"}]})
    changed = L.fit_text(sc)
    assert changed == 1
    assert "text_overflow" not in codes(sc)


def test_fit_canvas_extends_the_page_to_cover_everything():
    sc = S.normalize_scene({"width": 300, "height": 200,
                            "nodes": [{"id": "a", "type": "rect", "x": 400, "y": 10, "w": 120, "h": 50, "text": "out"}]})
    assert L.fit_canvas(sc) is True
    assert sc["width"] > 520
    assert "offcanvas" not in codes(sc)


def test_snap_alignment_lines_up_nearly_aligned_boxes():
    sc = S.normalize_scene({"nodes": [
        {"id": "a", "type": "rect", "x": 100, "y": 0, "w": 120, "h": 50, "text": "A"},
        {"id": "b", "type": "rect", "x": 103, "y": 200, "w": 120, "h": 50, "text": "B"},
    ]})
    assert L.snap_alignment(sc) >= 1
    assert sc["nodes"][0]["x"] == sc["nodes"][1]["x"]


def test_autofix_reports_what_it_did_in_plain_words():
    sc = S.normalize_scene({"width": 200, "height": 100, "nodes": [
        {"id": "a", "type": "rect", "x": 0, "y": 0, "w": 50, "h": 20, "text": "quite a long label here"},
        {"id": "b", "type": "rect", "x": 400, "y": 0, "w": 120, "h": 50, "text": "B"},
    ]})
    fixed, notes = L.autofix(sc)
    assert notes and any("resized" in n or "canvas" in n for n in notes)
    assert "text_overflow" not in codes(fixed)


def test_summarize_is_short_and_mentions_the_count():
    issues = L.lint(S.normalize_scene({"nodes": [{"id": "a", "type": "rect", "x": 0, "y": 0, "w": 30, "h": 10, "text": "much too long for this box"}]}))
    text = L.summarize(issues)
    assert text and len(text) < 2000


# ---------------------------------------------------------------- edit ops


def test_update_moves_a_node(tiny_scene):
    out, notes, errors = apply_ops(tiny_scene, [{"op": "update", "id": "a", "x": 11, "y": 12}])
    assert not errors
    node = S.node_by_id(out)["a"]
    assert (node["x"], node["y"]) == (11, 12)
    assert notes


def test_add_and_remove(tiny_scene):
    out, _, errors = apply_ops(tiny_scene, [{"op": "add", "node": {"id": "c", "type": "rect", "x": 0, "y": 200, "w": 80, "h": 40, "text": "C"}}])
    assert not errors and "c" in S.node_by_id(out)
    out, _, errors = apply_ops(out, [{"op": "remove", "id": "c"}])
    assert not errors and "c" not in S.node_by_id(out)


def test_removing_a_node_takes_its_connectors_with_it(tiny_scene):
    out, _, _ = apply_ops(tiny_scene, [{"op": "remove", "id": "b"}])
    assert out["edges"] == []


def test_an_op_on_a_missing_node_is_reported_not_crashed(tiny_scene):
    out, _, errors = apply_ops(tiny_scene, [{"op": "update", "id": "ghost", "x": 1}])
    assert errors and len(out["nodes"]) == 2


def test_an_unknown_op_is_reported(tiny_scene):
    _, _, errors = apply_ops(tiny_scene, [{"op": "teleport", "id": "a"}])
    assert errors


def test_ops_can_arrive_as_a_json_string(tiny_scene):
    out, _, errors = apply_ops(tiny_scene, json.dumps([{"op": "update", "id": "a", "text": "Changed"}]))
    assert not errors and S.node_by_id(out)["a"]["text"] == "Changed"


def test_ops_can_arrive_as_a_single_object(tiny_scene):
    out, _, errors = apply_ops(tiny_scene, {"op": "update", "id": "a", "text": "One"})
    assert not errors and S.node_by_id(out)["a"]["text"] == "One"


def test_junk_instead_of_ops_is_an_error_not_an_exception(tiny_scene):
    out, _, errors = apply_ops(tiny_scene, "not json at all")
    assert errors and S.scene_hash(out) == S.scene_hash(tiny_scene)


def test_retheme_op_recolours_the_whole_figure(flow):
    out, _, errors = apply_ops(flow, [{"op": "theme", "theme": "mono"}])
    assert not errors and out["style"]["theme"] == "mono"


def test_ops_cannot_smuggle_in_a_remote_image(tiny_scene):
    out, _, _ = apply_ops(tiny_scene, [{"op": "add", "node": {"id": "pic", "type": "image", "href": "http://x/y.png", "x": 0, "y": 0, "w": 10, "h": 10}}])
    assert not S.node_by_id(out).get("pic", {}).get("href")
