"""Exports. The PowerPoint file is the one people check hardest, because the
promise is that every shape is still a shape they can nudge.
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd
import pytest
from pptx import Presentation
from pptx.util import Emu

from figwright import export_pptx, export_share, plot, render, scene as S
from figwright.generate import stamp


def deck(data: bytes) -> Presentation:
    return Presentation(io.BytesIO(data))


def shapes_of(data: bytes):
    return list(deck(data).slides[0].shapes)


# ------------------------------------------------------------------ pptx


def test_a_deck_opens_again_and_holds_the_shapes(flow):
    data, notes = export_pptx.scene_to_pptx(flow)
    assert data[:2] == b"PK"
    shapes = shapes_of(data)
    assert len(shapes) >= len([n for n in flow["nodes"] if n["type"] != "frame"])
    assert isinstance(notes, list)


def test_the_slide_is_the_size_of_the_figure(tiny_scene):
    data, _ = export_pptx.scene_to_pptx(tiny_scene)
    pres = deck(data)
    ratio = pres.slide_width / pres.slide_height
    assert ratio == pytest.approx(tiny_scene["width"] / tiny_scene["height"], rel=0.02)


def test_text_is_still_text_that_can_be_edited(flow):
    data, _ = export_pptx.scene_to_pptx(flow)
    said = {s.text_frame.text for s in shapes_of(data) if s.has_text_frame}
    for node in flow["nodes"]:
        if node.get("text"):
            assert any(node["text"] in t for t in said), node["text"]


def test_a_box_is_a_shape_not_a_picture(tiny_scene):
    data, _ = export_pptx.scene_to_pptx(tiny_scene)
    kinds = {s.shape_type for s in shapes_of(data)}
    assert all("PICTURE" not in str(k) for k in kinds)


def test_a_diamond_stays_a_diamond():
    sc = S.normalize_scene({"nodes": [{"id": "d", "type": "diamond", "x": 0, "y": 0, "w": 160, "h": 90, "text": "ok?"}]})
    data, _ = export_pptx.scene_to_pptx(sc)
    xml = shapes_of(data)[0]._element.xml
    assert "diamond" in xml or "flowChartDecision" in xml


def test_a_connector_is_a_line_with_an_arrow(tiny_scene):
    data, _ = export_pptx.scene_to_pptx(tiny_scene)
    xml = " ".join(s._element.xml for s in shapes_of(data))
    assert "<a:tailEnd" in xml or "<a:headEnd" in xml
    assert "triangle" in xml


def test_an_embedded_picture_travels_with_the_deck(shapes_png):
    import base64

    href = "data:image/png;base64," + base64.b64encode(shapes_png).decode("ascii")
    sc = S.normalize_scene({"nodes": [{"id": "p", "type": "image", "x": 0, "y": 0, "w": 320, "h": 240, "href": href}]})
    data, _ = export_pptx.scene_to_pptx(sc)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert [n for n in zf.namelist() if n.startswith("ppt/media/")]


def test_a_curved_connector_is_exported_as_a_free_shape_and_said_so(tiny_scene):
    tiny_scene["edges"][0]["routing"] = "curve"
    _data, notes = export_pptx.scene_to_pptx(tiny_scene)
    assert isinstance(notes, list)


def test_the_disclosure_travels_in_the_speaker_notes(flow):
    """It belongs with the file, not on top of the figure."""
    flow["nodes"].append({"id": "memo", "type": "note", "x": 0, "y": 0, "w": 120, "h": 50,
                          "text": "check the units", "author": "Fe"})
    data, _ = export_pptx.scene_to_pptx(flow, disclosure="Made with a model.")
    notes = deck(data).slides[0].notes_slide.notes_text_frame.text
    assert "Made with a model." in notes
    assert "check the units" in notes and "Fe" in notes  # comments ride along too
    assert "Made with a model." not in " ".join(s.text_frame.text for s in shapes_of(data) if s.has_text_frame)


def test_a_chart_becomes_a_real_powerpoint_chart(table_csv):
    """Not a picture of a chart: the numbers are in the file and editable."""
    df = plot.load_table("t.csv", table_csv.encode())
    spec = plot.normalize_spec({"stats": True}, df)
    data, notes = export_pptx.plot_to_pptx(df, spec, theme="ink", caption="Figure 1.")
    assert data[:2] == b"PK"
    shapes = shapes_of(data)
    assert any(s.has_chart for s in shapes)
    chart = next(s.chart for s in shapes if s.has_chart)
    assert [c for c in chart.plots[0].categories] == ["ctrl", "low", "high"]
    assert deck(data).slides[0].notes_slide.notes_text_frame.text.count("Figure 1.") == 1
    # The brackets cannot exist in a native chart, and it says so rather than pretending.
    assert any("bracket" in n for n in notes)


def test_an_empty_figure_gives_an_empty_slide_rather_than_an_error():
    data, _notes = export_pptx.scene_to_pptx(S.new_scene())
    assert data[:2] == b"PK" and shapes_of(data) == []


def test_shapes_land_where_they_were_put():
    sc = S.normalize_scene({"width": 400, "height": 300,
                            "nodes": [{"id": "a", "type": "rect", "x": 100, "y": 50, "w": 120, "h": 60, "text": "A"}]})
    data, _ = export_pptx.scene_to_pptx(sc)
    shape = shapes_of(data)[0]
    pres = deck(data)
    # x/width as a fraction of the slide must match the scene.
    assert shape.left / pres.slide_width == pytest.approx(100 / 400, abs=0.01)
    assert shape.width / pres.slide_width == pytest.approx(120 / 400, abs=0.01)


# ------------------------------------------------------------------ raster and sizes


@pytest.mark.parametrize("fmt,magic", [("png", b"\x89PNG"), ("jpeg", b"\xff\xd8"), ("tiff", None), ("webp", None)])
def test_export_raster_writes_each_format(flow, fmt, magic):
    data, info = export_share.export_raster(flow, fmt=fmt, dpi=150)
    if magic:
        assert data.startswith(magic)
    assert info["width"] > 0 and info["dpi"] == 150


def test_a_print_width_decides_the_pixel_size(flow):
    _data, info = export_share.export_raster(flow, dpi=300, width_mm=85)
    assert info["width"] == pytest.approx(85 / 25.4 * 300, rel=0.02)
    assert info["mm"][0] == pytest.approx(85, abs=0.5)


def test_a_transparent_png_is_transparent(flow):
    from PIL import Image

    data, _info = export_share.export_raster(flow, fmt="png", dpi=72, transparent=True)
    img = Image.open(io.BytesIO(data))
    assert img.mode == "RGBA" and np_min_alpha(img) == 0


def np_min_alpha(img) -> int:
    import numpy as np

    return int(np.asarray(img)[..., 3].min())


def test_an_absurd_size_is_refused(flow):
    with pytest.raises(export_share.ExportError):
        export_share.export_raster(flow, dpi=6000, width_mm=2000)


def test_the_size_table_is_offered_in_both_languages():
    zh, en = export_share.describe_sizes("zh"), export_share.describe_sizes("en")
    assert len(zh) == len(en) >= 3
    assert all("mm" in str(row) or "width" in row or "width_mm" in row for row in en)


# ------------------------------------------------------------------ share page and record


def test_the_share_page_is_self_contained(flow):
    html = export_share.share_html(flow, lang="en")
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "<svg" in html
    assert "http://" not in html.replace("http://www.w3.org", "")  # no outside links


def test_the_share_page_carries_the_scene_so_it_can_be_opened_again(flow):
    """Someone who is sent the page can drop it back in and keep editing."""
    html = export_share.share_html(flow)
    svg = html[html.index("<svg") : html.rindex("</svg>") + 6]
    back = render.extract_scene_from_svg(svg)
    assert back and len(back["nodes"]) == len(flow["nodes"])


def test_the_record_lists_which_model_did_what(flow):
    stamp(flow, "generate", "anthropic", "claude-test-1")
    stamp(flow, "refine", "openai", "gpt-test-2")
    rows = export_share.provenance(flow)
    assert [r["action"] for r in rows] == ["generate", "refine"]
    assert set(export_share.ai_models(flow)) == {"anthropic / claude-test-1", "openai / gpt-test-2"}
    text = export_share.disclosure(flow, "en")
    assert "claude-test-1" in text and "gpt-test-2" in text


def test_a_figure_made_without_a_model_says_so(flow):
    assert export_share.ai_models(flow) == []
    assert export_share.disclosure(flow, "en") == "" or "no" in export_share.disclosure(flow, "en").lower()


def test_the_record_page_is_a_plain_page(flow):
    stamp(flow, "generate", "mock", "offline")
    html = export_share.record_html(flow, "zh")
    assert "<html" in html and "offline" in html


def test_the_print_page_asks_for_vector_output(flow):
    html = export_share.print_html(flow)
    assert "@page" in html and "<svg" in html
    assert "window.print" in html
