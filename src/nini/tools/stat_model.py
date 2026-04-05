"""统计建模统一入口。"""

from __future__ import annotations

import json
from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.statistics import CorrelationTool, RegressionTool


class StatModelTool(Tool):
    """统一相关分析与回归分析入口。"""

    def __init__(self) -> None:
        self._delegates = {
            "correlation": CorrelationTool(),
            "linear_regression": RegressionTool(),
            "multiple_regression": RegressionTool(),
        }

    @property
    def name(self) -> str:
        return "stat_model"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def description(self) -> str:
        return (
            "统一执行相关分析、线性回归和多元回归。必须传入 method 字段。\n"
            "最小示例：{method: correlation, dataset_name: demo, columns: [x, y]}\n"
            "method 枚举：correlation/linear_regression/multiple_regression。"
            "回归需 dependent_var+independent_vars。不确定列名时先用 dataset_catalog 查看。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["correlation", "linear_regression", "multiple_regression"],
                    "description": (
                        "【必填】分析方法。"
                        "correlation=相关性分析（需 columns）；"
                        "linear_regression/multiple_regression=回归分析（需 dependent_var + independent_vars）"
                    ),
                },
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称。多数据集会话必须显式指定，单数据集可省略",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '【correlation 必填】参与相关性计算的数值列名，至少 2 列，例如 ["收缩压/Hgmm", "舒张压/Hgmm", "心率次/分"]',
                },
                "correlation_method": {
                    "type": "string",
                    "enum": ["pearson", "spearman", "kendall"],
                    "description": "相关性系数类型，默认 pearson；数据非正态时推荐 spearman",
                },
                "dependent_var": {
                    "type": "string",
                    "description": "【回归必填】因变量（Y）列名",
                },
                "independent_vars": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '【回归必填】自变量（X）列名列表，例如 ["年龄", "体重"]',
                },
            },
            "required": ["method"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        method = str(kwargs.get("method", "")).strip()
        delegate = self._delegates.get(method)
        if delegate is None:
            supported = list(self._delegates.keys())
            if not method:
                return self._input_error(
                    method=method,
                    error_code="STAT_MODEL_METHOD_REQUIRED",
                    message=(
                        "缺少必要参数 method，请指定分析类型。"
                        f"支持的值：{supported}。"
                        '示例（相关性）：{{"method":"correlation","dataset_name":"<数据集名>","columns":["列A","列B"]}}。'
                        '示例（回归）：{{"method":"linear_regression","dataset_name":"<数据集名>",'
                        '"dependent_var":"Y列","independent_vars":["X1","X2"]}}'
                    ),
                    expected_fields=["method"],
                    recovery_hint="请先指定 method，再补齐该方法对应的列参数。",
                    minimal_example='{method: "correlation", dataset_name: "demo", columns: ["x", "y"]}',
                )
            return self._input_error(
                method=method,
                error_code="STAT_MODEL_METHOD_INVALID",
                message=f"不支持的 method: '{method}'，支持的值：{supported}",
                expected_fields=["method"],
                recovery_hint="请将 method 改为 correlation、linear_regression 或 multiple_regression。",
                minimal_example='{method: "correlation", dataset_name: "demo", columns: ["x", "y"]}',
            )

        params = {k: v for k, v in kwargs.items() if k != "method"}
        self._normalize_sequence_params(params)
        validation_error = self._validate_sequence_params(params)
        if validation_error is not None:
            return validation_error
        validation_error = self._validate_method_params(method, params)
        if validation_error is not None:
            return validation_error

        dataset_name = self._resolve_dataset_name(session, params)
        if isinstance(dataset_name, ToolResult):
            return dataset_name
        if dataset_name:
            params["dataset_name"] = dataset_name

        if method == "correlation":
            if "correlation_method" in params:
                params["method"] = params.pop("correlation_method")
            elif "method_detail" in params:
                params["method"] = params.pop("method_detail")
        try:
            result = await delegate.execute(session, **params)
        except KeyError as exc:
            missing = str(exc).strip("'\"")
            return self._input_error(
                method=method,
                error_code="STAT_MODEL_REQUIRED_PARAM_MISSING",
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

    def _normalize_sequence_params(self, params: dict[str, Any]) -> None:
        """归一化列表参数，兼容模型输出的字符串化 JSON 数组。"""
        for key in ("columns", "independent_vars"):
            value = params.get(key)
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    params[key] = parsed

    def _validate_sequence_params(self, params: dict[str, Any]) -> ToolResult | None:
        """对列表参数做前置校验，避免下游返回误导性错误。"""
        for key in ("columns", "independent_vars"):
            if key not in params:
                continue
            value = params[key]
            if not isinstance(value, list):
                value_type = type(value).__name__
                return ToolResult(
                    success=False,
                    message=f"参数 {key} 必须是数组（list），当前是 {value_type}",
                )
        return None

    def _validate_method_params(
        self,
        method: str,
        params: dict[str, Any],
    ) -> ToolResult | None:
        required = {
            "correlation": ["columns"],
            "linear_regression": ["dependent_var", "independent_vars"],
            "multiple_regression": ["dependent_var", "independent_vars"],
        }.get(method, [])
        missing = [
            field
            for field in required
            if params.get(field) is None
            or (isinstance(params.get(field), str) and not str(params.get(field)).strip())
        ]
        if not missing:
            return None
        return self._input_error(
            method=method,
            error_code="STAT_MODEL_REQUIRED_PARAM_MISSING",
            message=f"缺少必要参数: {missing[0]}",
            expected_fields=self._expected_fields_for_method(method),
            recovery_hint="根据当前 method 补齐必填字段后重试。",
            minimal_example=self._minimal_example_for_method(method),
        )

    def _expected_fields_for_method(self, method: str) -> list[str]:
        mapping = {
            "correlation": ["method", "columns"],
            "linear_regression": ["method", "dependent_var", "independent_vars"],
            "multiple_regression": ["method", "dependent_var", "independent_vars"],
        }
        return mapping.get(method, ["method"])

    def _minimal_example_for_method(self, method: str) -> str:
        examples = {
            "correlation": '{method: "correlation", dataset_name: "demo", columns: ["x", "y"]}',
            "linear_regression": (
                '{method: "linear_regression", dataset_name: "demo", '
                'dependent_var: "y", independent_vars: ["x1", "x2"]}'
            ),
            "multiple_regression": (
                '{method: "multiple_regression", dataset_name: "demo", '
                'dependent_var: "y", independent_vars: ["x1", "x2", "x3"]}'
            ),
        }
        return examples.get(
            method, '{method: "correlation", dataset_name: "demo", columns: ["x", "y"]}'
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
