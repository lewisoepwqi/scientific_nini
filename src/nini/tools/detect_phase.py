"""研究阶段检测工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.models.risk import ResearchPhase
from nini.tools.base import Tool, ToolResult

_PHASE_KEYWORDS: dict[ResearchPhase, tuple[str, ...]] = {
    ResearchPhase.LITERATURE_REVIEW: (
        "文献综述",
        "文献调研",
        "相关研究",
        "研究现状",
        "综述",
        "systematic review",
        "literature review",
        "related work",
    ),
    ResearchPhase.EXPERIMENT_DESIGN: (
        "实验设计",
        "研究设计",
        "研究方案",
        "方案设计",
        "样本量",
        "功效分析",
        "随机对照",
        "rct",
        "效应量",
        "sample size",
        "power analysis",
    ),
    ResearchPhase.PAPER_WRITING: (
        "写论文",
        "论文写作",
        "写作",
        "方法章节",
        "结果章节",
        "讨论章节",
        "引言",
        "摘要",
        "论文初稿",
        "paper writing",
        "manuscript",
    ),
}

_DEFAULT_PHASE = ResearchPhase.DATA_ANALYSIS


def detect_phase_from_text(user_message: str) -> tuple[ResearchPhase, float, list[str]]:
    """基于关键词匹配检测研究阶段。"""
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return _DEFAULT_PHASE, 0.0, []

    best_phase = _DEFAULT_PHASE
    best_matches: list[str] = []

    for phase, keywords in _PHASE_KEYWORDS.items():
        matches = [keyword for keyword in keywords if keyword.lower() in normalized]
        if len(matches) > len(best_matches):
            best_phase = phase
            best_matches = matches

    if not best_matches:
        return _DEFAULT_PHASE, 0.0, []

    confidence = min(0.95, 0.4 + 0.2 * len(best_matches))
    return best_phase, confidence, best_matches


class DetectPhaseTool(Tool):
    """根据用户消息内容检测当前研究阶段。"""

    @property
    def name(self) -> str:
        return "detect_phase"

    @property
    def description(self) -> str:
        return "根据用户消息中的关键词检测当前研究阶段，返回 ResearchPhase 枚举值。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_message": {
                    "type": "string",
                    "description": "待检测的用户消息内容",
                }
            },
            "required": ["user_message"],
        }

    @property
    def category(self) -> str:
        return "utility"

    @property
    def research_domain(self) -> str:
        return "general"

    @property
    def expose_to_llm(self) -> bool:
        return False

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        del session
        user_message = str(kwargs.get("user_message") or "").strip()
        phase, confidence, matched_keywords = detect_phase_from_text(user_message)
        return ToolResult(
            success=True,
            data={
                "current_phase": phase.value,
                "confidence": confidence,
                "matched_keywords": matched_keywords,
            },
            message=f"当前阶段: {phase.value}",
        )
