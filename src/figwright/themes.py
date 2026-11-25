"""Colour themes.

A theme is a small set of named slots. Builders and the LLM prompt only ever
use slot colours, which is what makes "apply another theme" and "keep the same
look across every figure of a paper" possible: swapping a theme is a slot-for-
slot colour substitution.
"""

from __future__ import annotations

from copy import deepcopy

FONT_STACK = "Inter, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', 'WenQuanYi Zen Hei', sans-serif"

THEMES: dict[str, dict] = {
    "ink": {
        "label": {"zh": "墨蓝", "en": "Ink"},
        "bg": "#ffffff",
        "ink": "#1f2a44",
        "muted": "#5b6478",
        "line": "#3b4a66",
        "panel": "#f4f6fa",
        "strong": ["#2f6fb7", "#e07a3f", "#2a9d8f", "#b8558b", "#8a6fd1", "#c9a227"],
        "soft": ["#dbe9f8", "#fbe6d8", "#d9f0ec", "#f5dcea", "#e6defa", "#f6edc9"],
    },
    "coral": {
        "label": {"zh": "珊瑚", "en": "Coral"},
        "bg": "#fffdfa",
        "ink": "#3a2a2a",
        "muted": "#7a6a66",
        "line": "#5a4642",
        "panel": "#fbf3ee",
        "strong": ["#e4572e", "#17a398", "#f3a712", "#5d5fa8", "#a8327e", "#4f8f3a"],
        "soft": ["#fde0d6", "#d5f1ee", "#fdeec9", "#e0e0f3", "#f3d9e8", "#dcedd5"],
    },
    "forest": {
        "label": {"zh": "森林", "en": "Forest"},
        "bg": "#ffffff",
        "ink": "#1e2d24",
        "muted": "#5a6b60",
        "line": "#35493c",
        "panel": "#f1f6f1",
        "strong": ["#2d7d46", "#c8553d", "#3b6ea5", "#b9892b", "#7b4fa0", "#2a8f9d"],
        "soft": ["#d8eedd", "#f8ded8", "#dbe7f5", "#f6ebcf", "#e9def3", "#d6eff2"],
    },
    "mono": {
        "label": {"zh": "极简灰", "en": "Mono"},
        "bg": "#ffffff",
        "ink": "#111827",
        "muted": "#6b7280",
        "line": "#374151",
        "panel": "#f3f4f6",
        "strong": ["#1f2937", "#4b5563", "#9ca3af", "#0f172a", "#6b7280", "#d1d5db"],
        "soft": ["#eef0f3", "#e5e7eb", "#f9fafb", "#dfe3e8", "#f3f4f6", "#fbfbfc"],
    },
    # Colour-blind-safe palette by Masataka Okabe and Kei Ito ("Color Universal Design").
    "okabe": {
        "label": {"zh": "色盲友好 (Okabe-Ito)", "en": "Okabe-Ito (colour-blind safe)"},
        "bg": "#ffffff",
        "ink": "#1a1a1a",
        "muted": "#555555",
        "line": "#333333",
        "panel": "#f5f5f5",
        "strong": ["#0072b2", "#e69f00", "#009e73", "#cc79a7", "#56b4e9", "#d55e00"],
        "soft": ["#d6e9f5", "#fbefd2", "#d4f0e7", "#f6e3ee", "#e0f1fb", "#f8dfd0"],
    },
}

DEFAULT_THEME = "ink"


def get_theme(name: str | None) -> dict:
    return THEMES.get(name or DEFAULT_THEME, THEMES[DEFAULT_THEME])


def style_for_theme(name: str | None = None) -> dict:
    """Build the ``scene.style`` object for a theme."""
    key = name if name in THEMES else DEFAULT_THEME
    t = THEMES[key]
    return {
        "theme": key,
        "fontFamily": FONT_STACK,
        "fontSize": 16,
        "textColor": t["ink"],
        "mutedColor": t["muted"],
        "stroke": t["line"],
        "strokeWidth": 2,
        "fill": t["soft"][0],
        "panel": t["panel"],
        "edgeColor": t["line"],
        "edgeWidth": 2,
        "cornerRadius": 10,
        "arrowSize": 9,
        "palette": list(t["strong"]),
        "soft": list(t["soft"]),
        "locked": False,
    }


def _slot_pairs(old: dict, new: dict) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for key in ("bg", "ink", "muted", "line", "panel"):
        pairs[old[key].lower()] = new[key]
    for i, c in enumerate(old["strong"]):
        pairs[c.lower()] = new["strong"][i % len(new["strong"])]
    for i, c in enumerate(old["soft"]):
        pairs[c.lower()] = new["soft"][i % len(new["soft"])]
    return pairs


def retheme(scene: dict, new_theme: str) -> dict:
    """Return a copy of ``scene`` recoloured from its current theme to ``new_theme``.

    Colours that are not theme slots (hand-picked by the user) are left alone.
    """
    out = deepcopy(scene)
    style = out.get("style") or {}
    old = get_theme(style.get("theme"))
    new = get_theme(new_theme)
    if new_theme not in THEMES:
        return out
    pairs = _slot_pairs(old, new)

    def swap(v):
        if isinstance(v, str) and v.lower() in pairs:
            return pairs[v.lower()]
        return v

    for node in out.get("nodes", []):
        for k in ("fill", "stroke", "color", "accent"):
            if k in node:
                node[k] = swap(node[k])
    for edge in out.get("edges", []):
        if "color" in edge:
            edge["color"] = swap(edge["color"])
    if "background" in out:
        out["background"] = swap(out["background"])
    keep = {k: style[k] for k in ("fontFamily", "fontSize", "strokeWidth", "edgeWidth", "cornerRadius", "arrowSize", "locked") if k in style}
    new_style = style_for_theme(new_theme)
    new_style.update(keep)
    out["style"] = new_style
    return out
