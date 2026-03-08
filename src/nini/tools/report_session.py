"""报告会话基础工具。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.models import ReportSection, ReportSessionRecord, ResourceType
from nini.tools.base import Skill, SkillResult
from nini.tools.export_report import export_workspace_document
from nini.tools.report import _sanitize_chinese_filename
from nini.workspace import WorkspaceManager


class ReportSessionSkill(Skill):
    """管理报告会话资源。"""

    _EMBEDDED_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
    _EMBEDDED_CHART_SUFFIXES = (".plotly.json",)

    @property
    def name(self) -> str:
        return "report_session"

    @property
    def category(self) -> str:
        return "report"

    @property
    def description(self) -> str:
        return "创建、更新、查询和导出报告会话资源，章节结构持久化到受管资源目录。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "patch_section", "attach_artifact", "get", "export"],
                },
                "report_id": {"type": "string"},
                "title": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "attachments": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["key", "title"],
                    },
                },
                "summary_text": {"type": "string"},
                "methods": {"type": "string"},
                "conclusions": {"type": "string"},
                "section_key": {"type": "string"},
                "mode": {"type": "string", "enum": ["replace", "append"]},
                "content": {"type": "string"},
                "artifact_resource_id": {"type": "string"},
                "output_format": {"type": "string", "enum": ["pdf", "docx"]},
                "filename": {"type": "string"},
            },
            "required": ["operation"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        operation = str(kwargs.get("operation", "")).strip()
        if operation == "create":
            return self._create_report(session, **kwargs)
        if operation == "patch_section":
            return self._patch_section(session, **kwargs)
        if operation == "attach_artifact":
            return self._attach_artifact(session, **kwargs)
        if operation == "get":
            return self._get_report(session, **kwargs)
        if operation == "export":
            return await self._export_report(session, **kwargs)
        return SkillResult(success=False, message=f"不支持的 operation: {operation}")

    def _create_report(self, session: Session, **kwargs: Any) -> SkillResult:
        report_id = str(kwargs.get("report_id", "")).strip() or f"report_{uuid.uuid4().hex[:12]}"
        title = str(kwargs.get("title", "")).strip() or "科研数据分析报告"
        sections = self._normalize_sections(kwargs)
        record = ReportSessionRecord(
            id=report_id,
            session_id=session.id,
            title=title,
            sections=sections,
        )
        filename = self._normalize_markdown_filename(kwargs.get("filename"))
        if filename:
            record.markdown_path = f"notes/reports/{filename}"
        manager = WorkspaceManager(session.id)
        markdown_rel_path = self._write_report_markdown(manager, record)
        record.markdown_path = markdown_rel_path
        self._persist_report_record(manager, record)
        self._update_latest_report_handles(session, record)
        return SkillResult(
            success=True,
            message=f"报告会话已创建：{report_id}",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
            },
        )

    def _patch_section(self, session: Session, **kwargs: Any) -> SkillResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        if not report_id:
            return SkillResult(success=False, message="patch_section 操作必须提供 report_id")
        record = self._load_report_record(session, report_id)
        if record is None:
            return SkillResult(success=False, message=f"未找到报告会话: {report_id}")
        section_key = str(kwargs.get("section_key", "")).strip()
        if not section_key:
            return SkillResult(success=False, message="patch_section 操作必须提供 section_key")
        mode = str(kwargs.get("mode", "replace")).strip() or "replace"
        content = str(kwargs.get("content", "") or "")
        matched = False
        for section in record.sections:
            if section.key != section_key:
                continue
            section.content = content if mode == "replace" else section.content + content
            matched = True
            break
        if not matched:
            return SkillResult(success=False, message=f"未找到章节: {section_key}")
        manager = WorkspaceManager(session.id)
        markdown_rel_path = self._write_report_markdown(manager, record)
        record.markdown_path = markdown_rel_path
        self._persist_report_record(manager, record)
        self._update_latest_report_handles(session, record)
        return SkillResult(
            success=True,
            message=f"报告章节已更新：{section_key}",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
            },
        )

    def _attach_artifact(self, session: Session, **kwargs: Any) -> SkillResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        artifact_resource_id = str(kwargs.get("artifact_resource_id", "")).strip()
        section_key = str(kwargs.get("section_key", "")).strip()
        if not report_id or not artifact_resource_id or not section_key:
            return SkillResult(
                success=False,
                message="attach_artifact 操作必须提供 report_id、section_key 和 artifact_resource_id",
            )
        record = self._load_report_record(session, report_id)
        if record is None:
            return SkillResult(success=False, message=f"未找到报告会话: {report_id}")
        matched = False
        for section in record.sections:
            if section.key != section_key:
                continue
            if artifact_resource_id not in section.attachments:
                section.attachments.append(artifact_resource_id)
            matched = True
            break
        if not matched:
            return SkillResult(success=False, message=f"未找到章节: {section_key}")
        manager = WorkspaceManager(session.id)
        markdown_rel_path = self._write_report_markdown(manager, record)
        record.markdown_path = markdown_rel_path
        self._persist_report_record(manager, record)
        self._update_latest_report_handles(session, record)
        return SkillResult(
            success=True,
            message=f"已为章节 '{section_key}' 绑定资源",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
            },
        )

    def _get_report(self, session: Session, **kwargs: Any) -> SkillResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        if not report_id:
            return SkillResult(success=False, message="get 操作必须提供 report_id")
        record = self._load_report_record(session, report_id)
        if record is None:
            return SkillResult(success=False, message=f"未找到报告会话: {report_id}")
        manager = WorkspaceManager(session.id)
        return SkillResult(
            success=True,
            message=f"已读取报告会话 '{report_id}'",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
                "resource": manager.get_resource_summary(report_id),
            },
        )

    async def _export_report(self, session: Session, **kwargs: Any) -> SkillResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        if not report_id:
            return SkillResult(success=False, message="export 操作必须提供 report_id")
        record = self._load_report_record(session, report_id)
        if record is None or not record.markdown_path:
            return SkillResult(success=False, message=f"未找到可导出的报告会话: {report_id}")
        output_format = str(kwargs.get("output_format", "pdf")).strip() or "pdf"
        result = await export_workspace_document(
            session,
            source_ref=record.markdown_path,
            output_format=output_format,
            filename=str(kwargs.get("filename", "")).strip() or None,
            prefer_latest_report=False,
        )
        if not result.success:
            return result
        manager = WorkspaceManager(session.id)
        record.export_ids = self._resolve_artifact_ids(manager, result.artifacts)
        self._persist_report_record(manager, record)
        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["report_id"] = report_id
        data["resource_id"] = report_id
        data["resource_type"] = "report"
        payload["data"] = data
        return SkillResult(**payload)

    def _normalize_sections(self, kwargs: dict[str, Any]) -> list[ReportSection]:
        raw_sections = kwargs.get("sections")
        if isinstance(raw_sections, list) and raw_sections:
            return [ReportSection.model_validate(item) for item in raw_sections if isinstance(item, dict)]

        sections: list[ReportSection] = []
        methods = str(kwargs.get("methods", "") or "").strip()
        summary_text = str(kwargs.get("summary_text", "") or "").strip()
        conclusions = str(kwargs.get("conclusions", "") or "").strip()
        if methods:
            sections.append(ReportSection(key="methods", title="分析方法", content=methods))
        if summary_text:
            sections.append(ReportSection(key="summary", title="分析摘要", content=summary_text))
        if conclusions:
            sections.append(ReportSection(key="conclusions", title="结论与建议", content=conclusions))
        if not sections:
            sections.append(ReportSection(key="summary", title="分析摘要", content=""))
        return sections

    def _record_path(self, manager: WorkspaceManager, report_id: str) -> Path:
        return manager.build_managed_resource_path(
            ResourceType.REPORT,
            f"{report_id}.json",
            default_name=f"{report_id}.json",
        )

    def _load_report_record(self, session: Session, report_id: str) -> ReportSessionRecord | None:
        manager = WorkspaceManager(session.id)
        path = self._record_path(manager, report_id)
        if not path.exists():
            return None
        try:
            return ReportSessionRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _persist_report_record(self, manager: WorkspaceManager, record: ReportSessionRecord) -> None:
        path = self._record_path(manager, record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manager.upsert_managed_resource(
            resource_id=record.id,
            resource_type=ResourceType.REPORT,
            name=record.title,
            path=path,
            source_kind="reports",
            metadata={
                "title": record.title,
                "markdown_path": record.markdown_path,
                "section_count": len(record.sections),
                "section_keys": [section.key for section in record.sections],
                "export_ids": record.export_ids,
            },
        )

    def _write_report_markdown(self, manager: WorkspaceManager, record: ReportSessionRecord) -> str:
        rel_path = record.markdown_path
        if not rel_path:
            safe_title = _sanitize_chinese_filename(record.title, max_bytes=60) or record.id
            rel_path = f"notes/reports/{safe_title}_{record.id}.md"
        lines = [f"# {record.title}", ""]
        for section in record.sections:
            lines.append(f"## {section.title}")
            lines.append(section.content or "")
            if section.attachments:
                lines.append("")
                lines.append("### 关联资源")
                for resource_id in section.attachments:
                    lines.extend(self._resource_markdown_lines(manager, resource_id))
            lines.append("")
        manager.save_text_file(rel_path, "\n".join(lines).strip() + "\n")
        return rel_path

    def _normalize_markdown_filename(self, filename: Any) -> str | None:
        if not isinstance(filename, str) or not filename.strip():
            return None
        normalized = filename.strip()
        if not normalized.lower().endswith(".md"):
            normalized += ".md"
        return normalized.lstrip("/").replace("\\", "/")

    def _resource_markdown_lines(self, manager: WorkspaceManager, resource_id: str) -> list[str]:
        resource = manager.get_resource_summary(resource_id)
        if not isinstance(resource, dict):
            return [f"- 资源 `{resource_id}`"]
        embedded_resource = self._resolve_embeddable_resource(manager, resource)
        if embedded_resource is not None:
            resource = embedded_resource
        name = str(resource.get("name", resource_id)).strip() or resource_id
        url = str(resource.get("download_url", "")).strip()
        if url and self._should_embed_resource(resource, name=name, url=url):
            return [f"![{name}]({url})", ""]
        if url:
            return [f"- [{name}]({url})"]
        return [f"- 资源 `{name}`"]

    def _resolve_embeddable_resource(
        self,
        manager: WorkspaceManager,
        resource: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """将图表会话资源解析到可直接嵌入的图片产物。"""
        if not isinstance(resource, dict):
            return None
        resource_type = str(resource.get("resource_type", "")).strip().lower()
        if resource_type != ResourceType.CHART.value:
            return None

        metadata = resource.get("metadata")
        if not isinstance(metadata, dict):
            return None

        candidate_ids: list[str] = []
        for field in ("last_export_ids", "artifact_ids"):
            raw_ids = metadata.get(field)
            if not isinstance(raw_ids, list):
                continue
            for item in raw_ids:
                candidate_id = str(item).strip()
                if candidate_id and candidate_id not in candidate_ids:
                    candidate_ids.append(candidate_id)

        for candidate_id in candidate_ids:
            candidate = manager.get_resource_summary(candidate_id)
            if not isinstance(candidate, dict):
                continue
            candidate_name = str(candidate.get("name", "")).strip().lower()
            candidate_url = str(candidate.get("download_url", "")).strip().lower()
            candidate_mime = str(candidate.get("mime_type", "")).strip().lower()
            if candidate_mime.startswith("image/"):
                return candidate
            if candidate_name.endswith(self._EMBEDDED_IMAGE_SUFFIXES):
                return candidate
            if candidate_url.endswith(self._EMBEDDED_IMAGE_SUFFIXES):
                return candidate
        return None

    def _should_embed_resource(
        self,
        resource: dict[str, Any],
        *,
        name: str,
        url: str,
    ) -> bool:
        resource_type = str(resource.get("resource_type", "")).strip().lower()
        metadata = resource.get("metadata")
        if isinstance(metadata, dict):
            mime_type = str(metadata.get("mime_type", "")).strip().lower()
            if mime_type.startswith("image/"):
                return True

        mime_type = str(resource.get("mime_type", "")).strip().lower()
        if mime_type.startswith("image/"):
            return True

        normalized_name = name.lower()
        normalized_url = url.lower()
        if normalized_name.endswith(self._EMBEDDED_IMAGE_SUFFIXES) or normalized_url.endswith(
            self._EMBEDDED_IMAGE_SUFFIXES
        ):
            return True

        return resource_type == ResourceType.CHART.value and (
            normalized_name.endswith(self._EMBEDDED_CHART_SUFFIXES)
            or normalized_url.endswith(self._EMBEDDED_CHART_SUFFIXES)
        )

    def _update_latest_report_handles(self, session: Session, record: ReportSessionRecord) -> None:
        if not record.markdown_path:
            return
        manager = WorkspaceManager(session.id)
        download_url = manager.build_workspace_file_download_url(record.markdown_path)
        session.documents["latest_report"] = {
            "name": Path(record.markdown_path).name,
            "path": record.markdown_path,
            "type": "report",
            "download_url": download_url,
        }
        session.documents["latest_document"] = dict(session.documents["latest_report"])
        session.artifacts["latest_report"] = {
            "name": Path(record.markdown_path).name,
            "type": "report",
            "path": record.markdown_path,
            "download_url": download_url,
        }

    def _resolve_artifact_ids(
        self,
        manager: WorkspaceManager,
        artifacts: list[dict[str, Any]] | None,
    ) -> list[str]:
        if not isinstance(artifacts, list):
            return []
        files = manager.list_workspace_files_with_paths()
        ids: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path", "")).strip()
            name = str(artifact.get("name", "")).strip()
            for item in files:
                if path and str(item.get("path", "")).strip() == path:
                    ids.append(str(item.get("id", "")))
                    break
                if name and str(item.get("name", "")).strip() == name:
                    ids.append(str(item.get("id", "")))
                    break
        return [item for item in ids if item]
