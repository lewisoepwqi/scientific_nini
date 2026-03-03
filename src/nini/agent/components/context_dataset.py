"""数据集上下文构建逻辑。"""

from __future__ import annotations

from typing import Any

from nini.agent.prompt_policy import format_untrusted_context_block
from nini.agent.session import Session
from nini.agent.components.context_utils import sanitize_for_system_context


def build_dataset_context(session: Session) -> tuple[str, list[str]]:
    """构建数据集元信息上下文，并返回列名列表。"""
    columns: list[str] = []
    if not session.datasets:
        return "", columns

    dataset_info_parts: list[str] = []
    for name, df in session.datasets.items():
        safe_name = sanitize_for_system_context(name, max_len=80)
        cols = ", ".join(
            f"{sanitize_for_system_context(column, max_len=48)}"
            f"({sanitize_for_system_context(str(df[column].dtype), max_len=24)})"
            for column in df.columns[:10]
        )
        extra = f" ... 等共 {len(df.columns)} 列" if len(df.columns) > 10 else ""
        dataset_info_parts.append(f'- 数据集名="{safe_name}"; {len(df)} 行; 列: {cols}{extra}')
        columns.extend(df.columns.tolist())

    return (
        format_untrusted_context_block(
            "dataset_metadata",
            "```text\n" + "\n".join(dataset_info_parts) + "\n```",
        ),
        columns,
    )
