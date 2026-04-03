"""图表会话基础工具。"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.config import settings
from nini.models import ChartSessionRecord, ResourceType
from nini.tools.base import Tool, ToolResult
from nini.tools.export import ExportChartTool
from nini.tools.visualization import CreateChartTool
from nini.workspace import WorkspaceManager


class ChartSessionTool(Tool):
    """管理图表会话资源。"""

    def __init__(self) -> None:
        self._create = CreateChartTool()
        self._export = ExportChartTool()

    @property
    def name(self) -> str:
        return "chart_session"

    @property
    def category(self) -> str:
        return "visualization"

    @property
    def description(self) -> str:
        return (
            "创建、更新、查询和导出图表会话资源，规格持久化到受管资源目录。\n"
            "最小示例：{operation: create, dataset_name: demo, chart_type: line, x_column: x, y_column: y}\n"
            "约束：create 需 dataset_name+chart_type；update/get/export 需 chart_id。"
            "render_engine 支持 auto/plotly/matplotlib。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "update", "get", "export"],
                },
                "chart_id": {"type": "string"},
                "dataset_name": {"type": "string"},
                "chart_type": {
                    "type": "string",
                    "enum": ["scatter", "line", "bar", "box", "violin", "histogram", "heatmap"],
                },
                "title": {"type": "string"},
                "journal_style": {"type": "string"},
                "render_engine": {
                    "type": "string",
                    "enum": ["auto", "plotly", "matplotlib"],
                    "description": "渲染引擎：auto|plotly|matplotlib",
                },
                "x_column": {"type": "string"},
                "y_column": {"type": "string"},
                "group_column": {"type": "string"},
                "color_column": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "bins": {"type": "integer"},
                "format": {"type": "string"},
                "filename": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "scale": {"type": "number"},
            },
            "required": ["operation"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "operation": {"const": "create"},
                    },
                    "required": ["operation", "dataset_name", "chart_type"],
                },
                {
                    "type": "object",
                    "properties": {
                        "operation": {"const": "update"},
                    },
                    "required": ["operation", "chart_id"],
                },
                {
                    "type": "object",
                    "properties": {
                        "operation": {"const": "get"},
                    },
                    "required": ["operation", "chart_id"],
                },
                {
                    "type": "object",
                    "properties": {
                        "operation": {"const": "export"},
                    },
                    "required": ["operation", "chart_id"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()
        if operation == "create":
            return await self._create_or_update(session, create=True, **kwargs)
        if operation == "update":
            return await self._create_or_update(session, create=False, **kwargs)
        if operation == "get":
            return self._get_chart(session, **kwargs)
        if operation == "export":
            return await self._export_chart(session, **kwargs)
        return self._input_error(
            operation=operation,
            error_code="CHART_SESSION_OPERATION_INVALID",
            message=f"不支持的 operation: {operation}",
            expected_fields=["operation"],
            recovery_hint="请将 operation 改为 create、update、get 或 export 之一。",
            minimal_example='{operation: "create", dataset_name: "trend_demo", chart_type: "line"}',
        )

    async def _create_or_update(
        self, session: Session, *, create: bool, **kwargs: Any
    ) -> ToolResult:
        chart_id = str(kwargs.get("chart_id", "")).strip() or f"chart_{uuid.uuid4().hex[:12]}"
        if not create and not str(kwargs.get("chart_id", "")).strip():
            return self._input_error(
                operation="update",
                error_code="CHART_SESSION_UPDATE_CHART_ID_REQUIRED",
                message="update 操作必须提供 chart_id",
                expected_fields=["operation", "chart_id"],
                recovery_hint="先提供已有图表的 chart_id，再传入要更新的字段。",
                minimal_example=self._minimal_example_for_operation("update"),
            )
        existing = None if create else self._load_chart_record(session, chart_id)
        if not create and existing is None:
            return ToolResult(success=False, message=f"未找到图表会话: {chart_id}")

        spec = {
            "dataset_name": kwargs.get("dataset_name")
            or (existing.dataset_name if existing else ""),
            "chart_type": kwargs.get("chart_type") or (existing.chart_type if existing else ""),
            "title": (
                kwargs.get("title")
                if "title" in kwargs
                else (existing.spec.get("title") if existing else None)
            ),
            "journal_style": kwargs.get("journal_style")
            or (existing.spec.get("journal_style") if existing else "default"),
            "render_engine": kwargs.get("render_engine")
            or (existing.render_engine if existing else None)
            or (
                "matplotlib"
                if getattr(session, "chart_output_preference", None) == "image"
                else (
                    "plotly"
                    if getattr(session, "chart_output_preference", None) == "interactive"
                    else "auto"
                )
            ),
            "x_column": (
                kwargs.get("x_column")
                if "x_column" in kwargs
                else (existing.spec.get("x_column") if existing else None)
            ),
            "y_column": (
                kwargs.get("y_column")
                if "y_column" in kwargs
                else (existing.spec.get("y_column") if existing else None)
            ),
            "group_column": (
                kwargs.get("group_column")
                if "group_column" in kwargs
                else (existing.spec.get("group_column") if existing else None)
            ),
            "color_column": (
                kwargs.get("color_column")
                if "color_column" in kwargs
                else (existing.spec.get("color_column") if existing else None)
            ),
            "columns": (
                kwargs.get("columns")
                if "columns" in kwargs
                else (existing.spec.get("columns") if existing else None)
            ),
            "bins": (
                kwargs.get("bins")
                if "bins" in kwargs
                else (existing.spec.get("bins") if existing else None)
            ),
        }
        if not spec["dataset_name"] or not spec["chart_type"]:
            expected_fields = ["operation"]
            if create:
                expected_fields.extend(["dataset_name", "chart_type"])
            else:
                if not spec["dataset_name"]:
                    expected_fields.append("dataset_name")
                if not spec["chart_type"]:
                    expected_fields.append("chart_type")
                expected_fields.insert(1, "chart_id")
            return self._input_error(
                operation="create" if create else "update",
                error_code=(
                    "CHART_SESSION_CREATE_FIELDS_REQUIRED"
                    if create
                    else "CHART_SESSION_UPDATE_FIELDS_REQUIRED"
                ),
                message="create/update 图表会话必须提供 dataset_name 和 chart_type",
                expected_fields=expected_fields,
                recovery_hint=(
                    "create 时请显式提供 dataset_name 和 chart_type；"
                    "update 时若原记录缺少这些字段，也需要一并补齐。"
                ),
                minimal_example=self._minimal_example_for_operation(
                    "create" if create else "update"
                ),
            )

        create_params = {k: v for k, v in spec.items() if v is not None}
        result = await self._create.execute(session, **create_params)
        if not result.success:
            return result

        manager = WorkspaceManager(session.id)
        artifact_ids = self._resolve_artifact_ids(manager, result.artifacts)
        record = ChartSessionRecord(
            id=chart_id,
            session_id=session.id,
            dataset_name=str(spec["dataset_name"]),
            chart_type=str(spec["chart_type"]),
            spec=spec,
            render_engine=str(spec.get("render_engine") or "auto"),
            artifact_ids=artifact_ids,
            last_export_ids=existing.last_export_ids if existing else [],
            last_export_metadata=existing.last_export_metadata if existing else {},
        )
        self._persist_chart_record(manager, record)
        return ToolResult(
            success=True,
            message=f"图表会话已{'创建' if create else '更新'}：{chart_id}",
            data={
                "chart_id": chart_id,
                "resource_id": chart_id,
                "resource_type": "chart",
                "record": record.model_dump(mode="json"),
            },
            has_chart=result.has_chart,
            chart_data=result.chart_data,
            artifacts=result.artifacts,
        )

    def _get_chart(self, session: Session, **kwargs: Any) -> ToolResult:
        chart_id = str(kwargs.get("chart_id", "")).strip()
        if not chart_id:
            return self._input_error(
                operation="get",
                error_code="CHART_SESSION_GET_CHART_ID_REQUIRED",
                message="get 操作必须提供 chart_id",
                expected_fields=["operation", "chart_id"],
                recovery_hint="先传入要读取的图表会话 chart_id。",
                minimal_example=self._minimal_example_for_operation("get"),
            )
        record = self._load_chart_record(session, chart_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到图表会话: {chart_id}")
        manager = WorkspaceManager(session.id)
        return ToolResult(
            success=True,
            message=f"已读取图表会话 '{chart_id}'",
            data={
                "chart_id": chart_id,
                "resource_id": chart_id,
                "resource_type": "chart",
                "record": record.model_dump(mode="json"),
                "resource": manager.get_resource_summary(chart_id),
            },
        )

    async def _export_chart(self, session: Session, **kwargs: Any) -> ToolResult:
        chart_id = str(kwargs.get("chart_id", "")).strip()
        if not chart_id:
            return self._input_error(
                operation="export",
                error_code="CHART_SESSION_EXPORT_CHART_ID_REQUIRED",
                message="export 操作必须提供 chart_id",
                expected_fields=["operation", "chart_id"],
                recovery_hint="先传入已存在的图表会话 chart_id，再指定导出格式。",
                minimal_example=self._minimal_example_for_operation("export"),
            )
        record = self._load_chart_record(session, chart_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到图表会话: {chart_id}")

        create_params = {k: v for k, v in record.spec.items() if v is not None}
        recreate = await self._create.execute(session, **create_params)
        if not recreate.success:
            return recreate

        export_params = {
            "format": kwargs.get("format", "png"),
            "filename": kwargs.get("filename"),
            "width": kwargs.get("width", 1200),
            "height": kwargs.get("height", 800),
            "scale": kwargs.get("scale", 2.0),
        }
        manager = WorkspaceManager(session.id)
        source_task_id = str(session.deep_task_state.get("task_id", "")).strip() or None
        requested_format = str(kwargs.get("format", "png")).strip() or "png"
        export_job = manager.create_export_job(
            target_resource_id=chart_id,
            target_resource_type="chart",
            output_format=requested_format,
            template_id=str(record.spec.get("journal_style") or "default"),
            source_task_id=source_task_id,
            idempotency_key=(
                f"chart-export:{source_task_id}:{chart_id}:{requested_format}"
                if source_task_id
                else None
            ),
            status="running",
            metadata={"chart_type": record.chart_type, "dataset_name": record.dataset_name},
        )
        timeout_seconds = max(1, int(settings.deep_task_external_timeout_seconds))
        max_attempts = max(1, int(settings.deep_task_external_retry_limit) + 1)
        attempt_log: list[dict[str, Any]] = []
        result: ToolResult | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                current = await asyncio.wait_for(
                    self._export.execute(session, **export_params),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                message = (
                    f"图表导出超时：超过 {timeout_seconds} 秒，"
                    f"第 {attempt}/{max_attempts} 次尝试失败。"
                )
                attempt_log.append({"attempt": attempt, "status": "timeout", "message": message})
                manager.update_export_job(
                    str(export_job.get("id", "")),
                    message=message,
                    metadata={
                        "external_attempts": attempt_log,
                        "retry_policy": {
                            "max_attempts": max_attempts,
                            "timeout_seconds": timeout_seconds,
                        },
                    },
                )
                if attempt >= max_attempts:
                    result = ToolResult(success=False, message=message)
                    break
                continue

            result = current
            attempt_log.append(
                {
                    "attempt": attempt,
                    "status": "success" if current.success else "error",
                    "message": current.message,
                }
            )
            manager.update_export_job(
                str(export_job.get("id", "")),
                metadata={
                    "external_attempts": attempt_log,
                    "retry_policy": {
                        "max_attempts": max_attempts,
                        "timeout_seconds": timeout_seconds,
                    },
                },
            )
            if current.success or attempt >= max_attempts:
                break

        if result is None or not result.success:
            manager.update_export_job(
                str(export_job.get("id", "")),
                status="failed",
                message=(result.message if result is not None else "图表导出失败"),
            )
            return result or ToolResult(success=False, message="图表导出失败")

        record.artifact_ids = self._resolve_artifact_ids(manager, recreate.artifacts)
        record.last_export_ids = self._resolve_artifact_ids(manager, result.artifacts)
        actual_format = (
            str((result.data or {}).get("format", "")).strip()
            if isinstance(result.data, dict)
            else ""
        ) or requested_format
        failed_formats = [requested_format] if actual_format != requested_format else []
        chart_artifact_name = (
            str((result.data or {}).get("filename", "")).strip()
            if isinstance(result.data, dict)
            else ""
        )
        chart_artifact_path = (
            manager.resolve_workspace_path(
                f"artifacts/{chart_artifact_name}" if chart_artifact_name else "",
                allow_missing=True,
            )
            if chart_artifact_name
            else None
        )
        if chart_artifact_name and chart_artifact_path is not None and chart_artifact_path.exists():
            project_artifact = manager.register_project_artifact(
                artifact_type="chart",
                name=chart_artifact_name,
                path=chart_artifact_path,
                format=actual_format,
                template_id=str(record.spec.get("journal_style") or "default"),
                resource_id=chart_id,
                source_task_id=source_task_id,
                export_job_id=str(export_job.get("id", "")),
                idempotency_key=(
                    f"project-artifact:{source_task_id}:{chart_id}:{requested_format}"
                    if source_task_id
                    else None
                ),
                logical_key=f"chart:{chart_id}:{requested_format}",
                available_formats=[actual_format],
                failed_formats=failed_formats,
                metadata={
                    "chart_type": record.chart_type,
                    "render_engine": record.render_engine,
                    "resolution": {
                        "width": int(kwargs.get("width", 1200)),
                        "height": int(kwargs.get("height", 800)),
                        "scale": float(kwargs.get("scale", 2.0)),
                    },
                    "style_template": record.spec.get("journal_style") or "default",
                },
            )
            manager.update_export_job(
                str(export_job.get("id", "")),
                status="completed",
                output_artifact_ids=[str(project_artifact.get("id", ""))],
                message="图表导出完成",
            )
        else:
            manager.update_export_job(
                str(export_job.get("id", "")),
                status="completed",
                message="图表导出完成",
            )
        record.last_export_metadata = {
            "requested_format": requested_format,
            "successful_formats": [actual_format],
            "failed_formats": failed_formats,
            "style_template": record.spec.get("journal_style") or "default",
            "resolution": {
                "width": int(kwargs.get("width", 1200)),
                "height": int(kwargs.get("height", 800)),
                "scale": float(kwargs.get("scale", 2.0)),
            },
            "export_job_id": export_job.get("id"),
        }
        self._persist_chart_record(manager, record)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["chart_id"] = chart_id
        data["resource_id"] = chart_id
        data["resource_type"] = "chart"
        data["export_job_id"] = export_job.get("id")
        data["successful_formats"] = [actual_format]
        data["failed_formats"] = failed_formats
        payload["data"] = data
        return ToolResult(**payload)

    def _record_path(self, manager: WorkspaceManager, chart_id: str) -> Path:
        return manager.build_managed_resource_path(
            ResourceType.CHART,
            f"{chart_id}.json",
            default_name=f"{chart_id}.json",
        )

    def _load_chart_record(self, session: Session, chart_id: str) -> ChartSessionRecord | None:
        manager = WorkspaceManager(session.id)
        path = self._record_path(manager, chart_id)
        if not path.exists():
            return None
        try:
            return ChartSessionRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _persist_chart_record(self, manager: WorkspaceManager, record: ChartSessionRecord) -> None:
        path = self._record_path(manager, record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manager.upsert_managed_resource(
            resource_id=record.id,
            resource_type=ResourceType.CHART,
            name=self._display_name(record),
            path=path,
            source_kind="charts",
            metadata={
                "dataset_name": record.dataset_name,
                "chart_type": record.chart_type,
                "render_engine": record.render_engine,
                "title": record.spec.get("title") or "",
                "artifact_ids": record.artifact_ids,
                "last_export_ids": record.last_export_ids,
                "last_export_metadata": record.last_export_metadata,
            },
        )

    def _display_name(self, record: ChartSessionRecord) -> str:
        title = str(record.spec.get("title") or "").strip()
        if title:
            return title
        return f"{record.chart_type}:{record.dataset_name}"

    def _resolve_artifact_ids(
        self,
        manager: WorkspaceManager,
        artifacts: list[dict[str, Any]] | None,
    ) -> list[str]:
        if not isinstance(artifacts, list):
            return []
        records = manager.list_artifacts()
        ids: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path", "")).strip()
            name = str(artifact.get("name", "")).strip()
            for record in records:
                if not isinstance(record, dict):
                    continue
                if path and str(record.get("path", "")).strip() == path:
                    ids.append(str(record.get("id", "")))
                    break
                if name and str(record.get("name", "")).strip() == name:
                    ids.append(str(record.get("id", "")))
                    break
        return [item for item in ids if item]

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
            "create": (
                '{operation: "create", dataset_name: "trend_demo", chart_type: "line", '
                'x_column: "month", y_column: "value"}'
            ),
            "update": '{operation: "update", chart_id: "chart_trend_demo", title: "新标题"}',
            "get": '{operation: "get", chart_id: "chart_trend_demo"}',
            "export": '{operation: "export", chart_id: "chart_trend_demo", format: "png"}',
        }
        return examples.get(operation, '{operation: "create", dataset_name: "trend_demo"}')
