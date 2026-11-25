"""Shared helpers for the deterministic layout builders."""

from __future__ import annotations

import re
from typing import Any

from ..icons import ICONS, match_icon
from ..scene import new_scene
from ..text import LINE_HEIGHT, is_wide, text_block_size
from ..themes import get_theme

MARGIN = 40.0


def has_cjk(*texts: Any) -> bool:
    return any(is_wide(ch) for t in texts if isinstance(t, str) for ch in t)


def clean(value: Any, limit: int = 400) -> str:
    """Coerce model output to a tidy single string."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = "\n".join(clean(v, limit) for v in value)
    s = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    s = re.sub(r"[ \t]+", " ", s)
    return s[:limit]


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def slug(value: Any, fallback: str) -> str:
    s = re.sub(r"[^\w\-]", "_", str(value or "")).strip("_")[:32]
    return s or fallback


def pick_icon(name: Any, text: str, default: str = "gear") -> str:
    n = str(name or "").strip().lower()
    if n in ICONS:
        return n
    return match_icon(f"{n} {text}", default=default) or default


class Canvas:
    """Accumulates nodes and edges with automatic ids and theme lookups."""

    def __init__(self, theme: str | None, kind: str, title: str = "") -> None:
        self.scene = new_scene(theme=theme, kind=kind, title=title)
        self.style = self.scene["style"]
        self.t = get_theme(self.style["theme"])
        self._n = 0
        self._e = 0

    # -- theme shortcuts ---------------------------------------------------------
    def soft(self, i: int) -> str:
        return self.t["soft"][i % len(self.t["soft"])]

    def strong(self, i: int) -> str:
        return self.t["strong"][i % len(self.t["strong"])]

    @property
    def ink(self) -> str:
        return self.t["ink"]

    @property
    def muted(self) -> str:
        return self.t["muted"]

    @property
    def line(self) -> str:
        return self.t["line"]

    @property
    def panel(self) -> str:
        return self.t["panel"]

    # -- building ------------------------------------------------------------------
    def add(self, type_: str, x: float, y: float, w: float, h: float, id: str | None = None, **props: Any) -> str:
        self._n += 1
        nid = id or f"n{self._n}"
        node = {"id": nid, "type": type_, "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)}
        node.update({k: v for k, v in props.items() if v is not None and v != ""})
        self.scene["nodes"].append(node)
        return nid

    def edge(self, a: Any, b: Any, **props: Any) -> str:
        self._e += 1
        eid = f"e{self._e}"
        edge = {"id": eid, "from": a, "to": b, "head": props.pop("head", "arrow")}
        edge.update({k: v for k, v in props.items() if v is not None and v != "" and v is not False})
        self.scene["edges"].append(edge)
        return eid

    def text_size(self, text: str, max_w: float, fs: float, bold: bool = False) -> tuple[float, float]:
        w, h, _lines = text_block_size(text, max_w, fs, bold)
        return w, h

    def title(self, text: str, width: float, y: float = MARGIN - 8, fs: float = 24) -> float:
        """Add a centred title; returns the y coordinate below it."""
        text = clean(text, 160)
        if not text:
            return y
        _w, h = self.text_size(text, width - 2 * MARGIN, fs, True)
        self.add("text", MARGIN, y, width - 2 * MARGIN, h + 4, id="title", text=text, fontSize=fs, fontWeight="bold", color=self.ink, role="title")
        return y + h + 22

    def finish(self, width: float, height: float) -> dict:
        self.scene["width"] = round(max(200.0, width), 1)
        self.scene["height"] = round(max(160.0, height), 1)
        return self.scene


def line_height(fs: float) -> float:
    return fs * LINE_HEIGHT
