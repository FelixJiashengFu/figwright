"""Pictures in, pictures out: the clean-up pass, the tracer that turns a bitmap
into editable shapes, and the sketch reader.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from figwright import raster, scene as S, sketch, vectorize


def open_png(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# ------------------------------------------------------------------ clean-up


def test_a_picture_survives_an_empty_option_set(shapes_png):
    out, info = raster.enhance(shapes_png, {})
    assert open_png(out).size == (320, 240)
    assert info["width"] == 320 and info["format"] == "png"


def test_whitening_brightens_the_page_and_says_so(photo_png):
    out, info = raster.enhance(photo_png, {"whiten": True})
    before = np.asarray(open_png(photo_png).convert("L"), dtype=float)
    after = np.asarray(open_png(out).convert("L"), dtype=float)
    assert after.max() >= before.max()
    assert np.percentile(after, 90) > np.percentile(before, 90)
    assert any("whiten" in s for s in info["steps"])


def test_trimming_removes_the_empty_margin():
    img = np.full((120, 160, 3), 255, dtype=np.uint8)
    img[40:80, 60:100] = 20
    data = io.BytesIO()
    Image.fromarray(img).save(data, format="PNG")
    out, info = raster.enhance(data.getvalue(), {"trim": True})
    w, h = open_png(out).size
    assert w < 160 and h < 120 and w >= 40 and h >= 40
    assert any("trim" in s for s in info["steps"])


def test_removing_the_background_makes_it_transparent(shapes_png):
    out, info = raster.enhance(shapes_png, {"remove_bg": True})
    img = open_png(out)
    assert img.mode == "RGBA"
    assert np.asarray(img)[..., 3].min() == 0
    assert any("background" in s or "transparent" in s for s in info["steps"])


def test_upscaling_hits_the_requested_size_and_is_honest_about_it(shapes_png):
    out, info = raster.enhance(shapes_png, {"upscale": 2})
    assert open_png(out).size == (640, 480)
    assert any("interpolat" in n for n in info["notes"])


def test_a_print_width_and_dpi_give_the_right_pixel_count(shapes_png):
    out, info = raster.enhance(shapes_png, {"width_mm": 85, "dpi": 300})
    expect = round(85 / 25.4 * 300)
    assert abs(open_png(out).size[0] - expect) <= 1
    assert info["dpi"] == 300 and info["mm"][0] == pytest.approx(85, abs=0.6)


def test_the_dpi_is_written_into_the_file(shapes_png):
    out, _info = raster.enhance(shapes_png, {"dpi": 600})
    assert open_png(out).info.get("dpi", (0, 0))[0] == pytest.approx(600, abs=1)


@pytest.mark.parametrize("fmt", ["png", "jpeg", "tiff", "webp"])
def test_each_save_format_opens_again(shapes_png, fmt):
    out, info = raster.enhance(shapes_png, {"format": fmt})
    assert open_png(out).format.lower().startswith(fmt[:3])
    assert info["format"] == fmt


def test_jpeg_says_what_it_did_with_transparency(shapes_png):
    out, info = raster.enhance(shapes_png, {"remove_bg": True, "format": "jpeg"})
    assert open_png(out).mode in ("RGB", "L")
    assert any("transparen" in n for n in info["notes"])


def test_denoise_and_sharpen_change_the_picture_without_breaking_it(photo_png):
    out, info = raster.enhance(photo_png, {"denoise": 0.6, "sharpen": 0.5, "contrast": 0.4})
    assert open_png(out).size == open_png(photo_png).size
    assert len(info["steps"]) >= 3


def test_colour_blind_preview_is_marked_as_a_check_not_a_result(shapes_png):
    out, info = raster.enhance(shapes_png, {"cvd": "deuteranopia"})
    assert open_png(out).size == (320, 240)
    assert any("not for publication" in n or "preview" in n for n in info["steps"] + info["notes"])


def test_an_unknown_option_is_ignored(shapes_png):
    out, _info = raster.enhance(shapes_png, {"make_it_pop": True})
    assert open_png(out).size == (320, 240)


def test_a_file_that_is_not_an_image_is_refused():
    with pytest.raises(raster.ImageError):
        raster.enhance(b"not an image at all", {})


def test_crop_and_paste_a_region(shapes_png):
    patch = raster.crop(shapes_png, (40, 40, 160, 120))
    assert open_png(patch).size == (120, 80)
    back = raster.paste_region(shapes_png, patch, (40, 40, 160, 120))
    assert open_png(back).size == (320, 240)


def test_a_region_outside_the_picture_is_clamped(shapes_png):
    patch = raster.crop(shapes_png, (-50, -50, 10**6, 10**6))
    assert open_png(patch).size == (320, 240)


# ------------------------------------------------------------------ tracing


def test_tracing_finds_the_flat_colour_patches(shapes_png):
    result = vectorize.vectorize(shapes_png, colors=4, detail="medium")
    assert 2 <= len(result["layers"]) <= 4
    fills = {layer["fill"] for layer in result["layers"]}
    assert len(fills) == len(result["layers"])
    assert all(layer["d"].startswith("M") for layer in result["layers"])


def test_a_traced_picture_becomes_an_editable_scene(shapes_png):
    result = vectorize.vectorize(shapes_png, colors=4)
    sc = S.normalize_scene(vectorize.vector_scene(result, theme="ink", title="Traced"))
    paths = [n for n in sc["nodes"] if n["type"] == "path"]
    assert paths and all(n.get("vb") for n in paths)
    from figwright import render

    assert render.render_svg(sc, embed_scene=False).count("<path") >= len(paths)


def test_splitting_gives_one_shape_per_patch(shapes_png):
    result = vectorize.vectorize(shapes_png, colors=4)
    merged = vectorize.vector_nodes(result, split=False)[0]
    split = vectorize.vector_nodes(result, split=True)[0]
    assert len(split) >= len(merged)


def test_more_detail_means_more_points(shapes_png):
    coarse = vectorize.vectorize(shapes_png, colors=4, detail="low")
    fine = vectorize.vectorize(shapes_png, colors=4, detail="high")
    assert fine["points"] >= coarse["points"]


def test_tracing_says_what_it_could_not_keep(shapes_png):
    result = vectorize.vectorize(shapes_png, colors=4)
    assert any("outline" in n for n in result["notes"])  # text becomes outlines


def test_a_photograph_is_flagged_as_a_poor_fit():
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, (160, 160, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise).save(buf, format="PNG")
    result = vectorize.vectorize(buf.getvalue(), colors=6)
    assert any("gradient" in n or "photographic" in n for n in result["notes"])


def test_a_huge_picture_is_traced_at_a_sane_size():
    img = np.full((3000, 4000, 3), 240, dtype=np.uint8)
    img[500:2500, 500:3500] = (30, 60, 180)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    result = vectorize.vectorize(buf.getvalue(), colors=3, max_side=800)
    assert max(result["width"], result["height"]) <= 800
    assert any("traced at" in n for n in result["notes"])


def test_transparency_is_kept_when_tracing():
    rgba = np.zeros((80, 80, 4), dtype=np.uint8)
    rgba[20:60, 20:60] = (200, 40, 40, 255)
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    result = vectorize.vectorize(buf.getvalue(), colors=3)
    assert any("transparent" in n for n in result["notes"])


# ------------------------------------------------------------------ sketch


def test_a_sketch_of_two_boxes_and_an_arrow_is_read():
    img = np.full((300, 400), 255, dtype=np.uint8)
    for x0, x1 in ((30, 150), (250, 370)):
        img[80:160, x0:x1] = 255
        img[80:82, x0:x1] = 0
        img[158:160, x0:x1] = 0
        img[80:160, x0:x0 + 2] = 0
        img[80:160, x1 - 2:x1] = 0
    img[118:122, 150:250] = 0  # the arrow between them
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    hints = sketch.detect(buf.getvalue())
    assert len(hints["shapes"]) == 2 and all(s["type"] == "rect" for s in hints["shapes"])
    assert len(hints["links"]) == 1  # the arrow between them
    text = sketch.hints_text(hints)
    assert "rect" in text and "->" in text  # the model is told what was found


def test_a_sketch_becomes_a_starting_scene():
    img = np.full((200, 200), 255, dtype=np.uint8)
    img[50:100, 50:150] = 0
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    sc = S.normalize_scene(sketch.hints_to_scene(sketch.detect(buf.getvalue()), theme="ink"))
    assert sc["nodes"]


def test_a_blank_page_is_refused_politely():
    blank = np.full((100, 100), 255, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(blank).save(buf, format="PNG")
    hints = sketch.detect(buf.getvalue())
    assert hints["shapes"] == [] and hints["links"] == []
    assert hints["width"] == 100
