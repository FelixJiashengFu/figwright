"""Edit operations: small, checkable changes to a scene.

Asking a model to "change the title" by re-emitting a 300-line scene is slow,
expensive and tends to damage things it was not asked to touch. Instead the
model (or the offline command parser, or an MCP client) returns a short list
of operations and :func:`apply_ops` applies them, validating each one.

Operations::

    {"op": "update", "id": "n3", "set": {"text": "New label", "fill": "#dbe9f8"}}
    {"op": "delete", "id": "n3"}                  (or "ids": [...])
    {"op": "add_node", "node": {...}}
    {"op": "add_edge", "edge": {"from": "a", "to": "b"}}
    {"op": "move", "id": "n3", "dx": 20, "dy": 0}  (or absolute "x" / "y")
    {"op": "replace_text", "find": "A", "replace": "B"}
    {"op": "set_title", "title": "..."}
    {"op": "set_theme", "theme": "forest"}
    {"op": "set_style", "set": {"fontSize": 18}}
    {"op": "set_canvas", "width": 1200, "height": 800, "background": "#ffffff"}
    {"op": "reorder", "id": "n3", "to": "front"}   (or "back")
    {"op": "replace_scene", "scene": {...}}
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .scene import norm_color, normalize_edge, normalize_node, normalize_scene
from .themes import THEMES, retheme

OP_NAMES = ("update", "delete", "add_node", "add_edge", "move", "replace_text", "set_title", "set_theme", "set_style", "set_canvas", "reorder", "replace_scene")

_OP_ALIASES = {
    "edit": "update",
    "modify": "update",
    "set": "update",
    "update_node": "update",
    "update_edge": "update",
    "remove": "delete",
    "delete_node": "delete",
    "delete_edge": "delete",
    "add": "add_node",
    "insert": "add_node",
    "connect": "add_edge",
    "link": "add_edge",
    "rename": "replace_text",
    "replace": "replace_text",
    "title": "set_title",
    "theme": "set_theme",
    "style": "set_style",
    "canvas": "set_canvas",
    "resize_canvas": "set_canvas",
    "bring_to_front": "reorder",
    "send_to_back": "reorder",
}


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v == v:
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _find(scene: dict, ident: Any) -> tuple[str, int] | None:
    for i, n in enumerate(scene["nodes"]):
        if n["id"] == ident:
            return "nodes", i
    for i, e in enumerate(scene["edges"]):
        if e["id"] == ident:
            return "edges", i
    return None


def _title_node(scene: dict) -> dict | None:
    for n in scene["nodes"]:
        if n["id"] == "title" or n.get("role") == "title":
            return n
    return None


def apply_ops(scene: dict, ops: Any) -> tuple[dict, list[str], list[str]]:
    """Apply ``ops`` to a copy of ``scene``.

    Returns ``(scene, applied, skipped)`` where the two lists are human-readable
    notes. Invalid operations are skipped, never raised: a model that gets one
    id wrong should not lose the nine edits it got right.
    """
    out = deepcopy(scene)
    out.setdefault("nodes", [])
    out.setdefault("edges", [])
    applied: list[str] = []
    skipped: list[str] = []
    if isinstance(ops, str):
        # Some models answer with the list as a string. Read it rather than refuse it.
        try:
            from .jsonx import extract_json

            ops = extract_json(ops)
        except Exception:
            return out, applied, ["the operations could not be read as JSON"]
    if isinstance(ops, dict):
        ops = ops.get("ops") or ops.get("operations") or ops.get("edits") or [ops]
    if not isinstance(ops, list):
        return out, applied, ["no operations were given"]

    for raw in ops[:400]:
        if not isinstance(raw, dict):
            skipped.append("ignored a non-object operation")
            continue
        name = str(raw.get("op") or raw.get("action") or raw.get("type") or "").strip().lower()
        original = name
        name = _OP_ALIASES.get(name, name)
        style = out.get("style") or {}

        if name == "replace_scene":
            new = raw.get("scene")
            if not isinstance(new, dict):
                skipped.append("replace_scene without a scene")
                continue
            try:
                replaced = normalize_scene(new, base_style=style if style.get("locked") else None)
            except ValueError as exc:
                skipped.append(f"replace_scene: {exc}")
                continue
            if not replaced["nodes"]:
                skipped.append("replace_scene: the new scene is empty")
                continue
            replaced["meta"] = out.get("meta", {})
            if not replaced.get("title"):
                replaced["title"] = out.get("title", "")
            replaced["kind"] = out.get("kind", replaced["kind"])
            out = replaced
            applied.append("replaced the whole figure")

        elif name == "update":
            ident = raw.get("id")
            changes = raw.get("set") or raw.get("props") or raw.get("changes") or {k: v for k, v in raw.items() if k not in ("op", "action", "type", "id")}
            where = _find(out, ident)
            if where is None or not isinstance(changes, dict) or not changes:
                skipped.append(f"update: nothing called {ident!r}" if where is None else "update without changes")
                continue
            kind, idx = where
            merged = dict(out[kind][idx])
            for k, v in changes.items():
                if k == "id":
                    continue
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            if kind == "nodes":
                if merged.get("type") != out[kind][idx].get("type") and "icon" in changes and merged.get("type") != "icon":
                    merged["type"] = "icon"
                used = {n["id"] for n in out["nodes"] if n["id"] != ident}
                node = normalize_node(merged, style, used, idx)
                if node is None:
                    skipped.append(f"update: {ident!r} became invalid")
                    continue
                out["nodes"][idx] = node
            else:
                ids = {n["id"] for n in out["nodes"]}
                used = {e["id"] for e in out["edges"] if e["id"] != ident} | ids
                edge = normalize_edge(merged, ids, used, idx)
                if edge is None:
                    skipped.append(f"update: connector {ident!r} lost an endpoint")
                    continue
                out["edges"][idx] = edge
            applied.append(f"updated {ident}")

        elif name == "delete":
            ids = raw.get("ids") if isinstance(raw.get("ids"), list) else [raw.get("id")]
            gone = [i for i in ids if _find(out, i) is not None]
            if not gone:
                skipped.append(f"delete: nothing called {ids!r}")
                continue
            dead = set(gone)
            out["nodes"] = [n for n in out["nodes"] if n["id"] not in dead]
            out["edges"] = [e for e in out["edges"] if e["id"] not in dead and not any(isinstance(end, str) and end in dead for end in (e["from"], e["to"]))]
            applied.append("deleted " + ", ".join(str(g) for g in gone))

        elif name == "add_node":
            node_raw = raw.get("node") if isinstance(raw.get("node"), dict) else {k: v for k, v in raw.items() if k not in ("op", "action")}
            if original in ("add", "insert") and "from" in node_raw and "to" in node_raw:
                name, raw = "add_edge", {"edge": node_raw}
            else:
                used = {n["id"] for n in out["nodes"]} | {e["id"] for e in out["edges"]}
                node = normalize_node(node_raw, style, used, len(out["nodes"]))
                if node is None:
                    skipped.append("add_node: invalid node")
                    continue
                out["nodes"].append(node)
                applied.append(f"added {node['id']}")
        if name == "add_edge":
            edge_raw = raw.get("edge") if isinstance(raw.get("edge"), dict) else {k: v for k, v in raw.items() if k not in ("op", "action")}
            ids = {n["id"] for n in out["nodes"]}
            used = {e["id"] for e in out["edges"]} | ids
            edge = normalize_edge(edge_raw, ids, used, len(out["edges"]))
            if edge is None:
                skipped.append("add_edge: unknown endpoint")
                continue
            out["edges"].append(edge)
            applied.append(f"connected {edge['from']} to {edge['to']}")

        elif name == "move":
            where = _find(out, raw.get("id"))
            if where is None or where[0] != "nodes":
                skipped.append(f"move: no element called {raw.get('id')!r}")
                continue
            node = out["nodes"][where[1]]
            x, y, dx, dy = _num(raw.get("x")), _num(raw.get("y")), _num(raw.get("dx")), _num(raw.get("dy"))
            ox, oy = node["x"], node["y"]
            node["x"] = round(x if x is not None else node["x"] + (dx or 0.0), 1)
            node["y"] = round(y if y is not None else node["y"] + (dy or 0.0), 1)
            if raw.get("group") is not False and node.get("group"):
                for other in out["nodes"]:
                    if other is not node and other.get("group") == node["group"]:
                        other["x"] = round(other["x"] + node["x"] - ox, 1)
                        other["y"] = round(other["y"] + node["y"] - oy, 1)
            applied.append(f"moved {node['id']}")

        elif name == "replace_text":
            find, repl = raw.get("find") or raw.get("from") or raw.get("old"), raw.get("replace") if raw.get("replace") is not None else raw.get("to", raw.get("new"))
            if not isinstance(find, str) or not find or not isinstance(repl, str):
                skipped.append("replace_text needs 'find' and 'replace'")
                continue
            count = 0
            for n in out["nodes"]:
                if isinstance(n.get("text"), str) and find in n["text"]:
                    n["text"] = n["text"].replace(find, repl)
                    count += 1
            for e in out["edges"]:
                if isinstance(e.get("label"), str) and find in e["label"]:
                    e["label"] = e["label"].replace(find, repl)
                    count += 1
            if isinstance(out.get("title"), str) and find in out["title"]:
                out["title"] = out["title"].replace(find, repl)
            if count:
                applied.append(f"replaced {find!r} in {count} place(s)")
            else:
                skipped.append(f"replace_text: {find!r} does not occur")

        elif name == "set_title":
            title = raw.get("title") if raw.get("title") is not None else raw.get("text")
            if not isinstance(title, str):
                skipped.append("set_title without a title")
                continue
            out["title"] = title[:200]
            node = _title_node(out)
            if node is not None:
                node["text"] = title[:200]
            applied.append("changed the title")

        elif name == "set_theme":
            theme = str(raw.get("theme") or raw.get("name") or "").strip().lower()
            if theme not in THEMES:
                skipped.append(f"set_theme: unknown theme {theme!r} (available: {', '.join(THEMES)})")
                continue
            out = retheme(out, theme)
            applied.append(f"switched to the {theme} theme")

        elif name == "set_style":
            changes = raw.get("set") if isinstance(raw.get("set"), dict) else {k: v for k, v in raw.items() if k not in ("op", "action")}
            scale = None
            new_fs = _num(changes.get("fontSize"))
            old_fs = _num(style.get("fontSize")) or 16.0
            if new_fs and new_fs > 0:
                scale = max(6.0, min(120.0, new_fs)) / old_fs
            merged = dict(out)
            merged["style"] = {**style, **changes}
            keep_meta = out.get("meta", {})
            out = normalize_scene(merged)
            out["meta"] = keep_meta
            if scale and abs(scale - 1) > 1e-6:
                # Elements with their own font size follow the global change proportionally.
                for n in out["nodes"]:
                    if "fontSize" in n:
                        n["fontSize"] = round(max(6.0, n["fontSize"] * scale), 1)
            applied.append("updated the style")

        elif name == "set_canvas":
            w, h = _num(raw.get("width")), _num(raw.get("height"))
            if w and 100 <= w <= 12000:
                out["width"] = round(w, 1)
            if h and 100 <= h <= 12000:
                out["height"] = round(h, 1)
            bg = norm_color(raw.get("background"))
            if bg:
                out["background"] = bg
            applied.append("updated the canvas")

        elif name == "reorder":
            where = _find(out, raw.get("id"))
            to = str(raw.get("to") or ("back" if original == "send_to_back" else "front")).lower()
            if where is None:
                skipped.append(f"reorder: nothing called {raw.get('id')!r}")
                continue
            kind, idx = where
            item = out[kind].pop(idx)
            if to in ("back", "bottom", "first"):
                out[kind].insert(0, item)
            else:
                out[kind].append(item)
            applied.append(f"moved {item['id']} to the {'back' if to in ('back', 'bottom', 'first') else 'front'}")

        elif name not in ("replace_scene", "update", "delete", "add_node", "add_edge"):
            skipped.append(f"unknown operation {original!r}")

    return out, applied, skipped
