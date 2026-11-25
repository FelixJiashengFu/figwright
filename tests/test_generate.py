"""The generation pipeline, driven by a scripted model.

What matters here is what happens when the model misbehaves: bad JSON, a scene
with overlapping boxes, a refusal, a timeout. None of it may reach the user as
a traceback, and demo mode must always be able to finish the job.
"""

from __future__ import annotations

import json

import pytest

from figwright import generate, scene as S
from figwright.providers.base import ChatResult, Provider, ProviderError


class Scripted(Provider):
    """A model that says exactly what the test tells it to."""

    def __init__(self, *replies, image: bytes | None = None, fail: Exception | None = None):
        super().__init__({"id": "scripted", "type": "openai", "model": "scripted-1"})
        self.replies = list(replies)
        self.image = image
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def chat(self, system, user, images=None, json_mode=True, max_tokens=8000):
        self.calls.append((system, user))
        if self.fail:
            raise self.fail
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, ChatResult):
            return reply
        return ChatResult(text=reply, model="scripted-1", usage={"input_tokens": 1, "output_tokens": 2})

    def generate_image(self, prompt, size="1024x1024", reference=None):
        if self.image is None:
            raise ProviderError("unsupported", "no image model")
        return self.image

    def list_models(self):
        return ["scripted-1"]


def use(monkeypatch, provider):
    monkeypatch.setattr(generate, "provider_for_role", lambda role, cfg=None: provider)
    return provider


def demo(monkeypatch):
    """Switch to demo mode: no model at all."""
    from figwright.providers.mock import MockProvider

    return use(monkeypatch, MockProvider({"id": "mock", "type": "mock", "model": ""}))


GOOD = json.dumps({
    "width": 600, "height": 300, "title": "Two steps",
    "nodes": [{"id": "a", "type": "rect", "x": 40, "y": 60, "w": 200, "h": 80, "text": "Collect"},
              {"id": "b", "type": "rect", "x": 360, "y": 60, "w": 200, "h": 80, "text": "Measure"}],
    "edges": [{"from": "a", "to": "b"}],
})


def test_a_good_answer_becomes_a_figure(monkeypatch):
    model = use(monkeypatch, Scripted(GOOD))
    out = generate.generate_figure("collect then measure", kind="illustration")
    assert [n["text"] for n in out.scene["nodes"]] == ["Collect", "Measure"]
    assert out.provider == "scripted" and out.model == "scripted-1"
    assert out.usage["output_tokens"] == 2
    assert model.calls  # it really went to the model


def test_the_prompt_reaches_the_model_with_the_source_text(monkeypatch):
    model = use(monkeypatch, Scripted(GOOD))
    generate.generate_figure("draw this", source="Methods: we did X.", kind="illustration")
    _system, user = model.calls[0]
    assert "draw this" in user and "we did X" in user


def test_json_wrapped_in_chatter_is_still_read(monkeypatch):
    use(monkeypatch, Scripted("Sure! Here is the figure:\n```json\n" + GOOD + "\n```\nHope it helps."))
    assert generate.generate_figure("x", kind="illustration").scene["nodes"]


def test_content_that_cannot_be_laid_out_is_asked_for_again(monkeypatch):
    """The second ask tells the model what was wrong with the first answer."""
    model = use(monkeypatch, Scripted(json.dumps({"nodes": []}), json.dumps(
        {"nodes": [{"id": "a", "text": "Collect"}, {"id": "b", "text": "Measure"}],
         "edges": [{"from": "a", "to": "b"}]})))
    out = generate.generate_figure("collect then measure", kind="flowchart")
    assert len(model.calls) == 2
    assert "could not be used" in model.calls[1][1]
    assert [n["text"] for n in out.scene["nodes"] if n.get("text")][:2] == ["Collect", "Measure"]


def test_an_answer_that_never_parses_is_reported_clearly(monkeypatch):
    use(monkeypatch, Scripted("nope", "still nope"))
    with pytest.raises(generate.GenerationError) as err:
        generate.generate_figure("x", kind="illustration")
    assert err.value.code == "bad_json"


def test_a_refusal_reaches_the_user_rather_than_being_papered_over(monkeypatch):
    """A figure built by the rules instead must not be passed off as the model's."""
    use(monkeypatch, Scripted(fail=ProviderError("refusal", "Claude declined this request.")))
    with pytest.raises(ProviderError) as err:
        generate.generate_figure("采样、提取、测序", kind="flowchart")
    assert err.value.code == "refusal"


def test_demo_mode_builds_the_figure_from_the_text_and_says_so(monkeypatch):
    demo(monkeypatch)
    out = generate.generate_figure("采样、提取、质检，如果合格则测序，否则重新提取", kind="flowchart")
    assert any(n.get("type") == "diamond" for n in out.scene["nodes"])
    assert any("offline demo" in n for n in out.notes)
    assert out.usage == {}


def test_demo_mode_says_what_it_could_not_parse(monkeypatch):
    demo(monkeypatch)
    with pytest.raises(generate.GenerationError) as err:
        generate.generate_figure("请画点什么好看的东西", kind="poster")
    assert err.value.code in ("offline_parse", "bad_content")
    assert "Settings" in str(err.value)


def test_a_missing_key_is_reported_to_the_user_not_swallowed(monkeypatch):
    def no_provider(role, cfg=None):
        raise ProviderError("config", "No API key is set for openai. Add it in Settings.")

    monkeypatch.setattr(generate, "provider_for_role", no_provider)
    with pytest.raises(ProviderError) as err:
        generate.generate_figure("x", kind="illustration")
    assert err.value.code == "config" and "Settings" in str(err.value)


def test_a_network_failure_is_reported(monkeypatch):
    use(monkeypatch, Scripted(fail=ProviderError("network", "Could not reach the provider.")))
    with pytest.raises(ProviderError) as err:
        generate.generate_figure("x", kind="illustration")
    assert err.value.code == "network"


def test_a_truncated_answer_is_called_out(monkeypatch):
    cut = ChatResult(text=GOOD, model="scripted-1", truncated=True)
    use(monkeypatch, Scripted(cut))
    out = generate.generate_figure("x", kind="illustration")
    assert any("cut off" in n for n in out.notes)


def test_the_layout_is_tidied_and_the_fixes_are_reported(monkeypatch):
    messy = json.dumps({
        "width": 300, "height": 200,
        "nodes": [{"id": "a", "type": "rect", "x": 0, "y": 0, "w": 40, "h": 18, "text": "a long label that will not fit"},
                  {"id": "b", "type": "rect", "x": 600, "y": 0, "w": 120, "h": 50, "text": "B"}],
    })
    use(monkeypatch, Scripted(messy))
    out = generate.generate_figure("x", kind="illustration")
    from figwright.lint import lint

    codes = {i["code"] for i in lint(out.scene)}
    assert "text_overflow" not in codes and "off_canvas" not in codes
    assert out.notes


def test_the_figure_records_which_model_made_it(monkeypatch):
    use(monkeypatch, Scripted(GOOD))
    out = generate.generate_figure("x", kind="illustration")
    steps = out.scene["meta"]["provenance"]
    assert steps[-1]["provider"] == "scripted" and steps[-1]["model"] == "scripted-1"
    assert steps[-1]["action"] == "generate"
    # The prompt itself is not stored, only a digest of it.
    assert "x" not in json.dumps(steps[-1]) or steps[-1].get("prompt_sha256")


def test_house_style_is_applied(monkeypatch):
    use(monkeypatch, Scripted(GOOD))
    cfg = {"house_style": {"fontFamily": "Georgia", "fontSize": 13}, "roles": {}, "providers": {}}
    out = generate.generate_figure("x", kind="illustration", cfg=cfg)
    assert out.scene["style"]["fontFamily"] == "Georgia" and out.scene["style"]["fontSize"] == 13





# ------------------------------------------------------------------ refine


def test_an_edit_applies_the_operations(monkeypatch, tiny_scene):
    ops = json.dumps({"ops": [{"op": "update", "id": "a", "set": {"text": "Changed"}}]})
    use(monkeypatch, Scripted(ops))
    out = generate.refine_figure(tiny_scene, "rename the first box")
    assert S.node_by_id(out.scene)["a"]["text"] == "Changed"
    assert out.notes


def test_an_edit_that_changes_nothing_says_so_instead_of_pretending(monkeypatch, tiny_scene):
    use(monkeypatch, Scripted(json.dumps({"ops": [], "summary": "nothing to do here"})))
    out = generate.refine_figure(tiny_scene, "leave it alone")
    assert S.scene_hash(out.scene) == S.scene_hash(tiny_scene)
    assert "nothing to do here" in out.notes


def test_an_edit_that_names_a_missing_node_keeps_the_rest(monkeypatch, tiny_scene):
    ops = json.dumps({"ops": [{"op": "update", "id": "ghost", "set": {"text": "x"}},
                              {"op": "update", "id": "b", "set": {"text": "Kept"}}]})
    use(monkeypatch, Scripted(ops))
    out = generate.refine_figure(tiny_scene, "two edits, one wrong")
    assert S.node_by_id(out.scene)["b"]["text"] == "Kept"


def test_an_edit_in_demo_mode_uses_the_simple_rules(monkeypatch, tiny_scene):
    demo(monkeypatch)
    out = generate.refine_figure(tiny_scene, "字号改为 20")
    assert out.scene["style"]["fontSize"] == 20


def test_an_edit_the_rules_cannot_do_explains_what_demo_mode_can(monkeypatch, tiny_scene):
    demo(monkeypatch)
    out = generate.refine_figure(tiny_scene, "make it more philosophical")
    assert S.scene_hash(out.scene) == S.scene_hash(tiny_scene)
    assert out.notes and len(out.notes[0]) > 20  # the list of what it does understand


def test_only_the_selected_nodes_are_described_to_the_model(monkeypatch, tiny_scene):
    model = use(monkeypatch, Scripted(json.dumps({"ops": []})))
    generate.refine_figure(tiny_scene, "move this", selection=["a"])
    _system, user = model.calls[0]
    assert "selected" in user.lower() or '"a"' in user


# ------------------------------------------------------------------ pictures


def test_an_illustration_wraps_the_png_in_a_scene(monkeypatch, shapes_png):
    use(monkeypatch, Scripted(GOOD, image=shapes_png))
    out = generate.illustrate("a cell", style="flat")
    pictures = [n for n in out.scene["nodes"] if n["type"] == "image"]
    assert pictures and pictures[0]["href"].startswith("data:image/png;base64,")


def test_an_image_model_that_cannot_draw_is_reported(monkeypatch):
    use(monkeypatch, Scripted(GOOD))
    with pytest.raises((generate.GenerationError, ProviderError)):
        generate.illustrate("a cell")


def test_redrawing_a_region_puts_the_patch_back(monkeypatch, shapes_png):
    use(monkeypatch, Scripted(GOOD, image=shapes_png))
    out, info = generate.redraw_region(shapes_png, (10, 10, 100, 100), "make it blue")
    assert out[:8] == b"\x89PNG\r\n\x1a\n" and info


def test_a_sketch_becomes_a_figure(monkeypatch, shapes_png):
    use(monkeypatch, Scripted(GOOD))
    out = generate.sketch_to_figure(shapes_png, "tidy this up")
    assert out.scene["nodes"]


def test_the_model_is_shown_the_figure_as_an_image_when_polishing(monkeypatch, tiny_scene):
    model = use(monkeypatch, Scripted(json.dumps({"ops": []})))
    generate.polish_figure(tiny_scene)
    assert model.calls


def test_a_chart_suggestion_comes_back_as_a_spec(monkeypatch, table_csv):
    from figwright import plot

    df = plot.load_table("t.csv", table_csv.encode())
    use(monkeypatch, Scripted(json.dumps({"kind": "box", "x": "group", "y": ["value"], "stats": True})))
    spec, info = generate.suggest_plot("box plot with stats", plot.describe(df))
    assert spec["kind"] == "box" and spec["stats"] is True
    assert info


def test_a_chart_suggestion_in_demo_mode_uses_the_word_rules(monkeypatch, table_csv):
    from figwright import plot

    df = plot.load_table("t.csv", table_csv.encode())
    demo(monkeypatch)
    spec, info = generate.suggest_plot("画成箱线图并做组间检验", plot.describe(df))
    assert spec["kind"] == "box" and spec["stats"] is True
    assert any("offline" in n or "rules" in n for n in info.get("notes", []))
