"""Projects on disk: save, version, duplicate, and the conflict check that
stops two open tabs from quietly overwriting each other.
"""

from __future__ import annotations

import json

import pytest

from figwright import scene as S, store
from figwright.config import projects_dir


def test_a_new_project_gets_an_id_and_shows_up_in_the_list(tiny_scene):
    p = store.create_project("My figure", tiny_scene)
    assert len(p["id"]) == 16 and p["name"] == "My figure"
    assert [x["id"] for x in store.list_projects()] == [p["id"]]


def test_an_empty_name_still_gets_something_readable(tiny_scene):
    p = store.create_project("   ", tiny_scene)
    assert p["name"].strip()


def test_loading_gives_the_scene_back(tiny_scene):
    p = store.create_project("x", tiny_scene)
    loaded = store.load_project(p["id"])
    assert S.scene_hash(loaded["scene"]) == S.scene_hash(tiny_scene)


def test_a_missing_project_raises_a_clear_error():
    with pytest.raises(store.StoreError):
        store.load_project("0" * 16)


@pytest.mark.parametrize("pid", ["../../etc/passwd", "nope", "", "A" * 16, "../" * 4 + "x"])
def test_an_id_that_is_not_an_id_is_refused(pid):
    with pytest.raises(store.StoreError):
        store.load_project(pid)


def test_saving_bumps_the_revision(tiny_scene):
    p = store.create_project("x", tiny_scene)
    first = store.load_project(p["id"])["rev"]
    tiny_scene["nodes"][0]["text"] = "Changed"
    after = store.save_project(p["id"], tiny_scene)
    assert after["rev"] == first + 1
    assert store.load_project(p["id"])["scene"]["nodes"][0]["text"] == "Changed"


def test_saving_against_a_stale_revision_is_refused(tiny_scene):
    p = store.create_project("x", tiny_scene)
    store.save_project(p["id"], tiny_scene)  # someone else saved first
    with pytest.raises(store.StoreError) as err:
        store.save_project(p["id"], tiny_scene, base_rev=0)
    assert err.value.code == "conflict"
    assert "saved somewhere else" in str(err.value)


def test_renaming_does_not_touch_the_scene(tiny_scene):
    p = store.create_project("old", tiny_scene)
    store.save_project(p["id"], name="new")
    got = store.load_project(p["id"])
    assert got["name"] == "new" and got["scene"]["nodes"]


def test_snapshots_are_listed_newest_first_and_can_be_loaded(tiny_scene):
    p = store.create_project("x", tiny_scene)
    store.save_project(p["id"], tiny_scene, snapshot=True, label="before the rewrite")
    tiny_scene["nodes"][0]["text"] = "Second"
    store.save_project(p["id"], tiny_scene, snapshot=True, label="after")
    versions = store.list_versions(p["id"])
    assert len(versions) >= 2 and versions[0]["label"] == "after"
    assert [v["index"] for v in versions] == [1, 0]
    old = store.load_version(p["id"], 0)
    assert old["scene"]["nodes"][0]["text"] == "Input"


def test_duplicating_makes_an_independent_copy(tiny_scene):
    p = store.create_project("x", tiny_scene)
    copy = store.duplicate_project(p["id"])
    assert copy["id"] != p["id"]
    store.save_project(copy["id"], S.new_scene())
    assert store.load_project(p["id"])["scene"]["nodes"]  # the original is untouched


def test_deleting_removes_it_from_the_list(tiny_scene):
    p = store.create_project("x", tiny_scene)
    store.delete_project(p["id"])
    assert store.list_projects() == []
    with pytest.raises(store.StoreError):
        store.load_project(p["id"])


def test_a_corrupt_project_file_does_not_break_the_list(tiny_scene):
    store.create_project("good", tiny_scene)
    (projects_dir() / ("b" * 16 + ".json")).write_text("{ not json", "utf-8")
    assert [p["name"] for p in store.list_projects()] == ["good"]


def test_the_project_file_is_json_we_can_read_by_hand(tiny_scene):
    p = store.create_project("x", tiny_scene)
    raw = json.loads((projects_dir() / f"{p['id']}.json").read_text("utf-8"))
    assert raw["name"] == "x" and raw["scene"]["nodes"]


def test_an_oversized_figure_is_refused_with_a_useful_message(tiny_scene):
    p = store.create_project("x", tiny_scene)
    huge = dict(tiny_scene, nodes=[dict(tiny_scene["nodes"][0], type="image",
                                        href="data:image/png;base64," + "A" * (61 * 1024 * 1024))])
    with pytest.raises(store.StoreError) as err:
        store.save_project(p["id"], huge)
    assert err.value.code == "too_large"
