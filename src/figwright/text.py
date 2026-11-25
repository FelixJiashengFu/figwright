"""Text measurement and wrapping.

SVG has no automatic line wrapping, so both renderers (this module and its
JavaScript twin in ``web/scene.js``) estimate glyph widths with the same small
table and break lines the same way. The numbers approximate a typical
sans-serif (Arial / Inter / PingFang); they only need to be good enough to
decide where a line breaks and whether a label fits its box.

Keep this file and ``wrapText`` in ``web/scene.js`` in sync.
"""

from __future__ import annotations

LINE_HEIGHT = 1.3

_NARROW = set("iljI.,:;'|!`")
_SEMI = set("ftr()[]{}-\"*/\\")
_WIDE = set("mwMW@%")
# Punctuation that must not start a line (CJK and Latin closers).
NO_LINE_START = set("，。、；：！？）》」』】〉…,.;:!?)]}%")


def is_wide(ch: str) -> bool:
    """True for CJK / full-width characters, which occupy a full em."""
    o = ord(ch)
    return (
        0x1100 <= o <= 0x115F
        or 0x2E80 <= o <= 0xA4CF
        or 0xAC00 <= o <= 0xD7A3
        or 0xF900 <= o <= 0xFAFF
        or 0xFE30 <= o <= 0xFE4F
        or 0xFF00 <= o <= 0xFF60
        or 0xFFE0 <= o <= 0xFFE6
        or 0x20000 <= o <= 0x3FFFD
    )


def char_width(ch: str, font_size: float, bold: bool = False) -> float:
    if is_wide(ch):
        w = 1.0
    elif ch == " ":
        w = 0.28
    elif ch in _NARROW:
        w = 0.28
    elif ch in _SEMI:
        w = 0.36
    elif ch in _WIDE:
        w = 0.88
    elif "A" <= ch <= "Z":
        w = 0.68
    elif "0" <= ch <= "9":
        w = 0.56
    else:
        w = 0.54
    if bold:
        w *= 1.06
    return w * font_size


def text_width(s: str, font_size: float, bold: bool = False) -> float:
    return sum(char_width(c, font_size, bold) for c in s)


def _tokens(par: str) -> list[str]:
    """Split a paragraph into break opportunities.

    Latin words stay whole, every wide (CJK) character is its own token and a
    run of spaces becomes a single " " token.
    """
    out: list[str] = []
    word = ""
    for ch in par:
        if ch in (" ", "\t"):
            if word:
                out.append(word)
                word = ""
            if not out or out[-1] != " ":
                out.append(" ")
        elif is_wide(ch):
            if word:
                out.append(word)
                word = ""
            out.append(ch)
        else:
            word += ch
    if word:
        out.append(word)
    return out


def wrap_text(text: str, max_width: float, font_size: float, bold: bool = False) -> list[str]:
    """Wrap ``text`` to ``max_width`` pixels. Explicit newlines are kept."""
    if text is None:
        return []
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    max_width = max(float(max_width), font_size)
    lines: list[str] = []
    space_w = char_width(" ", font_size, bold)
    for par in text.split("\n"):
        cur = ""
        cur_w = 0.0
        pending_space = False
        for tok in _tokens(par):
            if tok == " ":
                pending_space = bool(cur)
                continue
            tw = text_width(tok, font_size, bold)
            if tw > max_width and len(tok) > 1:
                # A single word longer than the line: break it by characters.
                if cur:
                    lines.append(cur)
                    cur, cur_w = "", 0.0
                piece, piece_w = "", 0.0
                for ch in tok:
                    cw = char_width(ch, font_size, bold)
                    if piece and piece_w + cw > max_width:
                        lines.append(piece)
                        piece, piece_w = "", 0.0
                    piece += ch
                    piece_w += cw
                cur, cur_w = piece, piece_w
                pending_space = False
                continue
            add = tw + (space_w if (pending_space and cur) else 0.0)
            keep = len(tok) == 1 and tok in NO_LINE_START
            if cur and cur_w + add > max_width and not keep:
                lines.append(cur)
                cur, cur_w = tok, tw
            else:
                cur += (" " if (pending_space and cur) else "") + tok
                cur_w += add
            pending_space = False
        lines.append(cur)
    return lines


def text_block_size(text: str, max_width: float, font_size: float, bold: bool = False) -> tuple[float, float, list[str]]:
    """Return (width, height, lines) of wrapped text."""
    lines = wrap_text(text, max_width, font_size, bold)
    w = max((text_width(line, font_size, bold) for line in lines), default=0.0)
    return w, len(lines) * font_size * LINE_HEIGHT, lines
