"""Getting JSON out of language-model output.

Models wrap JSON in prose and code fences, leave trailing commas, write Python
literals, and get cut off mid-object when they hit the token limit.
:func:`extract_json` copes with all of that, and raises :class:`JSONExtractError`
with a short excerpt when it cannot.
"""

from __future__ import annotations

import json
import re
from typing import Any


class JSONExtractError(ValueError):
    """No usable JSON value could be recovered from the text."""


_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.S)
_OPEN = {"{": "}", "[": "]"}


def _scan(text: str, start: int) -> tuple[int, list[str], bool]:
    """Walk a JSON value from ``start``.

    Returns ``(end, stack, in_string)``: ``end`` is the index after the matching
    closer (or ``len(text)`` if the value is cut off), ``stack`` the closers
    still owed and ``in_string`` whether the text ended inside a string.
    """
    stack: list[str] = []
    in_str = False
    esc = False
    quote = '"'
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            quote = ch
        elif ch in _OPEN:
            stack.append(_OPEN[ch])
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
                if not stack:
                    return i + 1, [], False
            else:
                return i, stack, False  # stray closer: stop here
        i += 1
    return n, stack, in_str


def _strip_comments(s: str) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    in_str = False
    esc = False
    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
        elif s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _outside_strings(s: str, fn) -> str:
    """Apply ``fn`` to the parts of ``s`` that are not inside double-quoted strings."""
    parts: list[str] = []
    buf: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                parts.append("".join(buf))
                buf = []
        elif ch == '"':
            parts.append(fn("".join(buf)))
            buf = [ch]
            in_str = True
        else:
            buf.append(ch)
    tail = "".join(buf)
    parts.append(tail if in_str else fn(tail))
    return "".join(parts)


def _single_to_double(s: str) -> str:
    """Convert 'single-quoted' strings to JSON strings (only used as a late repair)."""
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '"':
            j = i + 1
            esc = False
            while j < n:
                if esc:
                    esc = False
                elif s[j] == "\\":
                    esc = True
                elif s[j] == '"':
                    break
                j += 1
            out.append(s[i : j + 1])
            i = j + 1
        elif ch == "'":
            j = i + 1
            buf: list[str] = []
            while j < n and s[j] != "'":
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j : j + 2] if s[j + 1] != "'" else "'")
                    j += 2
                    continue
                buf.append('\\"' if s[j] == '"' else s[j])
                j += 1
            out.append('"' + "".join(buf) + '"')
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _literals(chunk: str) -> str:
    chunk = re.sub(r"\bTrue\b", "true", chunk)
    chunk = re.sub(r"\bFalse\b", "false", chunk)
    chunk = re.sub(r"\b(None|undefined|NaN)\b", "null", chunk)
    chunk = re.sub(r",\s*([}\]])", r"\1", chunk)  # trailing commas
    chunk = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', chunk)  # bare keys
    return chunk


_STR = r'"(?:[^"\\]|\\.)*"'
_DANGLING_KEY = re.compile(r"([{,])\s*" + _STR + r"\s*:?\s*$")
_PARTIAL_WORD = re.compile(r":\s*([A-Za-z]+)$")
_PARTIAL_NUM = re.compile(r"(-?\d+(?:\.\d+)?)(?:\.|[eE][-+]?|-)$")


def _close(candidate: str, stack: list[str], in_string: bool) -> str:
    """Finish a value that was cut off: close the string, drop the dangling member, close brackets."""
    s = candidate + ('"' if in_string else "")
    in_object = bool(stack) and stack[-1] == "}"
    for _ in range(6):
        before = s
        s = s.rstrip()
        if s.endswith(","):
            s = s[:-1]
        if in_object:
            # `{"a": 1, "b` / `{"a": 1, "b":` -> the last member has no value yet.
            s = _DANGLING_KEY.sub(lambda m: m.group(1), s)
            m = _PARTIAL_WORD.search(s)
            if m and m.group(1) not in ("true", "false", "null"):
                word = m.group(1)
                literal = next((lit for lit in ("true", "false", "null") if lit.startswith(word)), "null")
                s = s[: m.start()] + ": " + literal
        s = _PARTIAL_NUM.sub(lambda m: m.group(1), s)
        s = re.sub(r":\s*-$", ":", s)  # a number that got no further than its sign
        if s == before:
            break
    return s.rstrip() + "".join(reversed(stack))


def _attempts(candidate: str, stack: list[str], in_string: bool):
    yield candidate
    cleaned = _strip_comments(candidate).replace("“", '"').replace("”", '"') if ('"' not in candidate) else _strip_comments(candidate)
    fixed = _outside_strings(cleaned, _literals)
    yield fixed
    if stack or in_string:
        _end, st2, in2 = _scan(fixed, 0)
        closed = _close(fixed, st2, in2)
        yield closed
        yield _outside_strings(closed, _literals)
    if "'" in fixed:
        sq = _outside_strings(_single_to_double(cleaned), _literals)
        yield sq
        if stack or in_string:
            _end, st3, in3 = _scan(sq, 0)
            yield _outside_strings(_close(sq, st3, in3), _literals)


def extract_json(text: str, expect: type | tuple[type, ...] = (dict, list)) -> Any:
    """Return the first JSON value of type ``expect`` found in ``text``."""
    if not isinstance(text, str) or not text.strip():
        raise JSONExtractError("The model returned an empty reply.")
    raw = text.strip().lstrip("﻿")
    sources = [m.group(1) for m in _FENCE.finditer(raw)] + [raw]
    # A reply cut off inside a code fence has an opening fence but no closing one.
    if raw.count("```") % 2 == 1:
        sources.insert(0, raw[raw.rfind("```") + 3 :].lstrip("jsonJSON \n"))
    last_error: Exception | None = None
    for src in sources:
        try:
            value = json.loads(src)
            if isinstance(value, expect):
                return value
        except ValueError:
            pass
        pos = 0
        tries = 0
        while tries < 6:
            starts = [p for p in (src.find("{", pos), src.find("[", pos)) if p >= 0]
            if not starts:
                break
            start = min(starts)
            end, stack, in_string = _scan(src, start)
            candidate = src[start:end]
            for attempt in _attempts(candidate, stack, in_string):
                try:
                    value = json.loads(attempt)
                except ValueError as exc:
                    last_error = exc
                    continue
                if isinstance(value, expect):
                    return value
            if stack or in_string:
                break  # cut off and beyond repair: do not settle for a fragment nested inside it
            pos = start + 1
            tries += 1
    excerpt = raw[:160].replace("\n", " ")
    raise JSONExtractError(f"Could not read JSON from the model reply ({last_error or 'no JSON found'}). It began: {excerpt!r}")
