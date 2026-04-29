"""Markdown 兜底修复测试。"""

from __future__ import annotations

from nini.utils.markdown_fixups import fix_markdown_table_separator


def test_fix_colon_only_separator_to_left_aligned() -> None:
    """|:|:|:| 应被修复为 |:---|:---|:---|。"""
    src = "| a | b | c |\n" "|:|:|:|\n" "| 1 | 2 | 3 |\n"
    out = fix_markdown_table_separator(src)
    assert "|:---|:---|:---|" in out
    assert "|:|:|:|" not in out


def test_fix_bare_colon_and_dash_mix() -> None:
    """|:|---|:| 里只修复单冒号单元，不动合规单元。"""
    src = "|:|---|:|"
    out = fix_markdown_table_separator(src)
    assert out == "|:---|---|:---|"


def test_preserves_valid_separators() -> None:
    """合规分隔行不变。"""
    src = "|:---|:---:|---:|"
    assert fix_markdown_table_separator(src) == src


def test_non_separator_lines_untouched() -> None:
    """正文中的 |:| 若非分隔行不动。"""
    src = "some text with |:| inside that is not a table separator"
    assert fix_markdown_table_separator(src) == src


def test_idempotent() -> None:
    """函数幂等，反复调用结果相同。"""
    src = "| a | b |\n|:|:|\n| 1 | 2 |\n"
    once = fix_markdown_table_separator(src)
    twice = fix_markdown_table_separator(once)
    assert once == twice


def test_empty_and_none_safe() -> None:
    assert fix_markdown_table_separator("") == ""


def test_fix_double_colon_separator_to_centered() -> None:
    """|::| 居中缩写应被修复为 |:---:|（DeepSeek/GLM 常见输出）。"""
    src = "| 指标 | ISX | Mock |\n|:|::|:|\n| 样本量 | 187 | 174 |\n"
    out = fix_markdown_table_separator(src)
    assert "|:---|:---:|:---|" in out
    assert "|:|::|:|" not in out


def test_fix_mixed_centered_and_left_columns() -> None:
    """4 列混合左/居中对齐缩写。"""
    src = "| a | b | c | d |\n|:|::|::|:|\n| 1 | 2 | 3 | 4 |\n"
    out = fix_markdown_table_separator(src)
    assert "|:---|:---:|:---:|:---|" in out


def test_build_text_event_applies_fixup() -> None:
    """build_text_event 产出的事件 content 已通过分隔行修复。"""
    from nini.agent.event_builders import build_text_event

    ev = build_text_event("| a | b |\n|:|:|\n| 1 | 2 |\n")
    assert "|:---|:---|" in ev.data["content"]
    assert "|:|:|" not in ev.data["content"]
