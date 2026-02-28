"""意图分析基础模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentCandidate:
    """意图候选项。"""

    name: str
    score: float
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "score": round(self.score, 3),
            "reason": self.reason,
            "payload": self.payload,
        }


@dataclass
class IntentAnalysis:
    """意图分析结果。"""

    query: str
    capability_candidates: list[IntentCandidate] = field(default_factory=list)
    skill_candidates: list[IntentCandidate] = field(default_factory=list)
    explicit_skill_calls: list[dict[str, str]] = field(default_factory=list)
    active_skills: list[dict[str, Any]] = field(default_factory=list)
    tool_hints: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    allowed_tool_sources: list[str] = field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: str | None = None
    clarification_options: list[dict[str, str]] = field(default_factory=list)
    analysis_method: str = "rule_based_v2"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示。"""
        return {
            "query": self.query,
            "capability_candidates": [
                candidate.to_dict() for candidate in self.capability_candidates
            ],
            "skill_candidates": [candidate.to_dict() for candidate in self.skill_candidates],
            "explicit_skill_calls": self.explicit_skill_calls,
            "active_skills": self.active_skills,
            "tool_hints": self.tool_hints,
            "allowed_tools": self.allowed_tools,
            "allowed_tool_sources": self.allowed_tool_sources,
            "clarification_needed": self.clarification_needed,
            "clarification_question": self.clarification_question,
            "clarification_options": self.clarification_options,
            "analysis_method": self.analysis_method,
        }
