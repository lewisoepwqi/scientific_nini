"""统计结果解读统一入口。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.interpretation import InterpretStatisticalResultSkill


class StatInterpretSkill(Tool):
    """统一统计解读入口。"""

    def __init__(self) -> None:
        self._delegate = InterpretStatisticalResultSkill()

    @property
    def name(self) -> str:
        return "stat_interpret"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def description(self) -> str:
        return "统一解读统计检验与建模结果，输出可读的结论文本。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_type": {
                    "type": "string",
                    "enum": [
                        "t_test",
                        "anova",
                        "correlation",
                        "regression",
                        "mann_whitney",
                        "kruskal_wallis",
                    ],
                    "description": "待解读的统计结果类型",
                },
                "result": {
                    "type": "object",
                    "description": "统计结果 data 字段",
                },
            },
            "required": ["test_type", "result"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        result = await self._delegate.execute(session, **kwargs)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["resource_type"] = "stat_result"
        payload["data"] = data
        return ToolResult(**payload)
