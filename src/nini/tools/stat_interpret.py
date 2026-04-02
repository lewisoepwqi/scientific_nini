"""统计结果解读统一入口。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.interpretation import InterpretStatisticalResultTool


class StatInterpretTool(Tool):
    """统一统计解读入口。"""

    def __init__(self) -> None:
        self._delegate = InterpretStatisticalResultTool()

    @property
    def name(self) -> str:
        return "stat_interpret"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def description(self) -> str:
        return (
            "统一解读统计检验与建模结果，输出可读的中文结论文本。\n"
            "最小示例：\n"
            '- 解读 t 检验：{test_type: "t_test", result: {statistic: 2.45, p_value: 0.018, '
            "effect_size: 0.65, group1_mean: 120.3, group2_mean: 115.8}}\n"
            '- 解读回归：{test_type: "regression", result: {r_squared: 0.85, '
            "coefficients: [{name: x1, value: 0.3, p_value: 0.001}]}}\n"
            "参数约束：test_type（枚举：t_test/anova/correlation/regression/mann_whitney/"
            "kruskal_wallis）和 result 均为必填。"
        )

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
