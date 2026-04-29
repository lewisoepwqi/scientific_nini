"""Markdown 兜底修复工具。

目前只处理一类模型常见输出缺陷：GFM 表格分隔行写成纯冒号（如 `|:|:|`），
不符合 CommonMark/GFM 规范，在严格解析器下渲染失败。
"""

from __future__ import annotations

import re

# 判定"仅含 | 、: 、- 和空白、至少两个 |"的整行为疑似分隔行。
_SEPARATOR_LINE_RE = re.compile(r"^\s*\|(?:\s*:?-*:?\s*\|){2,}\s*$")
# 匹配分隔行中双冒号单元 `|::|`（居中对齐缩写，应为 `|:---:|`）。
# 必须在单冒号匹配之前应用，避免被误吃成两段 `|:`。
_BARE_DOUBLE_COLON_CELL_RE = re.compile(r"\|\s*::\s*(?=\|)")
# 匹配分隔行中单冒号单元格 `|:|`（左对齐缩写，应为 `|:---|`）。
_BARE_COLON_CELL_RE = re.compile(r"\|\s*:\s*(?=\|)")


def fix_markdown_table_separator(text: str) -> str:
    """把疑似表格分隔行里的冒号缩写补齐为合规分隔行。

    覆盖国产 thinking 模型常见的两种缩写：
    - `|:|`  → `|:---|`   （左对齐）
    - `|::|` → `|:---:|`  （居中对齐）

    对已包含 `-` 的合规单元不做修改，保持幂等。
    """
    if not text:
        return text

    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not _SEPARATOR_LINE_RE.match(line):
            continue
        # 先处理 `|::|`（居中），再处理 `|:|`（左），避免单冒号正则吃掉双冒号的第一段
        line = _BARE_DOUBLE_COLON_CELL_RE.sub("|:---:", line)
        line = _BARE_COLON_CELL_RE.sub("|:---", line)
        lines[i] = line
    return "\n".join(lines)
