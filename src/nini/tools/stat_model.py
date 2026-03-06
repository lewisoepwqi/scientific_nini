"""统计建模统一入口。"""

from __future__ import annotations

import json
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
        return (
            "统一执行相关分析和线性/多元回归分析。"
            "最小示例："
            '1) 相关性: {"method":"correlation","dataset_name":"demo","columns":["x","y"]}；'
            '2) 回归: {"method":"linear_regression","dataset_name":"demo",'
            '"dependent_var":"y","independent_vars":["x1","x2"]}。'
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["correlation"],
                            "description": "建模方法：相关性分析",
                        },
                        "dataset_name": {
                            "type": "string",
                            "description": "数据集名称。多数据集会话必须显式指定",
                        },
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "description": "需要计算相关性的数值列名（至少两列）",
                        },
                        "correlation_method": {
                            "type": "string",
                            "enum": ["pearson", "spearman", "kendall"],
                            "description": "相关性方法别名（会映射为 method）",
                        },
                        "method_detail": {
                            "type": "string",
                            "enum": ["pearson", "spearman", "kendall"],
                            "description": "相关性方法（兼容别名）",
                        },
                    },
                    "required": ["method", "dataset_name", "columns"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["linear_regression", "multiple_regression"],
                            "description": "建模方法：线性/多元回归",
                        },
                        "dataset_name": {
                            "type": "string",
                            "description": "数据集名称。多数据集会话必须显式指定",
                        },
                        "dependent_var": {
                            "type": "string",
                            "description": "因变量（Y）列名",
                        },
                        "independent_vars": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": "自变量（X）列名列表",
                        },
                    },
                    "required": [
                        "method",
                        "dataset_name",
                        "dependent_var",
                        "independent_vars",
                    ],
                    "additionalProperties": False,
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        method = str(kwargs.get("method", "")).strip()
        delegate = self._delegates.get(method)
        if delegate is None:
            return SkillResult(success=False, message=f"不支持的 method: {method}")

        params = {k: v for k, v in kwargs.items() if k != "method"}
        self._normalize_sequence_params(params)
        validation_error = self._validate_sequence_params(params)
        if validation_error is not None:
            return validation_error

        dataset_name = self._resolve_dataset_name(session, params)
        if isinstance(dataset_name, SkillResult):
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
            return SkillResult(success=False, message=f"缺少必要参数: {missing}")

        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["requested_method"] = method
        data["resource_type"] = "stat_result"
        payload["data"] = data
        return SkillResult(**payload)

    def _resolve_dataset_name(
        self,
        session: Session,
        params: dict[str, Any],
    ) -> str | SkillResult | None:
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
            return SkillResult(success=False, message="缺少 dataset_name，且当前会话没有可用数据集")

        preview = ", ".join(dataset_names[:5])
        suffix = "..." if len(dataset_names) > 5 else ""
        return SkillResult(
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

    def _validate_sequence_params(self, params: dict[str, Any]) -> SkillResult | None:
        """对列表参数做前置校验，避免下游返回误导性错误。"""
        for key in ("columns", "independent_vars"):
            if key not in params:
                continue
            value = params[key]
            if not isinstance(value, list):
                value_type = type(value).__name__
                return SkillResult(
                    success=False,
                    message=f"参数 {key} 必须是数组（list），当前是 {value_type}",
                )
        return None
