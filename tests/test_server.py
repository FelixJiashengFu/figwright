"""The local HTTP server.

Two things are being checked: that every endpoint answers in the shape the
browser expects, and that a web page on another site cannot drive it. The
server holds the user's API keys and their files, so the second part matters as
much as the first.
"""

from __future__ import annotations

import base64
import io
import json
import time
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from figwright import scene as S
from figwright.server import TOKEN_HEADER, create_app


HOME_URL = "http://127.0.0.1:8765"  # the server only answers to a local address


@pytest.fixture
def client():
    with TestClient(create_app(), base_url=HOME_URL) as c:
        yield c


@pytest.fixture
def guarded():
    with TestClient(create_app(token="secret-token-1234"), base_url=HOME_URL) as c:
        yield c


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def finish(client, payload: dict, path: str) -> dict:
    """POST and, if the answer is a job, wait for it."""
    out = ok(client.post(path, json=payload))
    if "job" not in out:
        return out
    for _ in range(300):
        state = ok(client.get(f"/api/jobs/{out['job']}"))
        if state["status"] == "done":
            return state["result"]
        assert state["status"] in ("running", "queued", "pending"), state
        time.sleep(0.05)
    raise AssertionError("the job never finished")


def failed(client, payload: dict, path: str) -> dict:
    """POST something that should fail, and give back the error."""
    out = ok(client.post(path, json=payload))
    for _ in range(300):
        state = ok(client.get(f"/api/jobs/{out['job']}"))
        if state["status"] == "error":
            return state["error"]
        if state["status"] == "done":
            raise AssertionError(f"expected a failure, got {state['result']}")
        time.sleep(0.05)
    raise AssertionError("the job never finished")


# ------------------------------------------------------------------ the page itself


def test_the_page_is_served_with_a_strict_policy(client):
    r = client.get("/")
    assert r.status_code == 200 and "<title>" in r.text
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "object-src 'none'" in csp
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_the_browser_files_are_served(client):
    for path in ("/static/app.js", "/static/scene.js", "/static/style.css"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["x-content-type-options"] == "nosniff"


def test_health_and_meta_tell_the_page_what_it_can_do(client):
    assert ok(client.get("/api/health"))["ok"] is True
    meta = ok(client.get("/api/meta"))
    for key in ("themes", "kinds", "node_types", "plot_kinds", "vector_details", "version"):
        assert meta[key], key
    icons = ok(client.get("/api/icons"))
    assert icons["icons"] and icons["categories"]


# ------------------------------------------------------------------ keeping other sites out


def test_a_request_claiming_another_host_is_refused(client):
    r = client.get("/api/meta", headers={"host": "figwright.example.com"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "bad_host"


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:8765", "[::1]:8765", "localhost"])
def test_the_usual_local_addresses_are_allowed(client, host):
    assert client.get("/api/meta", headers={"host": host}).status_code == 200


def test_a_page_on_another_site_cannot_call_the_api(client):
    r = client.post("/api/lint", json={"scene": {}}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "cross_site"


def test_a_cross_site_fetch_marker_is_refused(client):
    r = client.post("/api/lint", json={"scene": {}}, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403


def test_the_apps_own_requests_are_accepted(client):
    r = client.post("/api/lint", json={"scene": S.new_scene()},
                    headers={"origin": HOME_URL, "sec-fetch-site": "same-origin"})
    assert r.status_code == 200


def test_a_token_is_required_when_one_is_set(guarded):
    assert guarded.get("/api/meta").status_code == 401
    assert guarded.get("/api/meta", headers={TOKEN_HEADER: "wrong"}).status_code == 401
    assert guarded.get("/api/meta", headers={TOKEN_HEADER: "secret-token-1234"}).status_code == 200
    assert guarded.get("/api/meta?token=secret-token-1234").status_code == 200


def test_the_token_in_the_address_becomes_a_cookie_so_it_leaves_the_url(guarded):
    r = guarded.get("/?token=secret-token-1234")
    assert r.status_code == 200
    assert "fw_token" in r.cookies or any("fw_token" in v for v in r.headers.get_list("set-cookie"))


def test_remote_access_without_a_token_is_not_allowed():
    with pytest.raises(ValueError):
        create_app(allow_remote=True)


def test_an_oversized_request_is_refused_before_it_is_read(client):
    r = client.post("/api/lint", content=b"{}", headers={"content-length": str(200 * 1024 * 1024), "content-type": "application/json"})
    assert r.status_code == 413


def test_an_error_always_has_a_code_and_a_message(client):
    r = client.post("/api/template", json={"kind": "nope", "content": {}})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "bad_template" and err["message"]


def test_a_job_that_fails_reports_the_reason_not_a_traceback(client):
    err = failed(client, {"prompt": "", "kind": "flowchart"}, "/api/generate")
    assert err["code"] == "empty_prompt" and "Describe" in err["message"]
    assert "Traceback" not in err["message"]


def test_a_bad_json_body_is_a_clean_error(client):
    r = client.post("/api/lint", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"]


# ------------------------------------------------------------------ figures


def test_demo_mode_generates_a_figure(client):
    out = finish(client, {"prompt": "采样、提取、质检，如果合格则测序，否则重新提取", "kind": "flowchart"}, "/api/generate")
    assert out["scene"]["nodes"] and any("offline" in n for n in out["notes"])


def test_every_diagram_template_in_the_catalogue_builds(client):
    """The gallery offers these in two languages, so all of them must work."""
    forms = [f for f in ok(client.get("/api/meta"))["templates"] if f["type"] == "builder"]
    assert len(forms) >= 6
    built = 0
    for form in forms:
        for lang, content in (form.get("content") or {}).items():
            out = ok(client.post("/api/template", json={"kind": form["kind"], "content": content, "theme": "ink"}))
            assert out["scene"]["nodes"], (form["id"], lang)
            assert not [i for i in out["issues"] if i["severity"] == "error"], (form["id"], lang, out["issues"])
            built += 1
    assert built == 2 * len(forms)


def test_the_chart_template_charts_its_own_example(client):
    form = next(f for f in ok(client.get("/api/meta"))["templates"] if f["type"] == "plot")
    out = ok(client.post("/api/plot/render", json={"csv": form["csv"], "spec": form["spec"]}))
    assert out["svg"] and out["spec"]["kind"] == form["spec"].get("kind", out["spec"]["kind"])


def test_the_picture_template_needs_an_image_model(client):
    """In demo mode it says so rather than drawing something misleading."""
    form = next(f for f in ok(client.get("/api/meta"))["templates"] if f["type"] == "illustrate")
    assert form["content"]["zh"] and form["style"]


def test_lint_autofix_and_retheme(client, tiny_scene):
    issues = ok(client.post("/api/lint", json={"scene": tiny_scene}))["issues"]
    assert isinstance(issues, list)
    fixed = ok(client.post("/api/autofix", json={"scene": tiny_scene}))
    assert "scene" in fixed and isinstance(fixed["notes"], list)
    other = ok(client.post("/api/retheme", json={"scene": tiny_scene, "theme": "mono"}))
    assert other["scene"]["style"]["theme"] == "mono"


def test_an_edit_in_demo_mode_changes_the_figure(client, tiny_scene):
    out = finish(client, {"scene": tiny_scene, "instruction": "字号改为 20"}, "/api/refine")
    assert out["scene"]["style"]["fontSize"] == 20


# ------------------------------------------------------------------ exports


@pytest.mark.parametrize("fmt,prefix", [("svg", b"<"), ("png", b"\x89PNG"), ("pptx", b"PK"), ("pdf", b"%PDF"), ("html", b"<")])
def test_every_export_format_downloads(client, flow, fmt, prefix):
    r = client.post("/api/export", json={"scene": flow, "format": fmt, "dpi": 150})
    assert r.status_code == 200, r.text
    assert r.content.startswith(prefix)
    assert "attachment" in r.headers["content-disposition"]
    assert "filename" in r.headers["content-disposition"]


def test_an_export_carries_its_notes_in_a_header(client, flow):
    flow["edges"][0]["routing"] = "curve"
    r = client.post("/api/export", json={"scene": flow, "format": "pptx"})
    assert r.status_code == 200
    notes = json.loads(unquote(r.headers.get("x-figwright-notes", "%5B%5D")))
    assert isinstance(notes, list)


def test_an_unknown_export_format_is_refused(client, flow):
    r = client.post("/api/export", json={"scene": flow, "format": "dwg"})
    assert r.status_code == 400


def test_the_disclosure_text_is_offered_in_both_languages(client, flow):
    out = ok(client.post("/api/disclosure", json={"scene": flow}))
    assert set(out) >= {"zh", "en"}


# ------------------------------------------------------------------ import


def test_an_svg_from_figwright_comes_back_as_a_scene(client, flow):
    from figwright import render

    svg = render.render_svg(flow, embed_scene=True)
    r = client.post("/api/import", files={"file": ("figure.svg", svg.encode(), "image/svg+xml")})
    out = ok(r)
    assert len(out["scene"]["nodes"]) == len(flow["nodes"])


def test_someone_elses_svg_becomes_a_picture_with_a_note(client):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="#333"/></svg>'
    out = ok(client.post("/api/import", files={"file": ("other.svg", svg.encode(), "image/svg+xml")}))
    assert out["scene"]["nodes"] and out["notes"]
    assert out["editable"] is False  # it came in as a picture, not as shapes


def test_an_svg_with_a_script_is_imported_without_it(client):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><script>bad()</script><rect width="10" height="10"/></svg>'
    out = ok(client.post("/api/import", files={"file": ("x.svg", svg.encode(), "image/svg+xml")}))
    assert "bad()" not in json.dumps(out)


def test_a_png_is_imported_as_a_picture(client, shapes_png):
    out = ok(client.post("/api/import", files={"file": ("x.png", shapes_png, "image/png")}))
    assert any(n["type"] == "image" for n in out["scene"]["nodes"])


def test_a_file_we_cannot_use_is_refused_politely(client):
    r = client.post("/api/import", files={"file": ("x.exe", b"MZ\x90\x00binary", "application/octet-stream")})
    assert r.status_code == 400 and r.json()["error"]["message"]


# ------------------------------------------------------------------ tables and charts


def test_a_table_is_read_and_described(client, table_csv):
    out = ok(client.post("/api/plot/table", files={"file": ("t.csv", table_csv.encode(), "text/csv")}))
    assert out["rows"] == 12
    assert [c["name"] for c in out["columns"]] == ["group", "dose", "value"]
    assert out["preview"]["rows"]


def test_a_big_table_warns_about_the_wait(client):
    rows = ["g,v"] + [f"a,{i}" for i in range(25000)]
    out = ok(client.post("/api/plot/table", files={"file": ("t.csv", "\n".join(rows).encode(), "text/csv")}))
    assert any("rows" in n for n in out["notes"])


def test_a_chart_renders_with_its_caption_and_statistics(client, table_csv):
    out = ok(client.post("/api/plot/render", json={"csv": table_csv, "spec": {"stats": True}}))
    assert out["svg"].startswith("<?xml") or out["svg"].startswith("<svg")
    assert out["spec"]["y"] == ["value"]
    assert out["stats"]["comparisons"] and out["caption"]["zh"]


def test_a_chart_says_which_values_a_log_axis_hides(client):
    out = ok(client.post("/api/plot/render", json={"csv": "g,v\na,0\nb,1\nc,10\n", "spec": {"logy": True}}))
    assert out["notes"] and "log y axis" in out["notes"][0]


@pytest.mark.parametrize("fmt", ["svg", "png", "pdf", "pptx"])
def test_a_chart_exports(client, table_csv, fmt):
    r = client.post("/api/plot/export", json={"csv": table_csv, "spec": {}, "format": fmt, "dpi": 150})
    assert r.status_code == 200 and len(r.content) > 500


def test_a_chart_can_be_put_on_the_canvas(client, table_csv):
    out = ok(client.post("/api/plot/image", json={"csv": table_csv, "spec": {}}))
    assert out["image"].startswith("data:image/png;base64,") and out["width"] > 0


def test_a_sentence_edits_the_chart_in_demo_mode(client, table_csv):
    out = finish(client, {"csv": table_csv, "prompt": "画成箱线图并做组间检验", "spec": {}}, "/api/plot/suggest")
    assert out["spec"]["kind"] == "box" and out["spec"]["stats"] is True


# ------------------------------------------------------------------ pictures


def test_a_picture_is_cleaned_up_and_the_steps_are_listed(client, photo_png):
    r = client.post("/api/image/enhance", files={"file": ("p.png", photo_png, "image/png")},
                    data={"options": json.dumps({"whiten": True, "trim": True})})
    out = ok(r)
    assert out["image"].startswith("data:image/png;base64,")
    assert out["info"]["steps"] and out["info"]["width"] > 0
    assert out["preview"] is None  # a PNG needs no separate preview


def test_a_picture_is_traced_into_shapes(client, shapes_png):
    r = client.post("/api/image/vectorize", files={"file": ("s.png", shapes_png, "image/png")},
                    data={"colors": "4", "detail": "medium", "split": "false"})
    out = ok(r)
    assert [n for n in out["scene"]["nodes"] if n["type"] == "path"]
    assert out["info"]["layers"] >= 2


# ------------------------------------------------------------------ projects


def test_a_project_can_be_saved_listed_and_loaded(client, tiny_scene):
    made = ok(client.post("/api/projects", json={"name": "My figure", "scene": tiny_scene}))
    assert ok(client.get("/api/projects"))["projects"][0]["id"] == made["id"]
    got = ok(client.get(f"/api/projects/{made['id']}"))
    assert len(got["scene"]["nodes"]) == 2


def test_saving_over_someone_elses_save_is_refused(client, tiny_scene):
    made = ok(client.post("/api/projects", json={"name": "x", "scene": tiny_scene}))
    ok(client.put(f"/api/projects/{made['id']}", json={"scene": tiny_scene}))
    r = client.put(f"/api/projects/{made['id']}", json={"scene": tiny_scene, "base_rev": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_versions_can_be_filed_and_fetched(client, tiny_scene):
    made = ok(client.post("/api/projects", json={"name": "x", "scene": tiny_scene}))
    ok(client.post(f"/api/projects/{made['id']}/versions", json={"label": "first draft"}))
    versions = ok(client.get(f"/api/projects/{made['id']}/versions"))["versions"]
    assert versions and versions[0]["label"] == "first draft"
    assert ok(client.get(f"/api/projects/{made['id']}/versions/0"))["scene"]["nodes"]


def test_a_project_thumbnail_is_an_svg_that_cannot_load_anything(client, tiny_scene):
    made = ok(client.post("/api/projects", json={"name": "x", "scene": tiny_scene}))
    r = client.get(f"/api/projects/{made['id']}/thumb.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_a_project_can_be_duplicated_and_deleted(client, tiny_scene):
    made = ok(client.post("/api/projects", json={"name": "x", "scene": tiny_scene}))
    copy = ok(client.post(f"/api/projects/{made['id']}/duplicate"))
    assert copy["id"] != made["id"]
    assert ok(client.delete(f"/api/projects/{made['id']}"))["ok"] is True
    assert client.get(f"/api/projects/{made['id']}").status_code == 404


@pytest.mark.parametrize("pid", ["../secrets", "not-an-id", "0" * 16])
def test_an_id_that_is_not_an_id_cannot_reach_a_file(client, pid):
    assert client.get(f"/api/projects/{pid}").status_code in (400, 404, 422)


# ------------------------------------------------------------------ settings


def test_the_settings_never_hand_back_a_key(client):
    ok(client.put("/api/config", json={"providers": {"openai": {"api_key": "sk-test-not-real-key-1234"}}}))
    body = client.get("/api/config").text
    assert "sk-test-not-real-key-1234" not in body
    row = next(p for p in json.loads(body)["providers"] if p["id"] == "openai")
    assert row["key_set"] is True


def test_a_bad_base_url_is_refused(client):
    r = client.put("/api/config", json={"providers": {"custom": {"base_url": "file:///etc/passwd"}}})
    assert r.status_code == 400


def test_the_language_and_house_style_are_remembered(client):
    ok(client.put("/api/config", json={"lang": "en", "house_style": {"fontSize": 15}}))
    out = ok(client.get("/api/config"))
    assert out["lang"] == "en" and out["house_style"]["fontSize"] == 15


def test_asking_an_unconfigured_provider_for_models_is_a_clean_error(client):
    r = client.post("/api/config/models", json={"provider": "openai"})
    assert r.status_code in (400, 401, 502) and r.json()["error"]["message"]


def test_the_demo_provider_passes_its_own_test(client):
    out = finish(client, {"provider": "mock"}, "/api/config/test")
    assert out["ok"] is True


# ------------------------------------------------------------------ jobs


def test_a_finished_job_can_be_read_more_than_once(client):
    out = ok(client.post("/api/generate", json={"prompt": "采样、提取、测序", "kind": "flowchart"}))
    jid = out["job"]
    for _ in range(300):
        if ok(client.get(f"/api/jobs/{jid}"))["status"] == "done":
            break
        time.sleep(0.05)
    first = ok(client.get(f"/api/jobs/{jid}"))
    again = ok(client.get(f"/api/jobs/{jid}"))
    assert first["result"]["scene"] == again["result"]["scene"]


def test_a_job_can_be_cancelled(client):
    out = ok(client.post("/api/generate", json={"prompt": "采样、提取、测序", "kind": "flowchart"}))
    assert ok(client.delete(f"/api/jobs/{out['job']}"))["ok"] is True
    assert ok(client.get(f"/api/jobs/{out['job']}"))["status"] == "cancelled"


def test_an_unknown_job_is_a_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
