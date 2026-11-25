"""Projects on disk: one JSON file per figure plus a file of earlier versions.

Everything lives under ``~/.figwright/projects`` (or ``$FIGWRIGHT_HOME``).
Ids are generated here and validated on every call, so an id can never be
used to reach a path outside that folder. Writes are atomic.

Each project carries a revision counter. A save that names the revision it
was based on is refused when somebody else saved in between, which is what
keeps two people editing the same figure over a shared server from silently
overwriting each other.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import projects_dir
from .scene import normalize_scene

MAX_PROJECT_BYTES = 60 * 1024 * 1024
MAX_VERSIONS = 30
MAX_VERSION_BYTES = 80 * 1024 * 1024
_ID = re.compile(r"^[a-f0-9]{16}$")
_LOCK = threading.RLock()


class StoreError(ValueError):
    """A project operation failed; ``code`` is ``not_found``, ``bad_id``, ``conflict`` or ``too_large``."""

    def __init__(self, message: str, code: str = "bad_request") -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check(pid: Any) -> str:
    if not isinstance(pid, str) or not _ID.match(pid):
        raise StoreError("That is not a project id.", "bad_id")
    return pid


def _path(pid: str, versions: bool = False) -> Path:
    return projects_dir() / (f"{_check(pid)}.versions.json" if versions else f"{_check(pid)}.json")


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StoreError("This project no longer exists.", "not_found") from None
    except (OSError, ValueError) as exc:
        raise StoreError("The project file could not be read (it may be damaged).", "damaged") from exc


def _summary(doc: dict) -> dict:
    scene = doc.get("scene") or {}
    return {
        "id": doc.get("id"),
        "name": doc.get("name") or "",
        "kind": scene.get("kind") or "",
        "created": doc.get("created") or "",
        "updated": doc.get("updated") or "",
        "rev": int(doc.get("rev") or 0),
        "width": scene.get("width"),
        "height": scene.get("height"),
        "nodes": len(scene.get("nodes") or []),
    }


def _clean_name(name: Any, scene: dict) -> str:
    s = " ".join(str(name or "").split())[:120]
    return s or str(scene.get("title") or "")[:120] or "Untitled"


def list_projects() -> list[dict]:
    """Newest first. Damaged files are skipped, not fatal."""
    out: list[dict] = []
    folder = projects_dir()
    if not folder.is_dir():
        return out
    for path in folder.glob("*.json"):
        if path.name.endswith(".versions.json") or not _ID.match(path.stem):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and doc.get("id") == path.stem:
            out.append(_summary(doc))
    out.sort(key=lambda d: d["updated"], reverse=True)
    return out


def load_project(pid: str) -> dict:
    doc = _read(_path(pid))
    if not isinstance(doc, dict) or not isinstance(doc.get("scene"), dict):
        raise StoreError("The project file could not be read (it may be damaged).", "damaged")
    return {**_summary(doc), "scene": doc["scene"]}


def _size_check(scene: dict) -> None:
    if len(json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_PROJECT_BYTES:
        raise StoreError("This figure is too large to save (embedded pictures count). Shrink or remove a picture.", "too_large")


def create_project(name: Any, scene: dict) -> dict:
    scene = normalize_scene(scene)
    _size_check(scene)
    with _LOCK:
        pid = secrets.token_hex(8)
        while _path(pid).exists():
            pid = secrets.token_hex(8)
        now = _now()
        doc = {"id": pid, "name": _clean_name(name, scene), "created": now, "updated": now, "rev": 1, "scene": scene}
        _write(_path(pid), doc)
    return _summary(doc)


def save_project(pid: str, scene: dict | None = None, name: Any = None, base_rev: int | None = None, snapshot: bool = False, label: str = "") -> dict:
    """Update a project. ``snapshot`` first files the stored state under Versions.

    ``base_rev`` is the revision the caller started from; a mismatch raises a ``conflict``.
    """
    with _LOCK:
        doc = _read(_path(pid))
        if not isinstance(doc, dict) or not isinstance(doc.get("scene"), dict):
            raise StoreError("The project file could not be read (it may be damaged).", "damaged")
        if base_rev is not None and int(base_rev) != int(doc.get("rev") or 0):
            raise StoreError("This figure was saved somewhere else in the meantime. Reload it, or save your copy under a new name.", "conflict")
        if snapshot:
            _push_version(pid, doc, label)
        if scene is not None:
            scene = normalize_scene(scene)
            _size_check(scene)
            doc["scene"] = scene
        if name is not None:
            doc["name"] = _clean_name(name, doc["scene"])
        doc["updated"] = _now()
        doc["rev"] = int(doc.get("rev") or 0) + 1
        _write(_path(pid), doc)
    return _summary(doc)


def delete_project(pid: str) -> None:
    with _LOCK:
        path = _path(pid)
        if not path.exists():
            raise StoreError("This project no longer exists.", "not_found")
        path.unlink()
        try:
            _path(pid, versions=True).unlink()
        except FileNotFoundError:
            pass


def duplicate_project(pid: str, name: Any = None) -> dict:
    src = load_project(pid)
    return create_project(name or f"{src['name']} (copy)", src["scene"])


# ------------------------------------------------------------------------------ versions
def _versions(pid: str) -> list[dict]:
    path = _path(pid, versions=True)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [v for v in data if isinstance(v, dict) and isinstance(v.get("scene"), dict)] if isinstance(data, list) else []


def _push_version(pid: str, doc: dict, label: str = "") -> None:
    versions = _versions(pid)
    versions.append({"at": _now(), "rev": int(doc.get("rev") or 0), "label": " ".join(str(label or "").split())[:80], "name": doc.get("name") or "", "scene": doc["scene"]})
    versions = versions[-MAX_VERSIONS:]
    # Old versions give way first when embedded pictures make the history heavy.
    while len(versions) > 1 and len(json.dumps(versions, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_VERSION_BYTES:
        versions.pop(0)
    _write(_path(pid, versions=True), versions)


def list_versions(pid: str) -> list[dict]:
    """Newest first; ``index`` is what :func:`load_version` takes."""
    if not _path(pid).exists():
        raise StoreError("This project no longer exists.", "not_found")
    out = [{"index": i, "at": v.get("at") or "", "rev": v.get("rev"), "label": v.get("label") or "", "nodes": len(v["scene"].get("nodes") or [])} for i, v in enumerate(_versions(pid))]
    return out[::-1]


def load_version(pid: str, index: int) -> dict:
    versions = _versions(pid)
    if not isinstance(index, int) or not 0 <= index < len(versions):
        raise StoreError("That version no longer exists.", "not_found")
    v = versions[index]
    return {"index": index, "at": v.get("at") or "", "label": v.get("label") or "", "scene": v["scene"]}


def snapshot_project(pid: str, label: str = "") -> list[dict]:
    """File the current state under Versions without changing it."""
    with _LOCK:
        doc = _read(_path(pid))
        if not isinstance(doc, dict) or not isinstance(doc.get("scene"), dict):
            raise StoreError("The project file could not be read (it may be damaged).", "damaged")
        _push_version(pid, doc, label)
    return list_versions(pid)
