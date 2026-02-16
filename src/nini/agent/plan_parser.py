"""解析 LLM 文本为结构化分析步骤列表。

纯函数模块，不依赖外部状态。当 LLM 输出编号列表格式的分析计划时，
将其解析为 AnalysisPlan 供前端渲染步骤进度。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

StepStatus = Literal["pending", "in_progress", "completed", "error"]


@dataclass
class AnalysisStep:
    """单个分析步骤。"""

    id: int  # 1-based
    title: str  # "检查数据集基本结构"
    tool_hint: str | None = None  # "load_dataset"
    status: StepStatus = "pending"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "tool_hint": self.tool_hint,
            "status": self.status,
        }


@dataclass
class AnalysisPlan:
    """完整的分析计划。"""

    steps: list[AnalysisStep] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "raw_text": self.raw_text,
        }


# 匹配编号列表行：1. 标题 - 使用工具: tool_name
# 或：1. 标题（无工具提示）
_STEP_PATTERN = re.compile(
    r"^\s*(\d+)\.\s+"  # 编号
    r"(.+?)"  # 标题（非贪婪）
    r"(?:\s*[-—–]\s*使用工具[:：]\s*(\w+))?"  # 可选的工具提示
    r"\s*$"
)


def parse_analysis_plan(text: str) -> AnalysisPlan | None:
    """解析编号列表为步骤。至少 2 步才返回，否则 None（回退旧行为）。

    支持格式：
        1. 加载并检查数据集 - 使用工具: load_dataset
        2. 正态性检验 - 使用工具: run_code
        3. 汇总结论

    Args:
        text: LLM 第一次迭代输出的文本（分析思路）。

    Returns:
        解析成功返回 AnalysisPlan，否则 None。
    """
    steps: list[AnalysisStep] = []

    for line in text.splitlines():
        m = _STEP_PATTERN.match(line)
        if m:
            step_id = int(m.group(1))
            title = m.group(2).strip().rstrip("-—–").strip()
            tool_hint = m.group(3) or None
            steps.append(AnalysisStep(id=step_id, title=title, tool_hint=tool_hint))

    if len(steps) < 2:
        return None

    return AnalysisPlan(steps=steps, raw_text=text)
