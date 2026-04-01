"""结构化数据变换基础工具。"""

from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from nini.agent.session import Session
from nini.models import ResourceType
from nini.tools.base import Tool, ToolResult
from nini.tools.clean_data import CleanDataTool, RecommendCleaningStrategyTool
from nini.utils.dataframe_io import dataframe_to_json_safe
from nini.workspace import WorkspaceManager


class DatasetTransformValidationError(ValueError):
    """数据变换输入校验失败。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        expected_params: list[str] | None = None,
        recovery_hint: str | None = None,
        minimal_example: str | None = None,
        step_id: str | None = None,
        op: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.expected_params = expected_params or []
        self.recovery_hint = recovery_hint or ""
        self.minimal_example = minimal_example or ""
        self.step_id = step_id
        self.op = op

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error_code": self.error_code}
        if self.expected_params:
            payload["expected_params"] = self.expected_params
        if self.recovery_hint:
            payload["recovery_hint"] = self.recovery_hint
        if self.minimal_example:
            payload["minimal_example"] = self.minimal_example
        if self.step_id:
            payload["invalid_step_id"] = self.step_id
        if self.op:
            payload["op"] = self.op
        return payload


class DatasetTransformTool(Tool):
    """执行结构化数据变换流水线。"""

    _supported_ops = {
        "concat_datasets",
        "concat_all",
        "derive_column",
        "filter_rows",
        "group_aggregate",
        "sort_rows",
        "deduplicate",
        "rename_columns",
        "select_columns",
        "clean_data",
        "recommend_cleaning_strategy",
    }

    def __init__(self) -> None:
        self._clean = CleanDataTool()
        self._recommend = RecommendCleaningStrategyTool()

    @property
    def name(self) -> str:
        return "dataset_transform"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return (
            "执行结构化数据变换流水线。支持拼接、衍生列、过滤、聚合、排序、去重、列重命名、"
            "列选择以及结构化清洗，并支持步骤级 patch 与重跑。"
            "steps[].op 仅支持：concat_datasets、concat_all、derive_column、filter_rows、"
            "group_aggregate、sort_rows、deduplicate、rename_columns、select_columns、"
            "clean_data、recommend_cleaning_strategy。"
            "其中 derive_column/filter_rows 使用 pandas eval/query 风格表达式，不是自由 Python："
            "请直接引用列名，例如 expr='测量时刻.dt.hour'；"
            "不支持 df[...]、lambda、三元 if ... else ...。"
            '最小示例：{"operation":"run","dataset_name":"demo","steps":[{"id":"derive_hour","op":"derive_column","params":{"column":"小时","expr":"测量时刻.dt.hour"}}]}。'
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["run", "patch_step", "get_plan"],
                    "description": "变换操作类型",
                },
                "transform_id": {"type": "string", "description": "已有变换计划 ID"},
                "dataset_name": {"type": "string", "description": "默认输入数据集名称"},
                "input_datasets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "多输入数据集名称列表",
                },
                "steps": {
                    "type": "array",
                    "items": self._build_step_item_schema(),
                    "description": "变换步骤列表",
                },
                "step_patch": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "op": {
                            "type": "string",
                            "enum": sorted(self._supported_ops),
                            "description": "目标步骤的替换操作（固定枚举）",
                        },
                        "params": {"type": "object"},
                    },
                    "required": ["step_id"],
                    "description": "patch_step 时对目标步骤的修改",
                },
                "output_dataset_name": {
                    "type": "string",
                    "description": "输出数据集名称",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "properties": {"operation": {"const": "run"}},
                    "required": ["operation", "steps"],
                },
                {
                    "properties": {"operation": {"const": "patch_step"}},
                    "required": ["operation", "transform_id", "step_patch"],
                },
                {
                    "properties": {"operation": {"const": "get_plan"}},
                    "required": ["operation", "transform_id"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()
        if operation == "run":
            return await self._run_transform(session, **kwargs)
        if operation == "patch_step":
            return await self._patch_step(session, **kwargs)
        if operation == "get_plan":
            return self._get_plan(session, **kwargs)
        return self._input_error(
            message=f"不支持的 operation: {operation}",
            payload={
                "error_code": "DATASET_TRANSFORM_OPERATION_INVALID",
                "operation": operation,
                "expected_fields": ["operation"],
                "expected_operations": ["run", "patch_step", "get_plan"],
                "recovery_hint": "请将 operation 改为 run、patch_step 或 get_plan。",
                "minimal_example": '{"operation":"run","dataset_name":"demo","steps":[{"id":"dedup","op":"deduplicate","params":{}}]}',
            },
        )

    async def _run_transform(self, session: Session, **kwargs: Any) -> ToolResult:
        transform_id = (
            str(kwargs.get("transform_id", "")).strip() or f"transform_{uuid.uuid4().hex[:12]}"
        )
        steps = kwargs.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return self._validation_result(
                DatasetTransformValidationError(
                    "run 操作必须提供 steps",
                    error_code="DATASET_TRANSFORM_STEPS_REQUIRED",
                    expected_params=["steps"],
                    recovery_hint="请提供非空 steps 列表，每个步骤至少包含 id 和 op。",
                    minimal_example='{"operation":"run","dataset_name":"demo","steps":[{"id":"dedup","op":"deduplicate","params":{}}]}',
                )
            )

        dataset_name = str(kwargs.get("dataset_name", "")).strip()
        input_datasets = [
            str(item).strip() for item in kwargs.get("input_datasets") or [] if str(item).strip()
        ]
        if dataset_name and not input_datasets:
            input_datasets = [dataset_name]

        df = await self._resolve_initial_dataframe(session, input_datasets)
        if df is None:
            return ToolResult(
                success=False, message="无法解析输入数据集，请提供 dataset_name 或 input_datasets"
            )

        try:
            execution_steps: list[dict[str, Any]] = []
            current_df = df
            for index, raw_step in enumerate(steps, start=1):
                step = dict(raw_step) if isinstance(raw_step, dict) else {}
                step_id = str(step.get("id", "")).strip() or f"s{index}"
                op = str(step.get("op", "")).strip()
                params_raw = step.get("params")
                params: dict[str, Any] = dict(params_raw) if isinstance(params_raw, dict) else {}
                if op not in self._supported_ops:
                    return ToolResult(
                        success=False, message=f"步骤 {step_id} 使用了不支持的操作: {op}"
                    )
                current_df, step_result = await self._apply_step(
                    session=session,
                    transform_id=transform_id,
                    df=current_df,
                    step_id=step_id,
                    op=op,
                    params=params,
                )
                execution_steps.append(
                    {
                        "id": step_id,
                        "op": op,
                        "params": params,
                        "result": step_result,
                    }
                )
        except DatasetTransformValidationError as exc:
            return self._validation_result(exc)
        except Exception as exc:
            return ToolResult(success=False, message=f"数据变换失败: {exc}")

        output_name = str(kwargs.get("output_dataset_name", "")).strip() or f"{transform_id}_output"
        dataset_record = self._persist_output_dataset(session, output_name, current_df)
        plan_record = self._persist_transform_plan(
            session=session,
            transform_id=transform_id,
            dataset_name=dataset_name,
            input_datasets=input_datasets,
            steps=execution_steps,
            output_dataset_name=output_name,
        )

        preview_rows = min(20, len(current_df))
        preview = {
            "data": dataframe_to_json_safe(current_df, n_rows=preview_rows),
            "columns": [
                {"name": col, "dtype": str(current_df[col].dtype)} for col in current_df.columns
            ],
            "total_rows": len(current_df),
            "preview_rows": preview_rows,
        }
        return ToolResult(
            success=True,
            message=f"数据变换完成，已生成数据集 '{output_name}'",
            data={
                "transform_id": transform_id,
                "resource_id": dataset_record["id"],
                "resource_type": "dataset",
                "plan_resource_id": plan_record["id"],
                "output_dataset_name": output_name,
                "output_resources": [
                    {
                        "resource_id": str(dataset_record["id"]),
                        "resource_type": "dataset",
                        "name": output_name,
                    },
                    {
                        "resource_id": str(plan_record["id"]),
                        "resource_type": str(plan_record.get("resource_type", "stat_result")),
                        "name": str(plan_record.get("name", "")) or transform_id,
                    },
                ],
                "steps": execution_steps,
            },
            has_dataframe=True,
            dataframe_preview=preview,
        )

    async def _patch_step(self, session: Session, **kwargs: Any) -> ToolResult:
        transform_id = str(kwargs.get("transform_id", "")).strip()
        if not transform_id:
            return self._input_error(
                message="patch_step 操作必须提供 transform_id",
                payload={
                    "error_code": "DATASET_TRANSFORM_PATCH_TRANSFORM_ID_REQUIRED",
                    "operation": "patch_step",
                    "expected_fields": ["operation", "transform_id", "step_patch"],
                    "recovery_hint": "请先提供已有变换计划的 transform_id，再传入 step_patch。",
                    "minimal_example": '{"operation":"patch_step","transform_id":"transform_demo","step_patch":{"step_id":"dedup","params":{}}}',
                },
            )

        patch = kwargs.get("step_patch")
        if not isinstance(patch, dict):
            return self._input_error(
                message="patch_step 操作必须提供 step_patch",
                payload={
                    "error_code": "DATASET_TRANSFORM_PATCH_STEP_PATCH_REQUIRED",
                    "operation": "patch_step",
                    "expected_fields": ["operation", "transform_id", "step_patch"],
                    "recovery_hint": "step_patch 至少需要包含 step_id，可选 op 与 params。",
                    "minimal_example": '{"operation":"patch_step","transform_id":"transform_demo","step_patch":{"step_id":"dedup","params":{}}}',
                },
            )

        plan = self._load_transform_plan(session, transform_id)
        if plan is None:
            return self._input_error(
                message=f"未找到变换计划: {transform_id}",
                payload={
                    "error_code": "DATASET_TRANSFORM_PLAN_NOT_FOUND",
                    "transform_id": transform_id,
                    "recovery_hint": "请先运行 operation='run' 生成 transform_id，或检查 transform_id 是否正确。",
                    "minimal_example": '{"operation":"get_plan","transform_id":"transform_demo"}',
                },
            )

        step_id = str(patch.get("step_id", "")).strip()
        if not step_id:
            return self._input_error(
                message="step_patch.step_id 不能为空",
                payload={
                    "error_code": "DATASET_TRANSFORM_PATCH_STEP_ID_REQUIRED",
                    "operation": "patch_step",
                    "expected_fields": ["step_patch.step_id"],
                    "recovery_hint": "请明确指定要 patch 的步骤 ID。",
                    "minimal_example": '{"operation":"patch_step","transform_id":"transform_demo","step_patch":{"step_id":"dedup","params":{}}}',
                },
            )

        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            return self._input_error(
                message="变换计划 steps 格式无效",
                payload={
                    "error_code": "DATASET_TRANSFORM_PLAN_STEPS_INVALID",
                    "transform_id": transform_id,
                    "recovery_hint": "该计划记录已损坏，请重新运行变换生成新计划。",
                    "minimal_example": '{"operation":"run","dataset_name":"demo","steps":[{"id":"dedup","op":"deduplicate","params":{}}]}',
                },
            )

        matched = False
        for step in steps:
            if not isinstance(step, dict) or str(step.get("id", "")).strip() != step_id:
                continue
            if "op" in patch and patch.get("op"):
                step["op"] = patch["op"]
            if isinstance(patch.get("params"), dict):
                step["params"] = patch["params"]
            step.pop("result", None)
            matched = True
            break

        if not matched:
            return self._input_error(
                message=f"未找到步骤: {step_id}",
                payload={
                    "error_code": "DATASET_TRANSFORM_STEP_NOT_FOUND",
                    "transform_id": transform_id,
                    "invalid_step_id": step_id,
                    "recovery_hint": "请先用 get_plan 查看现有步骤 ID，再选择正确的 step_id。",
                    "minimal_example": '{"operation":"get_plan","transform_id":"transform_demo"}',
                },
            )

        return await self._run_transform(
            session,
            transform_id=transform_id,
            dataset_name=plan.get("dataset_name"),
            input_datasets=plan.get("input_datasets") or [],
            steps=steps,
            output_dataset_name=plan.get("output_dataset_name"),
        )

    def _get_plan(self, session: Session, **kwargs: Any) -> ToolResult:
        transform_id = str(kwargs.get("transform_id", "")).strip()
        if not transform_id:
            return self._input_error(
                message="get_plan 操作必须提供 transform_id",
                payload={
                    "error_code": "DATASET_TRANSFORM_GET_PLAN_TRANSFORM_ID_REQUIRED",
                    "operation": "get_plan",
                    "expected_fields": ["operation", "transform_id"],
                    "recovery_hint": "请提供要读取的 transform_id。",
                    "minimal_example": '{"operation":"get_plan","transform_id":"transform_demo"}',
                },
            )
        plan = self._load_transform_plan(session, transform_id)
        if plan is None:
            return self._input_error(
                message=f"未找到变换计划: {transform_id}",
                payload={
                    "error_code": "DATASET_TRANSFORM_PLAN_NOT_FOUND",
                    "transform_id": transform_id,
                    "recovery_hint": "请先运行 operation='run' 生成 transform_id，或检查 transform_id 是否正确。",
                    "minimal_example": '{"operation":"run","dataset_name":"demo","steps":[{"id":"dedup","op":"deduplicate","params":{}}]}',
                },
            )
        manager = WorkspaceManager(session.id)
        resource = manager.get_resource_summary(transform_id)
        return ToolResult(
            success=True,
            message=f"已读取变换计划 '{transform_id}'",
            data={
                "transform_id": transform_id,
                "resource_id": transform_id,
                "resource": resource,
                "plan": plan,
            },
        )

    async def _resolve_initial_dataframe(
        self,
        session: Session,
        input_datasets: list[str],
    ) -> pd.DataFrame | None:
        if not input_datasets:
            return None
        if len(input_datasets) == 1:
            single = session.datasets.get(input_datasets[0])
            return single.copy(deep=True) if single is not None else None
        frames = []
        for name in input_datasets:
            df = session.datasets.get(name)
            if df is None:
                return None
            frames.append(df.copy(deep=True))
        return pd.concat(frames, ignore_index=True, sort=False)

    async def _apply_step(
        self,
        *,
        session: Session,
        transform_id: str,
        df: pd.DataFrame,
        step_id: str,
        op: str,
        params: dict[str, Any],
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        current = df.copy(deep=True)

        if op == "concat_datasets":
            dataset_names = [
                str(item).strip() for item in params.get("datasets", []) if str(item).strip()
            ]
            frames = []
            for name in dataset_names:
                frame = session.datasets.get(name)
                if frame is None:
                    raise ValueError(f"数据集 '{name}' 不存在")
                frames.append(frame.copy(deep=True))
            current = pd.concat(frames, ignore_index=True, sort=False)
            return current, {"rows": len(current), "columns": len(current.columns)}

        if op == "concat_all":
            dataset_names = [
                str(item).strip() for item in params.get("datasets", []) if str(item).strip()
            ]
            if not dataset_names:
                # 兼容旧调用：当 run 阶段已完成预拼接时，concat_all 视作占位步骤。
                return current, {
                    "rows": len(current),
                    "columns": len(current.columns),
                    "mode": "pass_through",
                }
            frames = []
            for name in dataset_names:
                frame = session.datasets.get(name)
                if frame is None:
                    raise ValueError(f"数据集 '{name}' 不存在")
                frames.append(frame.copy(deep=True))
            current = pd.concat(frames, ignore_index=True, sort=False)
            return current, {"rows": len(current), "columns": len(current.columns)}

        if op == "derive_column":
            column = str(params.get("column", "")).strip()
            expr = str(params.get("expr", "")).strip()
            if not column or not expr:
                raise DatasetTransformValidationError(
                    "derive_column 需要提供 column 和 expr",
                    error_code="DATASET_TRANSFORM_DERIVE_COLUMN_PARAMS_REQUIRED",
                    expected_params=["column", "expr"],
                    recovery_hint=(
                        "请在 params 中同时提供目标列名 column 和表达式 expr。"
                        "如需提取小时，可直接写 expr='测量时刻.dt.hour'。"
                    ),
                    minimal_example='{"id":"derive_hour","op":"derive_column","params":{"column":"小时","expr":"测量时刻.dt.hour"}}',
                    step_id=step_id,
                    op=op,
                )
            self._validate_expression(expr, step_id=step_id, op=op)
            current[column] = current.eval(expr, engine="python")
            return current, {"column": column}

        if op == "filter_rows":
            query = str(params.get("query", "")).strip()
            if not query:
                raise DatasetTransformValidationError(
                    "filter_rows 需要提供 query",
                    error_code="DATASET_TRANSFORM_FILTER_QUERY_REQUIRED",
                    expected_params=["query"],
                    recovery_hint="请提供 query 表达式，例如 '(收缩压 > 140) & (心率 < 100)'。",
                    minimal_example='{"id":"filter_high_bp","op":"filter_rows","params":{"query":"(收缩压 > 140) & (心率 < 100)"}}',
                    step_id=step_id,
                    op=op,
                )
            self._validate_expression(query, step_id=step_id, op=op)
            current = current.query(query, engine="python").reset_index(drop=True)
            return current, {"rows": len(current)}

        if op == "group_aggregate":
            by = params.get("by")
            metrics = params.get("metrics")
            if not by or not metrics:
                raise ValueError("group_aggregate 需要提供 by 和 metrics")
            current = current.groupby(by, dropna=False).agg(metrics).reset_index()
            return current, {"rows": len(current), "columns": len(current.columns)}

        if op == "sort_rows":
            by = params.get("by")
            if not by:
                raise ValueError("sort_rows 需要提供 by")
            current = current.sort_values(
                by=by, ascending=params.get("ascending", True)
            ).reset_index(drop=True)
            return current, {"rows": len(current)}

        if op == "deduplicate":
            current = current.drop_duplicates(
                subset=params.get("subset"),
                keep=params.get("keep", "first"),
            ).reset_index(drop=True)
            return current, {"rows": len(current)}

        if op == "rename_columns":
            mapping = params.get("mapping")
            if not isinstance(mapping, dict) or not mapping:
                raise DatasetTransformValidationError(
                    "rename_columns 需要提供 mapping",
                    error_code="DATASET_TRANSFORM_RENAME_MAPPING_REQUIRED",
                    expected_params=["mapping"],
                    recovery_hint=(
                        "请在 params.mapping 中提供旧列名到新列名的映射。"
                        "不要把列名映射直接平铺在 params 顶层。"
                    ),
                    minimal_example='{"id":"rename_cols","op":"rename_columns","params":{"mapping":{"收缩压/Hgmm":"收缩压","舒张压/Hgmm":"舒张压"}}}',
                    step_id=step_id,
                    op=op,
                )
            current = current.rename(columns=mapping)
            return current, {"columns": list(current.columns)}

        if op == "select_columns":
            columns = params.get("columns")
            if not isinstance(columns, list) or not columns:
                raise ValueError("select_columns 需要提供 columns")
            current = current[columns].copy()
            return current, {"columns": list(current.columns)}

        if op == "clean_data":
            input_name = f"__{transform_id}_clean_input"
            output_name = f"__{transform_id}_clean_output"
            session.datasets[input_name] = current
            try:
                result = await self._clean.execute(
                    session,
                    dataset_name=input_name,
                    missing_strategy=params.get("missing_strategy", "auto"),
                    outlier_method=params.get("outlier_method", "auto"),
                    outlier_threshold=params.get("outlier_threshold", 3.0),
                    normalize_numeric=params.get("normalize_numeric", False),
                    normalize_columns=params.get("normalize_columns") or [],
                    inplace=False,
                    output_dataset_name=output_name,
                )
                if not result.success:
                    raise ValueError(result.message)
                cleaned = session.datasets[output_name].copy(deep=True)
                return cleaned, result.data if isinstance(result.data, dict) else {}
            finally:
                session.datasets.pop(input_name, None)
                session.datasets.pop(output_name, None)

        if op == "recommend_cleaning_strategy":
            input_name = f"__{transform_id}_recommend_input"
            session.datasets[input_name] = current
            try:
                result = await self._recommend.execute(
                    session,
                    dataset_name=input_name,
                    target_columns=params.get("target_columns") or [],
                )
                if not result.success:
                    raise ValueError(result.message)
                return current, result.data if isinstance(result.data, dict) else {}
            finally:
                session.datasets.pop(input_name, None)

        raise ValueError(f"不支持的步骤操作: {op}")

    def _persist_output_dataset(
        self,
        session: Session,
        output_name: str,
        df: pd.DataFrame,
    ) -> dict[str, Any]:
        session.datasets[output_name] = df
        manager = WorkspaceManager(session.id)
        dataset_id = uuid.uuid4().hex[:12]
        path = manager.build_managed_resource_path(
            ResourceType.DATASET,
            f"{output_name}.csv",
            default_name=f"{dataset_id}.csv",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return manager.add_dataset_record(
            dataset_id=dataset_id,
            name=output_name,
            file_path=path,
            file_type="csv",
            file_size=path.stat().st_size,
            row_count=len(df),
            column_count=len(df.columns),
        )

    def _persist_transform_plan(
        self,
        *,
        session: Session,
        transform_id: str,
        dataset_name: str,
        input_datasets: list[str],
        steps: list[dict[str, Any]],
        output_dataset_name: str,
    ) -> dict[str, Any]:
        manager = WorkspaceManager(session.id)
        path = manager.build_managed_resource_path(
            ResourceType.STAT_RESULT,
            f"{transform_id}.json",
            default_name=f"{transform_id}.json",
        )
        plan = {
            "transform_id": transform_id,
            "dataset_name": dataset_name,
            "input_datasets": input_datasets,
            "steps": steps,
            "output_dataset_name": output_dataset_name,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return manager.upsert_managed_resource(
            resource_id=transform_id,
            resource_type=ResourceType.STAT_RESULT,
            name=path.name,
            path=path,
            source_kind="transforms",
            metadata={"output_dataset_name": output_dataset_name},
        )

    def _load_transform_plan(self, session: Session, transform_id: str) -> dict[str, Any] | None:
        manager = WorkspaceManager(session.id)
        path = manager.build_managed_resource_path(
            ResourceType.STAT_RESULT,
            f"{transform_id}.json",
            default_name=f"{transform_id}.json",
        )
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _build_step_item_schema(cls) -> dict[str, Any]:
        base_item = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "op": {
                    "type": "string",
                    "enum": sorted(cls._supported_ops),
                    "description": "变换步骤操作类型（固定枚举）",
                },
                "params": {
                    "type": "object",
                    "description": "步骤参数。不同 op 需要不同字段，请参考 oneOf 分支和最小示例。",
                },
            },
            "required": ["id", "op"],
            "additionalProperties": False,
        }
        variants = [
            cls._build_step_variant(
                "concat_datasets",
                {
                    "datasets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "待拼接的数据集名称列表",
                    }
                },
                required=["datasets"],
            ),
            cls._build_step_variant(
                "concat_all",
                {
                    "datasets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选。显式指定需要拼接的数据集列表；留空时可作为占位步骤。",
                    }
                },
            ),
            cls._build_step_variant(
                "derive_column",
                {
                    "column": {"type": "string", "description": "新列名"},
                    "expr": {
                        "type": "string",
                        "description": (
                            "pandas eval 风格表达式。直接引用列名，例如 '测量时刻.dt.hour'。"
                            "不支持 df[...]、lambda、if ... else ..."
                        ),
                    },
                },
                required=["column", "expr"],
            ),
            cls._build_step_variant(
                "filter_rows",
                {
                    "query": {
                        "type": "string",
                        "description": (
                            "pandas query 风格过滤表达式，例如 '(收缩压 > 140) & (心率 < 100)'。"
                            "不支持 df[...]、lambda、if ... else ..."
                        ),
                    }
                },
                required=["query"],
            ),
            cls._build_step_variant(
                "group_aggregate",
                {
                    "by": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "分组列名或列名列表",
                    },
                    "metrics": {
                        "type": "object",
                        "description": '聚合规则，例如 {"scaled":"sum"}',
                    },
                },
                required=["by", "metrics"],
            ),
            cls._build_step_variant(
                "sort_rows",
                {
                    "by": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "排序列名或列名列表",
                    },
                    "ascending": {"type": "boolean", "default": True},
                },
                required=["by"],
            ),
            cls._build_step_variant(
                "deduplicate",
                {
                    "subset": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "可选。去重子集列",
                    },
                    "keep": {
                        "anyOf": [
                            {"type": "string", "enum": ["first", "last"]},
                            {"type": "boolean", "enum": [False]},
                        ],
                        "description": "保留策略，支持 first、last 或 false",
                    },
                },
            ),
            cls._build_step_variant(
                "rename_columns",
                {
                    "mapping": {
                        "type": "object",
                        "description": '列名映射，例如 {"旧列":"新列"}',
                        "additionalProperties": {"type": "string"},
                    }
                },
                required=["mapping"],
            ),
            cls._build_step_variant(
                "select_columns",
                {
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "需要保留的列名列表",
                    }
                },
                required=["columns"],
            ),
            cls._build_step_variant(
                "clean_data",
                {
                    "missing_strategy": {"type": "string"},
                    "outlier_method": {"type": "string"},
                    "outlier_threshold": {"type": "number"},
                    "normalize_numeric": {"type": "boolean"},
                    "normalize_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            ),
            cls._build_step_variant(
                "recommend_cleaning_strategy",
                {
                    "target_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
            ),
        ]
        return {**base_item, "oneOf": variants}

    @staticmethod
    def _build_step_variant(
        op: str,
        params_properties: dict[str, Any],
        *,
        required: list[str] | None = None,
    ) -> dict[str, Any]:
        params_schema: dict[str, Any] = {
            "type": "object",
            "properties": params_properties,
            "additionalProperties": False,
        }
        if required:
            params_schema["required"] = required
        return {
            "properties": {
                "op": {"const": op},
                "params": params_schema,
            }
        }

    def _validation_result(
        self, exc: DatasetTransformValidationError | str, *, message: str | None = None
    ) -> ToolResult:
        if isinstance(exc, DatasetTransformValidationError):
            payload = exc.to_payload()
            return self.build_input_error(
                message=f"数据变换失败: {exc}",
                payload=payload,
            )
        return ToolResult(success=False, message=message or str(exc))

    def _input_error(self, *, message: str, payload: dict[str, Any]) -> ToolResult:
        return self.build_input_error(message=message, payload=payload)

    @classmethod
    def _validate_expression(cls, expr: str, *, step_id: str | None, op: str) -> None:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise DatasetTransformValidationError(
                f"表达式语法无效: {exc.msg}",
                error_code="DATASET_TRANSFORM_EXPR_SYNTAX_INVALID",
                expected_params=["expr"],
                recovery_hint=(
                    "请使用 pandas eval/query 风格表达式，直接引用列名。"
                    "如需自由 Python，请改用 code_session 并传 dataset_name。"
                ),
                minimal_example='{"column":"小时","expr":"测量时刻.dt.hour"}',
                step_id=step_id,
                op=op,
            ) from exc

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "df":
                raise DatasetTransformValidationError(
                    "表达式不支持引用 df 变量",
                    error_code="DATASET_TRANSFORM_EXPR_DF_UNSUPPORTED",
                    expected_params=["expr"],
                    recovery_hint=(
                        "在 dataset_transform 中请直接引用列名，例如 '测量时刻.dt.hour'；"
                        "如需使用 df[...] 或自由 Python，请改用 code_session 并传 dataset_name。"
                    ),
                    minimal_example='{"column":"小时","expr":"测量时刻.dt.hour"}',
                    step_id=step_id,
                    op=op,
                )
            if isinstance(node, ast.Lambda):
                raise DatasetTransformValidationError(
                    "表达式不支持 lambda",
                    error_code="DATASET_TRANSFORM_EXPR_LAMBDA_UNSUPPORTED",
                    expected_params=["expr"],
                    recovery_hint="请改写为列运算、布尔表达式或拆成多步处理。",
                    minimal_example='{"column":"白天标志","expr":"(小时 >= 6) & (小时 < 22)"}',
                    step_id=step_id,
                    op=op,
                )
            if isinstance(node, ast.IfExp):
                raise DatasetTransformValidationError(
                    "表达式不支持三元条件 if ... else ...",
                    error_code="DATASET_TRANSFORM_EXPR_IFEXP_UNSUPPORTED",
                    expected_params=["expr"],
                    recovery_hint=(
                        "请改用布尔表达式、分步衍生列，或切换到 code_session 执行自由 Python。"
                    ),
                    minimal_example='{"column":"白天标志","expr":"(小时 >= 6) & (小时 < 22)"}',
                    step_id=step_id,
                    op=op,
                )
