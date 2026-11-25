"""Text metrics. Every box size in the app comes from these three functions,
so an off-by-a-bit here shows up as clipped labels everywhere.
"""

from __future__ import annotations

import pytest

from figwright.text import char_width, is_wide, text_block_size, text_width, wrap_text


def test_wide_characters_are_wide():
    assert is_wide("图") and is_wide("あ") and is_wide("가") and is_wide("，")
    assert not is_wide("a") and not is_wide(" ") and not is_wide(",")


def test_cjk_is_about_twice_as_wide_as_latin():
    assert char_width("图", 10) == pytest.approx(10.0)
    assert 4.0 < char_width("a", 10) < 7.5  # roughly half of a CJK character


def test_bold_is_wider_and_width_grows_with_size():
    assert text_width("Hello", 12, bold=True) > text_width("Hello", 12)
    assert text_width("Hello", 24) == pytest.approx(2 * text_width("Hello", 12), rel=1e-6)
    assert text_width("", 12) == 0


def test_wrap_breaks_on_spaces_and_keeps_words_whole():
    lines = wrap_text("the quick brown fox jumps over it", 90, 12)
    assert len(lines) > 1
    assert all(text_width(line, 12) <= 90 + 1e-6 for line in lines)
    assert " ".join(lines).split() == "the quick brown fox jumps over it".split()


def test_wrap_breaks_cjk_between_characters():
    lines = wrap_text("实验流程图自动排版", 40, 12)
    assert len(lines) > 1
    assert "".join(lines) == "实验流程图自动排版"


def test_wrap_respects_explicit_newlines():
    assert wrap_text("one\ntwo", 500, 12) == ["one", "two"]


def test_a_single_long_word_is_cut_rather_than_overflowing():
    lines = wrap_text("Methylenetetrahydrofolate", 40, 12)
    assert len(lines) > 1
    assert all(text_width(line, 12) <= 40 + 1e-6 for line in lines)


def test_block_size_matches_its_lines():
    w, h, lines = text_block_size("alpha beta gamma delta", 100, 12)
    assert lines and w <= 100 + 1e-6
    assert w == pytest.approx(max(text_width(line, 12) for line in lines))
    assert h >= 12 * len(lines)


def test_blank_text_takes_no_width():
    w, h, lines = text_block_size("   ", 100, 12)
    assert w == 0 and lines == [""] and h > 0
