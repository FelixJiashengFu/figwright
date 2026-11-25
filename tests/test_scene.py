"""The scene model. A model's answer is never trusted: normalize_scene is the
gate that turns whatever came back into something the renderer can draw.
"""

from __future__ import annotations

import json

import pytest

from figwright import scene as S


def test_new_scene_has_a_style_and_no_content():
    sc = S.new_scene(theme="forest")
    assert sc["nodes"] == [] and sc["edges"] == []
    assert sc["style"]["fontFamily"] and sc["width"] > 0
    assert sc["style"]["theme"] == "forest"


def test_an_unknown_theme_name_falls_back_instead_of_failing():
    assert S.new_scene(theme="no-such-theme")["style"]["theme"] == "ink"


def test_normalize_keeps_good_nodes_and_drops_junk():
    sc = S.normalize_scene(
        {
            "nodes": [
                {"id": "a", "type": "box", "x": 0, "y": 0, "w": 100, "h": 40, "text": "ok"},
                "not a node",
                None,
                {"type": "nonsense-shape", "text": "unknown type becomes a box"},
            ],
            "edges": [{"from": "a", "to": "a"}, {"from": "a", "to": "ghost"}, 42],
        }
    )
    assert len(sc["nodes"]) == 2
    assert sc["nodes"][1]["type"] in S.NODE_TYPES
    # An edge to a node that does not exist cannot be drawn, so it goes.
    assert all(e["to"] in {n["id"] for n in sc["nodes"]} or isinstance(e["to"], list) for e in sc["edges"])


def test_ids_are_made_unique_and_never_empty():
    sc = S.normalize_scene({"nodes": [{"id": "a", "text": "1"}, {"id": "a", "text": "2"}, {"text": "3"}]})
    ids = [n["id"] for n in sc["nodes"]]
    assert len(set(ids)) == 3 and all(ids)


def test_numbers_that_arrive_as_strings_are_accepted():
    sc = S.normalize_scene({"nodes": [{"id": "a", "x": "10", "y": "20", "w": "100", "h": "50", "text": "x"}]})
    n = sc["nodes"][0]
    assert (n["x"], n["y"], n["w"], n["h"]) == (10.0, 20.0, 100.0, 50.0)


def test_nonsense_numbers_fall_back_to_a_usable_node():
    sc = S.normalize_scene({"nodes": [{"id": "a", "x": float("nan"), "w": -5, "h": "wide", "text": "x"}]})
    n = sc["nodes"][0]
    assert all(isinstance(n[k], float) or isinstance(n[k], int) for k in "xywh")
    assert n["w"] > 0 and n["h"] > 0 and n["x"] == n["x"]  # not NaN


def test_a_node_with_no_size_is_sized_to_fit_its_text():
    sc = S.normalize_scene({"nodes": [{"id": "a", "type": "box", "text": "a fairly long label that needs room"}]})
    short = S.normalize_scene({"nodes": [{"id": "b", "type": "box", "text": "hi"}]})
    assert sc["nodes"][0]["w"] > short["nodes"][0]["w"]


@pytest.mark.parametrize(
    "value,expected",
    [("#abc", "#aabbcc"), ("#AABBCC", "#aabbcc"), ("rgb(1,2,3)", "#010203"), ("none", "none"),
     ("transparent", "none"), ("url(#evil)", None), ("javascript:alert(1)", None), (42, None), ("", None)],
)
def test_colors_become_hex_or_nothing(value, expected):
    assert S.norm_color(value) == expected


def test_named_colors_are_resolved():
    assert S.norm_color("red", None).startswith("#")
    assert S.norm_color("not-a-colour", "#123456") == "#123456"


def test_a_script_in_a_label_is_escaped_when_drawn():
    from figwright import render

    sc = S.normalize_scene({"nodes": [{"id": "a", "text": "<script>bad()</script>", "href": "javascript:x"}]})
    assert not str(sc["nodes"][0].get("href", "")).lower().startswith("javascript")
    svg = render.render_svg(sc, embed_scene=False)
    assert "<script" not in svg and "&lt;script&gt;" in svg


@pytest.mark.parametrize("href", ["http://example.com/x.png", "https://example.com/x.png",
                                  "data:image/svg+xml,<svg onload=alert(1)/>", "file:///etc/passwd"])
def test_an_image_node_only_keeps_embedded_raster_data(href):
    """A figure must not fetch anything when someone opens it."""
    from figwright import render

    data = "data:image/png;base64,iVBORw0KGgo="
    keep = S.normalize_scene({"nodes": [{"id": "a", "type": "image", "href": data, "w": 10, "h": 10}]})
    assert keep["nodes"][0]["href"] == data
    drop = S.normalize_scene({"nodes": [{"id": "b", "type": "image", "href": href, "w": 10, "h": 10}]})
    assert not drop["nodes"][0].get("href")
    # And even if one got into a scene by another route, it is not drawn.
    sneaky = {**keep, "nodes": [dict(keep["nodes"][0], href=href)]}
    assert href not in render.render_svg(sneaky, embed_scene=False)


def test_bounds_and_bbox(tiny_scene):
    x0, y0, x1, y1 = S.scene_bounds(tiny_scene)
    assert (x0, y0) == (40, 60) and (x1, y1) == (540, 140)
    assert S.bbox(tiny_scene["nodes"][0]) == (40, 60, 180, 80)  # x, y, w, h
    assert S.scene_bounds(S.new_scene()) is None


def test_node_by_id(tiny_scene):
    index = S.node_by_id(tiny_scene)
    assert set(index) == {"a", "b"} and index["a"]["text"] == "Input"


def test_strip_and_restore_heavy_images():
    data = "data:image/png;base64," + "A" * 5000
    sc = S.normalize_scene({"nodes": [{"id": "a", "type": "image", "href": data, "w": 10, "h": 10}]})
    light = S.strip_heavy(sc)
    assert len(json.dumps(light)) < 1000
    back = S.restore_heavy(light, sc)
    assert back["nodes"][0]["href"] == data


def test_hash_ignores_key_order_but_not_content(tiny_scene):
    same = json.loads(json.dumps(tiny_scene, sort_keys=True))
    assert S.scene_hash(same) == S.scene_hash(tiny_scene)
    moved = json.loads(json.dumps(tiny_scene))
    moved["nodes"][0]["x"] += 1
    assert S.scene_hash(moved) != S.scene_hash(tiny_scene)


def test_compact_json_is_valid_and_small(tiny_scene):
    text = S.compact_json(tiny_scene)
    assert json.loads(text)["nodes"]
    assert "\n" not in text


def test_a_deeply_nested_answer_does_not_blow_the_stack():
    deep = {"nodes": [{"id": "a", "text": "x", "meta": None}]}
    cur = deep["nodes"][0]
    for _ in range(300):
        cur["meta"] = {"meta": None}
        cur = cur["meta"]
    sc = S.normalize_scene(deep)
    assert len(sc["nodes"]) == 1
