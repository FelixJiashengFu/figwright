"""The MCP server, exercised through the same door a client uses: list the tools,
call them by name with a dict of arguments, read what comes back.

Two things matter beyond "it draws": every tool must hand back a path and a
picture (a client cannot carry a 3 MB file through a chat), and the file reader
must stay inside the folders the user could have opened themselves.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from figwright import mcp_server as M

TOOL_NAMES = {
    "list_capabilities", "generate_figure", "refine_figure", "build_template",
    "describe_template", "export_figure", "plot_table", "describe_table",
    "vectorize_image", "enhance_image", "lint_figure",
}


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A real server, with the working folder where a client's files would be."""
    monkeypatch.chdir(tmp_path)
    return M.build_server()


def call(server, name, **args):
    """Call a tool the way a client does, and fail loudly if it errored."""
    out = asyncio.run(server.call_tool(name, args))
    assert not getattr(out, "isError", False), f"{name} failed: {text_of(out)}"
    return out


def failure(server, name, **args) -> str:
    """What the client is told when a tool refuses. The SDK turns ToolError into
    a protocol error, so the message has to come out of the exception."""
    try:
        out = asyncio.run(server.call_tool(name, args))
    except M.ToolError as exc:
        return str(exc)
    assert getattr(out, "isError", False), f"{name} was expected to fail but returned {text_of(out)[:200]}"
    return text_of(out)


def text_of(out) -> str:
    return "\n".join(getattr(c, "text", "") for c in out.content)


def report(out) -> dict:
    """The JSON report every tool puts first."""
    return json.loads(next(c.text for c in out.content if getattr(c, "text", None)))


def images(out) -> list:
    return [c for c in out.content if getattr(c, "type", "") == "image" or getattr(c, "mimeType", "").startswith("image/")]


def saved(out) -> Path:
    return Path(report(out)["saved"])


# ------------------------------------------------------------------ the catalogue


def test_the_client_is_offered_every_tool(server):
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == TOOL_NAMES


def test_every_tool_explains_itself_to_a_model(server):
    """A model picks a tool from its description, so an empty one is a broken tool."""
    for tool in asyncio.run(server.list_tools()):
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.title and tool.input_schema["type"] == "object", tool.name


def test_the_server_tells_the_client_what_it_is_for(server):
    assert "generate_figure" in server.instructions
    assert server.name == "figwright"


def test_capabilities_list_what_can_be_asked_for(server):
    out = json.loads(text_of(call(server, "list_capabilities")))
    assert "flowchart" in out["figure_kinds"] and "prisma" in out["template_kinds"]
    assert "ink" in out["themes"] and "violin" in out["chart_kinds"]
    assert "pptx" in out["formats"] and out["journal_widths_mm"]
    assert out["offline_demo"] is True  # no key is configured in the tests
    assert Path(out["output_dir"]).is_dir()


def test_a_template_shape_is_a_worked_example(server):
    form = json.loads(text_of(call(server, "describe_template", kind="prisma")))
    assert form["content"]["en"] and form["content"]["zh"]


def test_an_unknown_template_lists_the_real_ones(server):
    assert "flowchart" in failure(server, "describe_template", kind="sankey")


# ------------------------------------------------------------------ drawing


def test_a_figure_is_drawn_saved_and_previewed(server):
    out = call(server, "generate_figure", prompt="采样、提取、质检，如果合格则测序，否则重新提取", kind="flowchart")
    rep = report(out)
    path = Path(rep["saved"])
    assert path.suffix == ".svg" and path.stat().st_size == rep["bytes"]
    assert rep["kind"] == "flowchart" and rep["provider"] in ("mock", "")
    assert any("offline demo" in n for n in rep["notes"])
    assert images(out), "the client gets nothing to look at"


def test_the_saved_figure_can_be_reopened_by_another_tool(server, tmp_path):
    first = saved(call(server, "generate_figure", prompt="采样、提取、测序", kind="flowchart"))
    out = call(server, "refine_figure", figure_file=str(first), instruction="字号改为 22")
    assert "style" not in report(out)  # the report stays small
    reopened = M.load_scene_file(str(saved(out)))
    assert reopened["style"]["fontSize"] == 22
    assert first.exists(), "the original must be left alone"


def test_a_template_is_laid_out_without_any_model(server):
    from figwright.examples import TEMPLATE_FORMS

    content = next(f for f in TEMPLATE_FORMS if f.get("kind") == "prisma")["content"]["en"]
    out = call(server, "build_template", kind="prisma", content=content)
    rep = report(out)
    assert Path(rep["saved"]).exists()
    assert not [i for i in rep.get("issues", []) if "overlap" in i]


def test_a_template_kind_that_does_not_exist_lists_the_ones_that_do(server):
    assert "flowchart" in failure(server, "build_template", kind="mindmap", content={})


def test_content_that_cannot_be_laid_out_says_why(server):
    assert failure(server, "build_template", kind="flowchart", content={"nodes": []})


@pytest.mark.parametrize("fmt", ["pptx", "png", "tiff", "pdf", "json", "html"])
def test_a_figure_is_exported_in_each_format(server, fmt):
    figure = saved(call(server, "generate_figure", prompt="采样、提取、测序", kind="flowchart"))
    out = call(server, "export_figure", figure_file=str(figure), format=fmt, dpi=120)
    path = saved(out)
    assert path.suffix.lstrip(".") == fmt and path.stat().st_size > 200


def test_a_journal_column_width_is_respected(server):
    figure = saved(call(server, "generate_figure", prompt="采样、提取、测序", kind="flowchart"))
    out = call(server, "export_figure", figure_file=str(figure), format="png", dpi=300, width_mm=89)
    from PIL import Image as PILImage

    with PILImage.open(saved(out)) as img:
        assert img.width == pytest.approx(89 / 25.4 * 300, rel=0.03)


def test_an_unsupported_format_lists_the_supported_ones(server):
    figure = saved(call(server, "generate_figure", prompt="采样、提取、测序", kind="flowchart"))
    assert "pptx" in failure(server, "export_figure", figure_file=str(figure), format="dwg")


def test_a_layout_check_reports_problems_and_can_fix_them(server, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"width": 240, "height": 120, "nodes": [
        {"id": "a", "type": "rect", "x": 20, "y": 20, "w": 90, "h": 40, "text": "much too long for this little box"},
        {"id": "b", "type": "rect", "x": 60, "y": 30, "w": 90, "h": 40, "text": "B"},
    ]}), "utf-8")
    found = json.loads(text_of(call(server, "lint_figure", figure_file=str(bad))))
    assert found["issues"] and any("overlap" in i["message"].lower() for i in found["issues"])
    fixed = report(call(server, "lint_figure", figure_file=str(bad), fix=True))
    assert Path(fixed["saved"]).exists()
    assert len(fixed["remaining"]) < len(found["issues"])


# ------------------------------------------------------------------ tables and images


def test_a_table_is_described_column_by_column(server, tmp_path, table_csv):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    out = json.loads(text_of(call(server, "describe_table", table_file=str(csv))))
    assert out["rows"] == 12
    assert {c["name"] for c in out["columns"]} == {"group", "dose", "value"}
    value = next(c for c in out["columns"] if c["name"] == "value")
    assert value["type"] == "number" and value["rows"] == 12 and value["examples"]


def test_a_chart_comes_back_with_its_statistics_and_caption(server, tmp_path, table_csv):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    out = call(server, "plot_table", table_file=str(csv), spec={"kind": "box", "stats": True})
    rep = report(out)
    assert rep["spec"]["kind"] == "box"
    assert rep["statistics"]["omnibus"]["p"] < 0.05
    assert "n =" in rep["caption"]
    assert images(out)


def test_a_chart_can_be_asked_for_in_words(server, tmp_path, table_csv):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    rep = report(call(server, "plot_table", table_file=str(csv), ask="按组画小提琴图，加上组间检验"))
    assert rep["spec"]["kind"] == "violin" and rep["spec"]["stats"] is True


def test_a_chart_can_be_a_native_powerpoint_chart(server, tmp_path, table_csv):
    import io

    from pptx import Presentation

    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    out = call(server, "plot_table", table_file=str(csv), format="pptx")
    deck = Presentation(io.BytesIO(saved(out).read_bytes()))
    assert any(s.has_chart for s in deck.slides[0].shapes)


def test_a_chart_format_that_makes_no_sense_is_refused(server, tmp_path, table_csv):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    assert "svg" in failure(server, "plot_table", table_file=str(csv), format="docx")


def test_a_picture_is_traced_into_shapes(server, tmp_path, shapes_png):
    src = tmp_path / "s.png"
    src.write_bytes(shapes_png)
    rep = report(call(server, "vectorize_image", image_file=str(src), colors=4))
    assert rep["colours"] and rep["points"] > 10
    assert "<path" in Path(rep["saved"]).read_text("utf-8")


def test_a_photo_is_cleaned_up_and_the_steps_are_listed(server, tmp_path, photo_png):
    src = tmp_path / "p.png"
    src.write_bytes(photo_png)
    out = call(server, "enhance_image", image_file=str(src), whiten=True, trim=True, width_mm=89, dpi=600)
    rep = report(out)
    assert rep["did"] and Path(rep["saved"]).exists()
    assert images(out)


def test_a_file_that_is_not_an_image_is_refused(server, tmp_path):
    src = tmp_path / "notes.png"
    src.write_text("not a picture at all", "utf-8")
    assert failure(server, "enhance_image", image_file=str(src))


# ------------------------------------------------------------------ reading files safely


def test_only_files_the_user_could_have_opened_are_read(tmp_path, monkeypatch):
    """A model should not be able to talk the server into reading /etc/shadow."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    inside = tmp_path / "ok.txt"
    inside.write_text("fine", "utf-8")
    assert M.read_input(str(inside)) == b"fine"
    assert M.read_input("ok.txt") == b"fine"  # relative to the working folder

    for bad in ("/etc/passwd", "/etc/hosts", "../../../../etc/passwd"):
        with pytest.raises(ValueError, match="only reads files"):
            M.read_input(bad)


def test_hidden_files_are_not_read(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    secret = tmp_path / ".ssh"
    secret.mkdir()
    (secret / "id_rsa").write_text("not a real key", "utf-8")
    with pytest.raises(ValueError, match="Hidden"):
        M.read_input(str(secret / "id_rsa"))
    dotfile = tmp_path / ".env"
    dotfile.write_text("OPENAI_API_KEY=sk-nope", "utf-8")
    with pytest.raises(ValueError, match="Hidden"):
        M.read_input(str(dotfile))


def test_a_symlink_out_of_the_folder_is_not_followed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    link = tmp_path / "shortcut.txt"
    link.symlink_to("/etc/hosts")
    with pytest.raises(ValueError):
        M.read_input(str(link))


def test_a_huge_file_is_refused_before_it_is_read(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    big = tmp_path / "big.tif"
    with big.open("wb") as fh:
        fh.truncate(M.MAX_READ_BYTES + 1)
    with pytest.raises(ValueError, match="larger than"):
        M.read_input(str(big))


def test_a_missing_file_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(ValueError, match="No such file"):
        M.read_input(str(tmp_path / "ghost.png"))


def test_a_file_that_is_not_a_figure_points_at_the_right_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    plain = tmp_path / "plain.svg"
    plain.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>', "utf-8")
    with pytest.raises(ValueError, match="import_picture|does not contain"):
        M.load_scene_file(str(plain))


# ------------------------------------------------------------------ file names


def test_a_saved_name_keeps_the_meaning_and_adds_the_time():
    name = M._safe_name("Figure 2 流程图", ".svg")
    assert name.startswith("Figure-2-流程图-") and name.endswith(".svg")
    assert len(name.split("-")[-2]) == 8  # the date


def test_a_name_from_a_model_cannot_escape_the_output_folder():
    for attempt in ("../../etc/passwd", "/absolute/evil", "..\\..\\windows", "a/b/c"):
        assert "/" not in M._safe_name(attempt, ".svg") and "\\" not in M._safe_name(attempt, ".svg")
    assert M._safe_name("", ".svg").startswith("figure-")
    assert M._safe_name("...", ".svg").startswith("figure-")


def test_a_timestamp_is_not_stacked_on_a_timestamp():
    """Round-tripping a file through the tools must not grow its name forever."""
    once = M._safe_name("pathway", ".svg")
    twice = M._safe_name(once[:-4], ".svg")
    assert twice.count("-2") == once.count("-2")
    assert len(twice) <= len(once) + 1


def test_a_long_name_is_cut_to_something_a_file_system_accepts():
    assert len(M._safe_name("长" * 300, ".svg")) < 100


def test_a_preview_is_small_enough_to_send(flow):
    img = M.preview(flow)
    assert img._format == "png" and len(img.data) < 900_000


def test_a_thumbnail_shrinks_a_big_picture(shapes_png):
    from figwright import raster

    big = raster.encode(raster.open_image(shapes_png).resize((3000, 2000)), "png")
    thumb = M.thumbnail(big)
    assert len(thumb.data) < len(big)
    assert max(raster.open_image(thumb.data).size) <= M.PREVIEW_SIDE


def test_the_output_folder_is_made_if_it_is_missing(tmp_path, monkeypatch):
    target = tmp_path / "deep" / "Figwright"
    monkeypatch.setenv("FIGWRIGHT_OUTPUT_DIR", str(target))
    assert M.output_dir() == target and target.is_dir()
