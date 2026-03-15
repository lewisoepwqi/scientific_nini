"""假设驱动推理上下文。

提供 Hypothesis 和 HypothesisContext 数据类，用于在 Hypothesis-Driven 范式中
跟踪假设列表、置信度更新和三条件收敛判断。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

VALID_STATUSES = {"pending", "validated", "refuted", "revised"}


@dataclass
class Hypothesis:
    """单个假设的状态记录。"""

    id: str
    content: str
    confidence: float = 0.5
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class HypothesisContext:
    """假设推理上下文，存储于 SubSession.artifacts["_hypothesis_context"]。

    管理假设列表、当前推理阶段、迭代计数及收敛判断逻辑。
    """

    hypotheses: list[Hypothesis] = field(default_factory=list)
    current_phase: str = "generation"
    iteration_count: int = 0
    max_iterations: int = 3
    _prev_confidences: list[float] = field(default_factory=list)

    def should_conclude(self) -> bool:
        """三条件收敛判断，满足任一条件即返回 True。

        条件 1：iteration_count >= max_iterations（硬上限）
        条件 2：所有假设均已定论（无 pending 状态）
        条件 3：贝叶斯收敛（相邻两轮最大置信度变化 < 0.05）
        """
        # 条件 1：硬上限
        if self.iteration_count >= self.max_iterations:
            return True

        # 条件 2：所有假设已定论
        if self.hypotheses and all(h.status in {"validated", "refuted"} for h in self.hypotheses):
            return True

        # 条件 3：贝叶斯收敛
        if self.hypotheses and len(self._prev_confidences) == len(self.hypotheses):
            delta = max(
                abs(h.confidence - prev) for h, prev in zip(self.hypotheses, self._prev_confidences)
            )
            if delta < 0.05:
                return True

        return False

    def update_confidence(self, hypothesis_id: str, evidence_type: str) -> None:
        """更新指定假设的置信度。

        先保存当前置信度快照到 _prev_confidences，再执行更新：
        - evidence_type == "for"：+0.15（上限 1.0）
        - evidence_type == "against"：-0.20（下限 0.0）

        Args:
            hypothesis_id: 目标假设 ID
            evidence_type: "for" 或 "against"
        """
        # 保存快照
        self._prev_confidences = [h.confidence for h in self.hypotheses]

        for h in self.hypotheses:
            if h.id == hypothesis_id:
                if evidence_type == "for":
                    h.confidence = min(1.0, h.confidence + 0.15)
                elif evidence_type == "against":
                    h.confidence = max(0.0, h.confidence - 0.20)
                else:
                    logger.warning(
                        "update_confidence: 未知 evidence_type '%s'，跳过更新",
                        evidence_type,
                    )
                return

        logger.warning("update_confidence: 未找到 hypothesis_id '%s'", hypothesis_id)
