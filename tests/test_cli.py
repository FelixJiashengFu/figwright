"""The command line. Every subcommand is exercised, because a script that fails
quietly is worse than no script. ``serve`` is the one exception: it is tested
through its own helpers, since starting a server inside a test never ends well.
"""

from __future__ import annotations

import io
import json

import pytest

from figwright import cli


def run(*args, expect=0):
    code = cli.main(list(args))
    assert code == expect, f"{args} exited {code}"
    return code


def read(path):
    return json.loads(path.read_text("utf-8"))


def scene_file(tmp_path, scene, name="fig.json"):
    path = tmp_path / name
    path.write_text(json.dumps(scene, ensure_ascii=False), "utf-8")
    return path


# ------------------------------------------------------------------ the parser itself


def test_the_version_is_printed_and_the_program_stops(capsys):
    with pytest.raises(SystemExit) as exit:
        cli.main(["--version"])
    assert exit.value.code == 0
    assert "figwright" in capsys.readouterr().out.lower()


def test_every_subcommand_is_reachable():
    actions = cli.build_parser()._subparsers._group_actions[0].choices
    assert set(actions) == {"serve", "generate", "refine", "export", "template", "lint",
                            "plot", "vectorize", "enhance", "config", "doctor", "mcp"}


def test_an_unknown_subcommand_is_refused(capsys):
    with pytest.raises(SystemExit) as exit:
        cli.main(["teleport"])
    assert exit.value.code != 0
    assert capsys.readouterr().err


def test_every_subcommand_explains_itself():
    """A help text with no examples is how a tool goes unused."""
    text = cli.build_parser().format_help()
    for word in ("generate", "export", "plot", "doctor"):
        assert word in text
    assert "figwright" in cli.__doc__ and "-o fig.pptx" in cli.__doc__


def test_listening_on_the_network_is_not_something_you_do_by_accident():
    args = cli.build_parser().parse_args(["serve", "--host", "0.0.0.0"])
    with pytest.raises(cli.CliError) as err:
        cli.cmd_serve(args)
    assert "allow-remote" in str(err.value)


def test_a_busy_port_is_stepped_over():
    import socket

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        port = taken.getsockname()[1]
        taken.listen(1)
        assert cli._free_port("127.0.0.1", port) == port + 1


# ------------------------------------------------------------------ generate, refine, export


def test_generate_writes_an_editable_figure(tmp_path):
    out = tmp_path / "fig.json"
    run("generate", "采样、提取、质检，如果合格则测序，否则重新提取", "--kind", "flowchart", "-o", str(out))
    scene = read(out)["scene"]
    assert scene["nodes"] and any(n["type"] == "diamond" for n in scene["nodes"])


def test_generate_can_write_the_picture_straight_away(tmp_path):
    out = tmp_path / "fig.svg"
    run("generate", "采样、提取、测序", "--kind", "flowchart", "-o", str(out))
    svg = out.read_text("utf-8")
    assert svg.lstrip().startswith("<") and "测序" in svg


def test_generate_can_take_its_content_from_a_document(tmp_path):
    source = tmp_path / "methods.md"
    source.write_text("# Methods\n\nSamples were collected, then extracted, then sequenced.\n", "utf-8")
    out = tmp_path / "fig.json"
    run("generate", "draw the methods as a flowchart", "--kind", "flowchart", "--source", str(source), "-o", str(out))
    text = json.dumps(read(out), ensure_ascii=False).lower()
    assert "extract" in text or "sequenc" in text


def test_an_unknown_output_format_is_refused_before_any_work(tmp_path, capsys):
    assert cli.main(["generate", "采样、测序", "-o", str(tmp_path / "fig.dwg")]) == 1
    assert ".dwg" in capsys.readouterr().err


def test_refine_changes_the_figure_in_place(tmp_path, flow):
    path = scene_file(tmp_path, flow)
    run("refine", str(path), "字号改为 20", "-o", str(path))
    assert read(path)["scene"]["style"]["fontSize"] == 20


def test_refine_without_an_output_overwrites_the_input(tmp_path, flow):
    path = scene_file(tmp_path, flow)
    run("refine", str(path), "换成珊瑚配色")
    assert read(path)["scene"]["style"]["theme"] == "coral"


@pytest.mark.parametrize("fmt", ["svg", "png", "jpg", "tif", "webp", "pdf", "pptx", "json", "html"])
def test_export_writes_every_format_it_offers(tmp_path, flow, fmt):
    src = scene_file(tmp_path, flow)
    out = tmp_path / f"figure.{fmt}"
    run("export", str(src), "-o", str(out), "--dpi", "120")
    assert out.exists() and out.stat().st_size > 200


def test_export_says_where_it_put_the_file(tmp_path, flow, capsys):
    src = scene_file(tmp_path, flow)
    run("export", str(src), "-o", str(tmp_path / "out.png"), "--dpi", "96")
    said = capsys.readouterr().err
    assert "out.png" in said and "px" in said and "mm" in said


def test_export_can_recolour_on_the_way_out(tmp_path, flow):
    src = scene_file(tmp_path, flow)
    out = tmp_path / "mono.json"
    run("export", str(src), "-o", str(out), "--theme", "mono")
    scene = read(out)["scene"]
    assert scene["style"]["theme"] == "mono"
    assert scene["style"]["palette"] != flow["style"]["palette"]


def test_a_figure_can_be_reopened_from_the_svg_it_wrote(tmp_path, flow):
    """The promise of the whole format: the SVG is the save file."""
    src = scene_file(tmp_path, flow)
    svg = tmp_path / "round.svg"
    run("export", str(src), "-o", str(svg))
    back = tmp_path / "back.json"
    run("export", str(svg), "-o", str(back))
    assert len(read(back)["scene"]["nodes"]) == len(flow["nodes"])


def test_a_picture_that_figwright_did_not_make_is_explained_not_just_rejected(tmp_path, capsys):
    plain = tmp_path / "plain.svg"
    plain.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>', "utf-8")
    assert cli.main(["export", str(plain), "-o", str(tmp_path / "x.png")]) == 1
    assert "vectorize" in capsys.readouterr().err


def test_a_missing_input_file_is_reported(tmp_path, capsys):
    assert cli.main(["export", str(tmp_path / "nope.json"), "-o", str(tmp_path / "x.svg")]) == 1
    assert "nope.json" in capsys.readouterr().err


def test_a_file_that_is_not_a_figure_is_reported(tmp_path, capsys):
    path = tmp_path / "x.json"
    path.write_text("[1, 2, 3]", "utf-8")
    assert cli.main(["export", str(path), "-o", str(tmp_path / "x.svg")]) == 1
    assert "not made by Figwright" in capsys.readouterr().err


def test_broken_json_is_reported_with_the_reason(tmp_path, capsys):
    path = tmp_path / "x.json"
    path.write_text('{"nodes": [', "utf-8")
    assert cli.main(["export", str(path), "-o", str(tmp_path / "x.svg")]) == 1
    assert "not valid JSON" in capsys.readouterr().err


# ------------------------------------------------------------------ template and lint


@pytest.mark.parametrize("kind", ["flowchart", "workflow", "pathway", "abstract", "poster", "prisma"])
def test_template_builds_each_kind_from_the_documented_content(tmp_path, kind):
    from figwright.examples import TEMPLATE_FORMS

    form = next(f for f in TEMPLATE_FORMS if f.get("kind") == kind)
    content = tmp_path / "content.json"
    content.write_text(json.dumps(form["content"]["en"], ensure_ascii=False), "utf-8")
    out = tmp_path / f"{kind}.json"
    run("template", kind, str(content), "-o", str(out))
    scene = read(out)["scene"]
    assert scene["nodes"] and scene["kind"] == kind


def test_template_refuses_content_that_is_not_json(tmp_path, capsys):
    content = tmp_path / "content.json"
    content.write_text("steps: a, b, c", "utf-8")
    assert cli.main(["template", "flowchart", str(content), "-o", str(tmp_path / "x.svg")]) == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_template_explains_content_it_cannot_use(tmp_path, capsys):
    content = tmp_path / "content.json"
    content.write_text(json.dumps({"nodes": []}), "utf-8")
    assert cli.main(["template", "flowchart", str(content), "-o", str(tmp_path / "x.svg")]) == 1
    assert capsys.readouterr().err.strip()


def test_lint_is_quiet_about_a_good_figure(tmp_path, flow, capsys):
    run("lint", str(scene_file(tmp_path, flow)))
    assert "No layout problems" in capsys.readouterr().out


def test_lint_reports_problems_and_fails_the_exit_code(tmp_path, capsys):
    bad = {"width": 200, "height": 100,
           "nodes": [{"id": "a", "type": "rect", "x": 0, "y": 0, "w": 30, "h": 12,
                      "text": "far too much text for a box this small"}]}
    assert cli.main(["lint", str(scene_file(tmp_path, bad, "bad.json"))]) == 1
    printed = capsys.readouterr().out
    assert "error" in printed


# ------------------------------------------------------------------ plot


def test_plot_draws_a_chart_from_a_csv(tmp_path, table_csv):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    out = tmp_path / "chart.png"
    run("plot", str(csv), "-o", str(out), "--kind", "box", "--stats", "--dpi", "120")
    assert out.stat().st_size > 1000


def test_plot_prints_the_caption_with_the_test_it_used(tmp_path, table_csv, capsys):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    run("plot", str(csv), "-o", str(tmp_path / "c.svg"), "--stats")
    out = capsys.readouterr()
    assert "p" in out.out.lower() and "n =" in out.out
    assert "chart:" in out.err


def test_plot_writes_a_native_powerpoint_chart(tmp_path, table_csv):
    import io as _io

    from pptx import Presentation

    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    out = tmp_path / "chart.pptx"
    run("plot", str(csv), "-o", str(out), "--kind", "bar")
    deck = Presentation(_io.BytesIO(out.read_bytes()))
    assert any(s.has_chart for s in deck.slides[0].shapes)


def test_plot_takes_the_whole_description_as_json(tmp_path, table_csv):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    out = tmp_path / "c.svg"
    run("plot", str(csv), "-o", str(out), "--spec", json.dumps({"kind": "violin", "title": "标题在这"}))
    assert "标题在这" in out.read_text("utf-8")


def test_a_broken_spec_is_reported_rather_than_ignored(tmp_path, table_csv, capsys):
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    assert cli.main(["plot", str(csv), "-o", str(tmp_path / "c.svg"), "--spec", "{kind: bar}"]) == 1
    assert "--spec" in capsys.readouterr().err


def test_a_column_that_does_not_exist_is_reported(tmp_path, table_csv, capsys):
    """The chart is still drawn, but the typo is not swallowed."""
    csv = tmp_path / "t.csv"
    csv.write_text(table_csv, "utf-8")
    run("plot", str(csv), "-o", str(tmp_path / "c.svg"), "--x", "weather")
    said = capsys.readouterr().err
    assert "no column called 'weather'" in said and "group" in said


def test_plot_can_be_pointed_at_the_columns_by_hand(tmp_path, wide_csv, capsys):
    csv = tmp_path / "w.csv"
    csv.write_text(wide_csv, "utf-8")
    out = tmp_path / "c.svg"
    run("plot", str(csv), "-o", str(out), "--kind", "scatter", "--x", "conc", "--y", "signal", "--fit")
    assert "conc" in out.read_text("utf-8")
    said = capsys.readouterr()
    assert "x = conc, y = signal" in said.err
    assert "R" in said.out  # the caption carries the fit


# ------------------------------------------------------------------ images


def test_vectorize_turns_a_picture_into_shapes(tmp_path, shapes_png):
    src = tmp_path / "s.png"
    src.write_bytes(shapes_png)
    out = tmp_path / "traced.svg"
    run("vectorize", str(src), "-o", str(out), "--colors", "4")
    assert "<path" in out.read_text("utf-8")


def test_vectorize_can_write_a_figure_you_can_keep_editing(tmp_path, shapes_png):
    from figwright.render import extract_scene_from_svg

    src = tmp_path / "s.png"
    src.write_bytes(shapes_png)
    out = tmp_path / "traced.svg"
    run("vectorize", str(src), "-o", str(out), "--colors", "3", "--editable")
    assert extract_scene_from_svg(out.read_text("utf-8"))


def test_vectorize_reports_how_well_it_did(tmp_path, shapes_png, capsys):
    src = tmp_path / "s.png"
    src.write_bytes(shapes_png)
    run("vectorize", str(src), "-o", str(tmp_path / "t.svg"), "--colors", "4")
    said = capsys.readouterr().err
    assert "colours" in said and "colour error" in said


def test_enhance_cleans_up_a_scan_and_sets_the_print_size(tmp_path, photo_png, capsys):
    src = tmp_path / "p.png"
    src.write_bytes(photo_png)
    out = tmp_path / "clean.tif"
    run("enhance", str(src), "-o", str(out), "--whiten", "--trim", "--width-mm", "89", "--dpi", "600")
    assert out.stat().st_size > 100
    said = capsys.readouterr().err
    assert "89" in said and "600" in said and "did:" in said


def test_enhance_refuses_a_format_it_cannot_write(tmp_path, photo_png, capsys):
    src = tmp_path / "p.png"
    src.write_bytes(photo_png)
    assert cli.main(["enhance", str(src), "-o", str(tmp_path / "x.svg")]) == 1
    assert ".svg" in capsys.readouterr().err


def test_a_file_that_is_not_an_image_is_reported(tmp_path, capsys):
    src = tmp_path / "notes.png"
    src.write_text("I am text in a hat.", "utf-8")
    assert cli.main(["enhance", str(src), "-o", str(tmp_path / "x.png")]) == 1
    assert capsys.readouterr().err.strip()


# ------------------------------------------------------------------ config and doctor


def test_config_show_prints_the_settings_and_no_secrets(capsys):
    run("config", "show")
    printed = capsys.readouterr().out
    assert "settings file:" in printed
    for role in ("text", "vision", "image"):
        assert role in printed


def test_config_providers_lists_what_can_be_connected(capsys):
    run("config", "providers")
    printed = capsys.readouterr().out
    for pid in ("anthropic", "openai", "ollama", "deepseek", "zhipu", "mock"):
        assert pid in printed


def test_a_key_is_read_from_the_pipe_and_never_shown(monkeypatch, capsys):
    """Keys must not travel as arguments: shell history keeps those forever."""
    from figwright.config import load_config, provider_settings

    secret = "sk-not-a-real-key-" + "9" * 12
    monkeypatch.setattr("sys.stdin", io.StringIO(secret + "\n"))
    run("config", "set-key", "openai")
    said = capsys.readouterr()
    assert secret not in said.out + said.err
    assert provider_settings(load_config(), "openai")["api_key"] == secret

    run("config", "show")
    shown = capsys.readouterr().out
    assert secret not in shown and "key for openai" in shown


def test_a_key_can_be_cleared(monkeypatch):
    from figwright.config import load_config, provider_settings

    monkeypatch.setattr("sys.stdin", io.StringIO("sk-temporary-key-00000\n"))
    run("config", "set-key", "openai")
    run("config", "clear-key", "openai")
    assert not provider_settings(load_config(), "openai")["api_key"]


def test_an_empty_key_is_not_saved(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    assert cli.main(["config", "set-key", "openai"]) == 1
    assert "No key entered" in capsys.readouterr().err


def test_a_provider_nobody_has_heard_of_gets_advice(capsys):
    assert cli.main(["config", "set-key", "skynet"]) == 1
    assert "config providers" in capsys.readouterr().err


def test_a_role_can_be_pointed_at_a_provider(capsys):
    run("config", "role", "text", "ollama", "qwen3:8b")
    run("config", "show")
    printed = capsys.readouterr().out
    assert "ollama" in printed and "qwen3:8b" in printed


def test_a_role_that_does_not_exist_gets_advice(capsys):
    assert cli.main(["config", "role", "telepathy", "openai"]) == 1
    assert "text" in capsys.readouterr().err


def test_doctor_checks_every_part_of_the_installation(capsys):
    run("doctor")
    printed = capsys.readouterr().out
    assert "Python" in printed
    for part in ("matplotlib", "pptx", "scipy", "cv2", "resvg_py", "data folder", "rendering self-test"):
        assert part in printed, part
    assert "MISSING" not in printed and "PROBLEM" not in printed
    assert "Everything needed is in place." in printed


def test_doctor_fails_when_something_is_missing(capsys, monkeypatch):
    import importlib

    real = importlib.import_module

    def missing(name, *a, **k):
        if name == "matplotlib":
            raise ImportError("no matplotlib here")
        return real(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", missing)
    assert cli.main(["doctor"]) == 1
    printed = capsys.readouterr().out
    assert "MISSING  matplotlib" in printed and "Some parts are missing" in printed
