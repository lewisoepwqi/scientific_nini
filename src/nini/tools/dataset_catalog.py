"""数据目录基础工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.data_ops import DataSummaryTool, LoadDatasetTool, PreviewDataTool
from nini.tools.data_quality import DataQualityTool
from nini.workspace import WorkspaceManager


class DatasetCatalogTool(Tool):
    """统一数据集目录入口。"""

    def __init__(self) -> None:
        self._loader = LoadDatasetTool()
        self._preview = PreviewDataTool()
        self._summary = DataSummaryTool()
        self._quality = DataQualityTool()

    @property
    def name(self) -> str:
        return "dataset_catalog"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return (
            "统一管理数据集目录：list/load/profile 操作。\可聚合预览、摘要与质量概览。\n"
            "最小示例：{operation: profile, dataset_name: demo, view: full, n_rows: 5}\n"
            "约束：load/profile 必须提供 dataset_name。view=preview/full 可用 n_rows。 其他 view 忽略 n_rows。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "load", "profile"],
                    "description": "数据目录操作类型",
                },
                "dataset_name": {
                    "type": "string",
                    "description": "目标数据集名称",
                },
                "view": {
                    "type": "string",
                    "enum": ["basic", "preview", "summary", "quality", "full"],
                    "default": "basic",
                    "description": "profile 模式下的概况视图",
                },
                "n_rows": {
                    "type": "integer",
                    "default": 5,
                    "description": "preview/full 模式下的预览行数",
                },
                "sheet_mode": {
                    "type": "string",
                    "enum": ["default", "single", "all"],
                    "default": "default",
                    "description": "load 模式下的 Excel 读取模式",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "load 模式下指定 sheet 名称",
                },
                "combine_sheets": {
                    "type": "boolean",
                    "default": False,
                    "description": "load 模式下是否合并全部 sheet",
                },
                "include_sheet_column": {
                    "type": "boolean",
                    "default": True,
                    "description": "load 合并模式下是否增加来源 sheet 列",
                },
                "output_dataset_name": {
                    "type": "string",
                    "description": "load 模式下可选的输出数据集名称",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"operation": {"const": "list"}},
                    "required": ["operation"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "load"}},
                    "required": ["operation", "dataset_name"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "profile"}},
                    "required": ["operation", "dataset_name"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()

        if operation == "list":
            return self._list_datasets(session)
        if operation == "load":
            return await self._load_dataset(session, **kwargs)
        if operation == "profile":
            return await self._profile_dataset(session, **kwargs)
        return self._input_error(
            operation=operation,
            error_code="DATASET_CATALOG_OPERATION_INVALID",
            message=f"不支持的 operation: {operation}",
            expected_fields=["operation"],
            recovery_hint="请将 operation 改为 list、load 或 profile。",
            minimal_example='{operation: "list"}',
        )

    def _list_datasets(self, session: Session) -> ToolResult:
        manager = WorkspaceManager(session.id)
        workspace_records = {
            str(item.get("name", "")).strip(): item for item in manager.list_datasets()
        }
        dataset_names = sorted(set(workspace_records) | set(session.datasets.keys()))
        items: list[dict[str, Any]] = []

        for name in dataset_names:
            record = workspace_records.get(name)
            resource_id = str(record.get("id", "")).strip() if isinstance(record, dict) else ""
            loaded = name in session.datasets
            rows = (
                len(session.datasets[name])
                if loaded
                else record.get("row_count") if record else None
            )
            columns = (
                len(session.datasets[name].columns)
                if loaded
                else record.get("column_count") if record else None
            )
            items.append(
                {
                    "resource_id": resource_id or None,
                    "resource_type": "dataset",
                    "name": name,
                    "loaded": loaded,
                    "rows": rows,
                    "columns": columns,
                    "file_type": record.get("file_type") if record else None,
                    "file_path": record.get("file_path") if record else None,
                }
            )

        return ToolResult(
            success=True,
            message=f"当前可用 {len(items)} 个数据集",
            data={"datasets": items},
        )

    async def _load_dataset(self, session: Session, **kwargs: Any) -> ToolResult:
        dataset_name = str(kwargs.get("dataset_name", "")).strip()
        if not dataset_name:
            return self._input_error(
                operation="load",
                error_code="DATASET_CATALOG_LOAD_DATASET_NAME_REQUIRED",
                message="load 操作必须提供 dataset_name",
                expected_fields=["operation", "dataset_name"],
                recovery_hint="先传入要加载的数据集名称；如需指定 Excel sheet，可继续补充 sheet_mode/sheet_name。",
                minimal_example=self._minimal_example_for_operation("load"),
            )

        result = await self._loader.execute(
            session,
            dataset_name=dataset_name,
            sheet_mode=kwargs.get("sheet_mode", "default"),
            sheet_name=kwargs.get("sheet_name"),
            combine_sheets=kwargs.get("combine_sheets", False),
            include_sheet_column=kwargs.get("include_sheet_column", True),
            output_dataset_name=kwargs.get("output_dataset_name"),
        )
        if not result.success:
            return result

        target_name = dataset_name
        if isinstance(result.data, dict):
            target_name = str(result.data.get("output_dataset") or dataset_name)

        manager = WorkspaceManager(session.id)
        record = manager.get_dataset_by_name(target_name)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["resource_id"] = (str(record.get("id", "")).strip() or None) if record else None
        data["resource_type"] = "dataset"
        data["dataset_name"] = target_name
        payload["data"] = data
        return ToolResult(**payload)

    async def _profile_dataset(self, session: Session, **kwargs: Any) -> ToolResult:
        dataset_name = str(kwargs.get("dataset_name", "")).strip()
        if not dataset_name:
            return self._input_error(
                operation="profile",
                error_code="DATASET_CATALOG_PROFILE_DATASET_NAME_REQUIRED",
                message="profile 操作必须提供 dataset_name",
                expected_fields=["operation", "dataset_name"],
                recovery_hint="先传入要查看概况的数据集名称，再选择 view。",
                minimal_example=self._minimal_example_for_operation("profile"),
            )

        view = str(kwargs.get("view", "basic")).strip()
        manager = WorkspaceManager(session.id)
        record = manager.get_dataset_by_name(dataset_name)
        if dataset_name not in session.datasets:
            load_result = await self._loader.execute(session, dataset_name=dataset_name)
            if not load_result.success:
                return load_result

        base: dict[str, Any] = {
            "resource_id": (str(record.get("id", "")).strip() or None) if record else None,
            "resource_type": "dataset",
            "dataset_name": dataset_name,
        }

        if view in {"basic", "full"}:
            info = await self._loader.execute(session, dataset_name=dataset_name)
            if info.success and isinstance(info.data, dict):
                base["basic"] = info.data

        if view in {"preview", "full"}:
            preview = await self._preview.execute(
                session,
                dataset_name=dataset_name,
                n_rows=kwargs.get("n_rows", 5),
            )
            if preview.success and isinstance(preview.data, dict):
                base["preview"] = preview.data

        if view in {"summary", "full"}:
            summary = await self._summary.execute(session, dataset_name=dataset_name)
            if summary.success and isinstance(summary.data, dict):
                base["summary"] = summary.data

        if view in {"quality", "full"}:
            quality = await self._quality.execute(session, dataset_name=dataset_name)
            if quality.success and isinstance(quality.data, dict):
                base["quality"] = quality.data

        return ToolResult(
            success=True,
            message=f"已生成数据集 '{dataset_name}' 的 {view} 概况",
            data=base,
            has_dataframe="preview" in base,
            dataframe_preview=base.get("preview"),
        )

    def _input_error(
        self,
        *,
        operation: str,
        error_code: str,
        message: str,
        expected_fields: list[str],
        recovery_hint: str,
        minimal_example: str,
    ) -> ToolResult:
        payload = {
            "operation": operation,
            "error_code": error_code,
            "expected_fields": expected_fields,
            "recovery_hint": recovery_hint,
            "minimal_example": minimal_example,
        }
        return self.build_input_error(message=message, payload=payload)

    def _minimal_example_for_operation(self, operation: str) -> str:
        examples = {
            "list": '{operation: "list"}',
            "load": '{operation: "load", dataset_name: "demo"}',
            "profile": '{operation: "profile", dataset_name: "demo", view: "full", n_rows: 5}',
        }
        return examples.get(operation, '{operation: "list"}')
