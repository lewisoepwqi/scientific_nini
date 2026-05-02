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
        return (
            "统一差异检验与t/Mann-Whitney/ANOVA/Kruskal-Wallis 与多重比较校正。\n"
            "最小示例：{method: independent_t, dataset_name: demo, value_column: value, group_column: group}\n"
            "参数：两组/多组需 value_column+group_column；单样本 t 需 value_column+test_value；多重校正需 p_values。\n"
            "method：independent_t/paired_t/one_sample_t/mann_whitney/one_way_anova/kruskal_wallis/multiple_comparison_correction。"
        )

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
                "correction_method": {
                    "type": "string",
                    "enum": ["bonferroni", "holm", "fdr"],
                    "description": "仅 multiple_comparison_correction 使用的校正方法",
                },
                "alpha": {"type": "number", "description": "显著性水平", "default": 0.05},
                "context": {
                    "type": "string",
                    "enum": ["exploratory", "confirmatory", "high_stakes"],
                    "description": "研究场景",
                },
            },
            "required": ["method"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"method": {"const": "independent_t"}},
                    "required": ["method", "value_column", "group_column"],
                },
                {
                    "type": "object",
                    "properties": {"method": {"const": "paired_t"}},
                    "required": ["method", "value_column", "group_column"],
                },
                {
                    "type": "object",
                    "properties": {"method": {"const": "one_sample_t"}},
                    "required": ["method", "value_column", "test_value"],
                },
                {
                    "type": "object",
                    "properties": {"method": {"const": "mann_whitney"}},
                    "required": ["method", "value_column", "group_column"],
                },
                {
                    "type": "object",
                    "properties": {"method": {"const": "one_way_anova"}},
                    "required": ["method", "value_column", "group_column"],
                },
                {
                    "type": "object",
                    "properties": {"method": {"const": "kruskal_wallis"}},
                    "required": ["method", "value_column", "group_column"],
                },
                {
                    "type": "object",
                    "properties": {"method": {"const": "multiple_comparison_correction"}},
                    "required": ["method", "p_values"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        method = str(kwargs.get("method", "")).strip()
        delegate = self._delegates.get(method)
        if delegate is None:
            return self._input_error(
                method=method,
                error_code="STAT_TEST_METHOD_INVALID",
                message=f"不支持的 method: {method}",
                expected_fields=["method"],
                recovery_hint="请将 method 改为 independent_t、paired_t、one_sample_t、mann_whitney、one_way_anova、kruskal_wallis 或 multiple_comparison_correction。",
                minimal_example='{method: "independent_t", dataset_name: "demo", value_column: "value", group_column: "group"}',
            )

        params = {k: v for k, v in kwargs.items() if k != "method"}
        if method != "multiple_comparison_correction":
            dataset_name = self._resolve_dataset_name(session, params)
            if isinstance(dataset_name, ToolResult):
                return dataset_name
            if dataset_name:
                params["dataset_name"] = dataset_name
        else:
            correction_method = str(params.pop("correction_method", "")).strip()
            if correction_method:
                params["method"] = correction_method

        validation_error = self._validate_method_params(method, params)
        if validation_error is not None:
            return validation_error

        if method == "independent_t":
            params["paired"] = False
        elif method == "paired_t":
            params["paired"] = True

        try:
            result = await delegate.execute(session, **params)
        except KeyError as exc:
            missing = str(exc).strip("'\"")
            return self._input_error(
                method=method,
                error_code="STAT_TEST_REQUIRED_PARAM_MISSING",
                message=f"缺少必要参数: {missing}",
                expected_fields=self._expected_fields_for_method(method),
                recovery_hint="根据当前 method 补齐必填字段后重试。",
                minimal_example=self._minimal_example_for_method(method),
            )

        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["requested_method"] = method
        data["resource_type"] = "stat_result"
        payload["data"] = data
        return ToolResult(**payload)

    def _validate_method_params(
        self,
        method: str,
        params: dict[str, Any],
    ) -> ToolResult | None:
        required = {
            "independent_t": ["value_column", "group_column"],
            "paired_t": ["value_column", "group_column"],
            "one_sample_t": ["value_column", "test_value"],
            "mann_whitney": ["value_column", "group_column"],
            "one_way_anova": ["value_column", "group_column"],
            "kruskal_wallis": ["value_column", "group_column"],
            "multiple_comparison_correction": ["p_values"],
        }.get(method, [])
        missing = [
            field
            for field in required
            if params.get(field) is None
            or (isinstance(params.get(field), str) and not str(params.get(field)).strip())
        ]
        if not missing:
            return None
        first_missing = missing[0]
        return self._input_error(
            method=method,
            error_code="STAT_TEST_REQUIRED_PARAM_MISSING",
            message=f"缺少必要参数: {first_missing}",
            expected_fields=self._expected_fields_for_method(method),
            recovery_hint="根据当前 method 补齐必填字段后重试。",
            minimal_example=self._minimal_example_for_method(method),
        )

    def _expected_fields_for_method(self, method: str) -> list[str]:
        mapping = {
            "independent_t": ["method", "value_column", "group_column"],
            "paired_t": ["method", "value_column", "group_column"],
            "one_sample_t": ["method", "value_column", "test_value"],
            "mann_whitney": ["method", "value_column", "group_column"],
            "one_way_anova": ["method", "value_column", "group_column"],
            "kruskal_wallis": ["method", "value_column", "group_column"],
            "multiple_comparison_correction": ["method", "p_values"],
        }
        return mapping.get(method, ["method"])

    def _minimal_example_for_method(self, method: str) -> str:
        examples = {
            "independent_t": (
                '{method: "independent_t", dataset_name: "demo", '
                'value_column: "value", group_column: "group"}'
            ),
            "paired_t": (
                '{method: "paired_t", dataset_name: "demo", '
                'value_column: "value", group_column: "group"}'
            ),
            "one_sample_t": (
                '{method: "one_sample_t", dataset_name: "demo", '
                'value_column: "value", test_value: 0}'
            ),
            "mann_whitney": (
                '{method: "mann_whitney", dataset_name: "demo", '
                'value_column: "value", group_column: "group"}'
            ),
            "one_way_anova": (
                '{method: "one_way_anova", dataset_name: "demo", '
                'value_column: "value", group_column: "group"}'
            ),
            "kruskal_wallis": (
                '{method: "kruskal_wallis", dataset_name: "demo", '
                'value_column: "value", group_column: "group"}'
            ),
            "multiple_comparison_correction": (
                '{method: "multiple_comparison_correction", '
                'p_values: [0.01, 0.02], correction_method: "holm"}'
            ),
        }
        return examples.get(
            method, '{method: "independent_t", value_column: "value", group_column: "group"}'
        )

    def _input_error(
        self,
        *,
        method: str,
        error_code: str,
        message: str,
        expected_fields: list[str],
        recovery_hint: str,
        minimal_example: str,
    ) -> ToolResult:
        payload = {
            "method": method,
            "error_code": error_code,
            "expected_fields": expected_fields,
            "recovery_hint": recovery_hint,
            "minimal_example": minimal_example,
        }
        return self.build_input_error(message=message, payload=payload)
