"""统计建模统一入口。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics import CorrelationSkill, RegressionSkill


class StatModelSkill(Skill):
    """统一相关分析与回归分析入口。"""

    def __init__(self) -> None:
        self._delegates = {
            "correlation": CorrelationSkill(),
            "linear_regression": RegressionSkill(),
            "multiple_regression": RegressionSkill(),
        }

    @property
    def name(self) -> str:
        return "stat_model"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def description(self) -> str:
        return "统一执行相关分析和线性/多元回归分析。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": list(self._delegates.keys()),
                    "description": "建模方法",
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
        if method == "correlation" and "correlation_method" in params:
            params["method"] = params.pop("correlation_method")
        result = await delegate.execute(session, **params)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["requested_method"] = method
        data["resource_type"] = "stat_result"
        payload["data"] = data
        return SkillResult(**payload)
