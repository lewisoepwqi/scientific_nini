"""统计检验统一入口。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics import (
    ANOVASkill,
    KruskalWallisSkill,
    MannWhitneySkill,
    MultipleComparisonCorrectionSkill,
    TTestSkill,
)


class StatTestSkill(Skill):
    """统一差异检验与多重校正入口。"""

    def __init__(self) -> None:
        self._delegates = {
            "independent_t": TTestSkill(),
            "paired_t": TTestSkill(),
            "one_sample_t": TTestSkill(),
            "mann_whitney": MannWhitneySkill(),
            "one_way_anova": ANOVASkill(),
            "kruskal_wallis": KruskalWallisSkill(),
            "multiple_comparison_correction": MultipleComparisonCorrectionSkill(),
        }

    @property
    def name(self) -> str:
        return "stat_test"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def description(self) -> str:
        return "统一执行 t 检验、Mann-Whitney、ANOVA、Kruskal-Wallis 与多重比较校正。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": list(self._delegates.keys()),
                    "description": "统计检验方法",
                },
            },
            "required": ["method"],
            "additionalProperties": True,
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        method = str(kwargs.get("method", "")).strip()
        delegate = self._delegates.get(method)
        if delegate is None:
            return SkillResult(success=False, message=f"不支持的 method: {method}")

        params = {k: v for k, v in kwargs.items() if k != "method"}
        if method == "independent_t":
            params["paired"] = False
        elif method == "paired_t":
            params["paired"] = True

        result = await delegate.execute(session, **params)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["requested_method"] = method
        data["resource_type"] = "stat_result"
        payload["data"] = data
        return SkillResult(**payload)
