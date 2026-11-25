"""Rendering: the SVG must be well formed, carry its own scene back, and
rasterise. These tests also pin the promises the export dialog makes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from figwright import render, scene as S
from figwright.themes import THEMES, retheme


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_svg_is_well_formed_xml(flow):
    root = parse(render.render_svg(flow))
    assert root.tag.endswith("svg")
    assert root.get("viewBox")


def test_every_node_is_drawn_with_its_id(flow):
    svg = render.render_svg(flow)
    for node in flow["nodes"]:
        assert f'data-id="{node["id"]}"' in svg


def test_text_is_escaped_not_injected():
    sc = S.normalize_scene({"nodes": [{"id": "a", "text": 'a & b < c > "d"', "w": 300, "h": 80}]})
    svg = render.render_svg(sc, embed_scene=False)
    parse(svg)  # would raise if the ampersand were left raw
    assert "&amp;" in svg


def test_the_scene_rides_along_in_the_svg_and_comes_back(flow):
    svg = render.render_svg(flow, embed_scene=True)
    back = render.extract_scene_from_svg(svg)
    assert back and len(back["nodes"]) == len(flow["nodes"])
    assert S.scene_hash(back) == S.scene_hash(flow)


def test_a_plain_svg_has_no_scene_to_extract():
    assert render.extract_scene_from_svg('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>') is None


def test_an_embedded_picture_is_lifted_out_of_the_json_and_put_back():
    data = "data:image/png;base64," + "A" * 2000
    sc = S.normalize_scene({"nodes": [{"id": "pic", "type": "image", "href": data, "x": 0, "y": 0, "w": 100, "h": 100}]})
    svg = render.render_svg(sc, embed_scene=True)
    # The big base64 string appears once (in the <image>), not twice.
    assert svg.count("A" * 2000) == 1
    back = render.extract_scene_from_svg(svg)
    assert back["nodes"][0]["href"] == data


def test_scale_changes_the_pixel_size_but_not_the_coordinates(flow):
    small = parse(render.render_svg(flow, scale=1.0))
    big = parse(render.render_svg(flow, scale=2.0))
    assert small.get("viewBox") == big.get("viewBox")
    assert float(big.get("width").rstrip("px")) == pytest.approx(2 * float(small.get("width").rstrip("px")))


def test_sticky_notes_stay_out_of_the_figure_unless_asked_for(flow):
    """A note is a message to a co-author, not part of the published figure."""
    flow["nodes"].append({"id": "memo", "type": "note", "x": 10, "y": 10, "w": 160, "h": 60, "text": "ask the vet"})
    assert "ask the vet" not in render.render_svg(flow, embed_scene=False)
    assert "ask the vet" in render.render_svg(flow, embed_scene=False, include_notes=True)


def test_png_rendering_produces_a_real_png(tiny_scene):
    png = render.render_png(tiny_scene, scale=1.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    bigger = render.render_png(tiny_scene, scale=2.0)
    assert len(bigger) > len(png)


@pytest.mark.parametrize("theme", list(THEMES))
def test_every_theme_renders(flow, theme):
    svg = render.render_svg(retheme(flow, theme), embed_scene=False)
    parse(svg)
    assert len(svg) > 500


def test_retheme_changes_colours_but_keeps_the_content(flow):
    other = retheme(flow, "coral")
    assert [n["text"] for n in other["nodes"]] == [n["text"] for n in flow["nodes"]]
    assert other["style"]["theme"] == "coral"
    assert other["style"]["stroke"] != flow["style"]["stroke"]


def test_sanitizer_strips_scripts_entities_and_remote_links():
    dirty = (
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        '<svg xmlns="http://www.w3.org/2000/svg"><script>evil()</script>'
        '<image href="http://tracker.example/p.png"/><rect fill="url(http://x/y)"/>'
        '<foreignObject><iframe src="x"/></foreignObject><circle r="5"/></svg>'
    )
    with pytest.raises(ValueError):
        render.sanitize_foreign_svg(dirty)  # entity declarations are refused outright
    clean = render.sanitize_foreign_svg(dirty.replace('<!ENTITY x SYSTEM "file:///etc/passwd">', ""))
    assert "<script" not in clean and "foreignObject" not in clean.lower()
    assert "tracker.example" not in clean
    assert "circle" in clean


def test_a_foreign_svg_can_be_rasterised():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="#333"/></svg>'
    png = render.foreign_svg_to_png(svg)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_file_that_is_not_an_svg_is_refused():
    with pytest.raises(ValueError):
        render.foreign_svg_to_png("just some text")


def test_ids_in_the_svg_are_unique(flow):
    svg = render.render_svg(flow)
    ids = re.findall(r'\sid="([^"]+)"', svg)
    assert len(ids) == len(set(ids))
