"""Reasoning chain tracking for AgentRunner.

Tracks reasoning steps with parent-child relationships and metadata extraction.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


# Keywords for detecting reasoning type
_REASONING_TYPE_KEYWORDS = {
    "analysis": [
        "分析",
        "检查",
        "查看",
        "观察",
        "统计",
        "比较",
        "计算",
        "assess",
        "analyze",
        "examine",
        "inspect",
        "compare",
        "calculate",
    ],
    "decision": [
        "决定",
        "选择",
        "采用",
        "使用",
        "确定",
        "结论",
        "decide",
        "choose",
        "select",
        "determine",
        "conclusion",
        "therefore",
        "thus",
    ],
    "planning": [
        "计划",
        "步骤",
        "首先",
        "然后",
        "下一步",
        "plan",
        "step",
        "first",
        "then",
        "next",
        "approach",
        "strategy",
    ],
    "reflection": [
        "反思",
        "回顾",
        "重新考虑",
        "调整",
        "修正",
        "reflect",
        "reconsider",
        "revise",
        "adjust",
        "however",
        "but",
        "although",
    ],
}

# Keywords for detecting key decisions
_DECISION_KEYWORDS = [
    "决定",
    "选择",
    "采用",
    "使用",
    "确定",
    "结论",
    "应该",
    "decide",
    "choose",
    "select",
    "determine",
    "conclusion",
    "should",
    "will use",
    "opt for",
    "recommend",
]


def detect_reasoning_type(content: str) -> str | None:
    """Detect reasoning type from content based on keywords.

    Args:
        content: The reasoning content to analyze.

    Returns:
        The detected reasoning type (analysis, decision, planning, reflection)
        or None if no type is detected.
    """
    content_lower = content.lower()
    scores: dict[str, int] = {}

    for reasoning_type, keywords in _REASONING_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            scores[reasoning_type] = score

    if not scores:
        return None

    # Return the type with highest score
    return max(scores.items(), key=lambda x: x[1])[0]


def detect_key_decisions(content: str) -> list[str]:
    """Extract key decision sentences from content.

    Args:
        content: The reasoning content to analyze.

    Returns:
        List of up to 3 key decision sentences.
    """
    decisions: list[str] = []
    sentences = re.split(r"[。！.!?\n]", content)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Check if sentence contains decision keywords
        if any(kw in sentence.lower() for kw in _DECISION_KEYWORDS):
            # Only include substantial sentences (not too short)
            if len(sentence) > 10:
                decisions.append(sentence)

    # Limit to top 3 most significant decisions
    return decisions[:3]


def calculate_confidence_score(content: str) -> float | None:
    """Calculate confidence score based on content analysis.

    Args:
        content: The reasoning content to analyze.

    Returns:
        A confidence score between 0.0 and 1.0, or None if no indicators found.
    """
    # Look for confidence indicators
    confidence_indicators = [
        "确定",
        "明确",
        "显然",
        "clearly",
        "definitely",
        "certainly",
        "obviously",
    ]
    uncertainty_indicators = [
        "可能",
        "或许",
        "不确定",
        "也许",
        "probably",
        "maybe",
        "possibly",
        "uncertain",
    ]

    content_lower = content.lower()
    confidence_count = sum(1 for ind in confidence_indicators if ind in content_lower)
    uncertainty_count = sum(1 for ind in uncertainty_indicators if ind in content_lower)

    if confidence_count == 0 and uncertainty_count == 0:
        return None

    # Base score 0.5, adjust based on indicators
    score = 0.5 + (confidence_count * 0.1) - (uncertainty_count * 0.15)
    return max(0.0, min(1.0, score))  # Clamp to [0, 1]


class ReasoningChainTracker:
    """Track reasoning chain with parent-child relationships.

    Maintains a chain of reasoning nodes where each new node becomes
    the parent for subsequent nodes, creating a linked history.
    """

    def __init__(self) -> None:
        """Initialize an empty reasoning chain."""
        self._chain: list[dict[str, Any]] = []
        self._current_parent_id: str | None = None

    def add_reasoning(
        self,
        content: str,
        reasoning_type: str | None = None,
        key_decisions: list[str] | None = None,
        confidence_score: float | None = None,
    ) -> dict[str, Any]:
        """Add a reasoning node to the chain.

        Args:
            content: The reasoning text content.
            reasoning_type: Type of reasoning (analysis, decision, planning, reflection).
            key_decisions: List of key decision sentences.
            confidence_score: Confidence score between 0.0 and 1.0.

        Returns:
            The created reasoning node with metadata.
        """
        reasoning_id = f"reasoning_{len(self._chain)}"
        node: dict[str, Any] = {
            "id": reasoning_id,
            "content": content,
            "reasoning_type": reasoning_type,
            "key_decisions": key_decisions or [],
            "confidence_score": confidence_score,
            "parent_id": self._current_parent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._chain.append(node)
        # Update current parent for next reasoning
        self._current_parent_id = reasoning_id
        return node

    def get_chain(self) -> list[dict[str, Any]]:
        """Get the full reasoning chain.

        Returns:
            A copy of the reasoning chain list.
        """
        return self._chain.copy()

    def reset(self) -> None:
        """Reset the chain, clearing all nodes."""
        self._chain.clear()
        self._current_parent_id = None
