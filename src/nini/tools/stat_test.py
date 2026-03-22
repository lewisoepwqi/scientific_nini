"""统计检验统一入口。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.statistics import (
    ANOVATool,
    KruskalWallisTool,
    MannWhitneyTool,
    MultipleComparisonCorrectionTool,
    TTestTool,
)


class StatTestTool(Tool):
    """统一差异检验与多重校正入口。"""

    def __init__(self) -> None:
        self._delegates = {
            "independent_t": TTestTool(),
            "paired_t": TTestTool(),
            "one_sample_t": TTestTool(),
            "mann_whitney": MannWhitneyTool(),
            "one_way_anova": ANOVATool(),
            "kruskal_wallis": KruskalWallisTool(),
            "multiple_comparison_correction": MultipleComparisonCorrectionTool(),
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
                    "enum": [
                        "independent_t",
                        "paired_t",
                        "one_sample_t",
                        "mann_whitney",
                        "one_way_anova",
                        "kruskal_wallis",
                        "multiple_comparison_correction",
                    ],
                    "description": "统计方法",
                },
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称（当会话仅有一个数据集时可省略）",
                },
                "value_column": {"type": "string", "description": "数值列名"},
                "group_column": {"type": "string", "description": "分组列名"},
                "test_value": {"type": "number", "description": "单样本 t 检验的检验值"},
                "alternative": {
                    "type": "string",
                    "enum": ["two-sided", "less", "greater"],
                    "description": "备择假设方向",
                },
                "p_values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "待校正的 p 值列表",
                },
                "alpha": {"type": "number", "description": "显著性水平", "default": 0.05},
                "context": {
                    "type": "string",
                    "enum": ["exploratory", "confirmatory", "high_stakes"],
                    "description": "研究场景",
                },
            },
            "required": ["method"],
            "additionalProperties": True,
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        method = str(kwargs.get("method", "")).strip()
        delegate = self._delegates.get(method)
        if delegate is None:
            return ToolResult(success=False, message=f"不支持的 method: {method}")

        params = {k: v for k, v in kwargs.items() if k != "method"}
        if method != "multiple_comparison_correction":
            dataset_name = self._resolve_dataset_name(session, params)
            if isinstance(dataset_name, ToolResult):
                return dataset_name
            if dataset_name:
                params["dataset_name"] = dataset_name

        if method == "independent_t":
            params["paired"] = False
        elif method == "paired_t":
            params["paired"] = True

        try:
            result = await delegate.execute(session, **params)
        except KeyError as exc:
            missing = str(exc).strip("'\"")
            return ToolResult(success=False, message=f"缺少必要参数: {missing}")

        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["requested_method"] = method
        data["resource_type"] = "stat_result"
        payload["data"] = data
        return ToolResult(**payload)

    def _resolve_dataset_name(
        self,
        session: Session,
        params: dict[str, Any],
    ) -> str | ToolResult | None:
        dataset_name = str(params.get("dataset_name", "")).strip()
        if dataset_name:
            return dataset_name

        for alias in ("dataset", "dataset_id", "input_dataset", "source_dataset"):
            value = params.get(alias)
            if isinstance(value, str) and value.strip():
                return value.strip()

        dataset_names = [
            name for name in session.datasets.keys() if isinstance(name, str) and name.strip()
        ]
        if len(dataset_names) == 1:
            return dataset_names[0]
        if not dataset_names:
            return ToolResult(success=False, message="缺少 dataset_name，且当前会话没有可用数据集")

        preview = ", ".join(dataset_names[:5])
        suffix = "..." if len(dataset_names) > 5 else ""
        return ToolResult(
            success=False,
            message=f"缺少 dataset_name，当前会话存在多个数据集，请明确指定（可选: {preview}{suffix}）",
        )
