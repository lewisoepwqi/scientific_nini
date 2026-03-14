"""图表会话基础工具。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.models import ChartSessionRecord, ResourceType
from nini.tools.base import Skill, SkillResult
from nini.tools.export import ExportChartSkill
from nini.tools.visualization import CreateChartSkill
from nini.workspace import WorkspaceManager


class ChartSessionSkill(Skill):
    """管理图表会话资源。"""

    def __init__(self) -> None:
        self._create = CreateChartSkill()
        self._export = ExportChartSkill()

    @property
    def name(self) -> str:
        return "chart_session"

    @property
    def category(self) -> str:
        return "visualization"

    @property
    def description(self) -> str:
        return "创建、更新、查询和导出图表会话资源，图表规格持久化到受管资源目录。"

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
                "render_engine": {"type": "string"},
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
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        operation = str(kwargs.get("operation", "")).strip()
        if operation == "create":
            return await self._create_or_update(session, create=True, **kwargs)
        if operation == "update":
            return await self._create_or_update(session, create=False, **kwargs)
        if operation == "get":
            return self._get_chart(session, **kwargs)
        if operation == "export":
            return await self._export_chart(session, **kwargs)
        return SkillResult(success=False, message=f"不支持的 operation: {operation}")

    async def _create_or_update(self, session: Session, *, create: bool, **kwargs: Any) -> SkillResult:
        chart_id = str(kwargs.get("chart_id", "")).strip() or f"chart_{uuid.uuid4().hex[:12]}"
        existing = None if create else self._load_chart_record(session, chart_id)
        if not create and existing is None:
            return SkillResult(success=False, message=f"未找到图表会话: {chart_id}")

        spec = {
            "dataset_name": kwargs.get("dataset_name") or (existing.dataset_name if existing else ""),
            "chart_type": kwargs.get("chart_type") or (existing.chart_type if existing else ""),
            "title": kwargs.get("title") if "title" in kwargs else (existing.spec.get("title") if existing else None),
            "journal_style": kwargs.get("journal_style")
            or (existing.spec.get("journal_style") if existing else "default"),
            "render_engine": kwargs.get("render_engine")
            or (existing.render_engine if existing else None)
            or (
                "matplotlib"
                if getattr(session, "chart_output_preference", None) == "image"
                else "plotly"
                if getattr(session, "chart_output_preference", None) == "interactive"
                else "auto"
            ),
            "x_column": kwargs.get("x_column") if "x_column" in kwargs else (existing.spec.get("x_column") if existing else None),
            "y_column": kwargs.get("y_column") if "y_column" in kwargs else (existing.spec.get("y_column") if existing else None),
            "group_column": kwargs.get("group_column")
            if "group_column" in kwargs
            else (existing.spec.get("group_column") if existing else None),
            "color_column": kwargs.get("color_column")
            if "color_column" in kwargs
            else (existing.spec.get("color_column") if existing else None),
            "columns": kwargs.get("columns") if "columns" in kwargs else (existing.spec.get("columns") if existing else None),
            "bins": kwargs.get("bins") if "bins" in kwargs else (existing.spec.get("bins") if existing else None),
        }
        if not spec["dataset_name"] or not spec["chart_type"]:
            return SkillResult(
                success=False,
                message="create/update 图表会话必须提供 dataset_name 和 chart_type",
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
        )
        self._persist_chart_record(manager, record)
        return SkillResult(
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

    def _get_chart(self, session: Session, **kwargs: Any) -> SkillResult:
        chart_id = str(kwargs.get("chart_id", "")).strip()
        if not chart_id:
            return SkillResult(success=False, message="get 操作必须提供 chart_id")
        record = self._load_chart_record(session, chart_id)
        if record is None:
            return SkillResult(success=False, message=f"未找到图表会话: {chart_id}")
        manager = WorkspaceManager(session.id)
        return SkillResult(
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

    async def _export_chart(self, session: Session, **kwargs: Any) -> SkillResult:
        chart_id = str(kwargs.get("chart_id", "")).strip()
        if not chart_id:
            return SkillResult(success=False, message="export 操作必须提供 chart_id")
        record = self._load_chart_record(session, chart_id)
        if record is None:
            return SkillResult(success=False, message=f"未找到图表会话: {chart_id}")

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
        result = await self._export.execute(session, **export_params)
        if not result.success:
            return result

        manager = WorkspaceManager(session.id)
        record.artifact_ids = self._resolve_artifact_ids(manager, recreate.artifacts)
        record.last_export_ids = self._resolve_artifact_ids(manager, result.artifacts)
        self._persist_chart_record(manager, record)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["chart_id"] = chart_id
        data["resource_id"] = chart_id
        data["resource_type"] = "chart"
        payload["data"] = data
        return SkillResult(**payload)

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
