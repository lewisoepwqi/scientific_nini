"""报告会话基础工具。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.claim_verification import apply_claim_verification
from nini.evidence import normalize_source_record, render_methods_v1, utc_now
from nini.models import (
    ClaimVerificationStatus,
    EvidenceBlock,
    MethodsLedgerEntry,
    ReportSection,
    ReportSessionRecord,
    ResourceType,
    SourceRecord,
)
from nini.tools.base import Tool, ToolResult
from nini.tools.export_report import export_workspace_document
from nini.tools.report import _sanitize_chinese_filename
from nini.workspace import WorkspaceManager


class ReportSessionTool(Tool):
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
        return (
            "创建、更新、查询和导出报告会话资源，章节结构会持久化到受管资源目录。\n"
            "最小示例：\n"
            "- 创建报告：{operation: create, title: 月度分析报告, sections: [{key: summary, title: 摘要}]}\n"
            "- 更新章节：{operation: patch_section, report_id: report_demo, section_key: summary, "
            "mode: append, content: 补充说明}\n"
            "- 绑定资源：{operation: attach_artifact, report_id: report_demo, section_key: summary, "
            "artifact_resource_id: chart_scatter_demo}\n"
            "- 查询报告：{operation: get, report_id: report_demo}\n"
            "- 导出报告：{operation: export, report_id: report_demo, output_format: pdf}\n"
            "参数约束：patch_section 必须提供 report_id 和 section_key；attach_artifact 必须提供 "
            "report_id、section_key、artifact_resource_id；get/export 必须提供 report_id。"
        )

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
                        "additionalProperties": False,
                    },
                },
                "summary_text": {"type": "string"},
                "methods": {"type": "string"},
                "methods_v1": {"type": "string"},
                "methods_entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entry_id": {"type": "string"},
                            "step_name": {"type": "string"},
                            "method_name": {"type": "string"},
                            "tool_name": {"type": "string"},
                            "data_sources": {"type": "array", "items": {"type": "string"}},
                            "key_parameters": {"type": "object"},
                            "model_name": {"type": "string"},
                            "model_version": {"type": "string"},
                            "executed_at": {"type": "string"},
                            "notes": {"type": "string"},
                            "missing_fields": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["step_name", "method_name"],
                        "additionalProperties": False,
                    },
                },
                "conclusions": {"type": "string"},
                "evidence_blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim_id": {"type": "string"},
                            "claim_summary": {"type": "string"},
                            "section_key": {"type": "string"},
                            "sources": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "source_id": {"type": "string"},
                                        "source_type": {"type": "string"},
                                        "title": {"type": "string"},
                                        "acquisition_method": {"type": "string"},
                                        "resource_id": {"type": "string"},
                                        "url": {"type": "string"},
                                        "excerpt": {"type": "string"},
                                        "metadata": {"type": "object"},
                                    },
                                    "required": [
                                        "source_id",
                                        "source_type",
                                        "title",
                                        "acquisition_method",
                                    ],
                                    "additionalProperties": True,
                                },
                            },
                        },
                        "required": ["claim_summary"],
                        "additionalProperties": False,
                    },
                },
                "section_key": {"type": "string"},
                "mode": {"type": "string", "enum": ["replace", "append"]},
                "content": {"type": "string"},
                "artifact_resource_id": {"type": "string"},
                "output_format": {"type": "string", "enum": ["pdf", "docx", "pptx", "tex"]},
                "filename": {"type": "string"},
            },
            "required": ["operation"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"operation": {"const": "create"}},
                    "required": ["operation"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "patch_section"}},
                    "required": ["operation", "report_id", "section_key"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "attach_artifact"}},
                    "required": [
                        "operation",
                        "report_id",
                        "section_key",
                        "artifact_resource_id",
                    ],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "get"}},
                    "required": ["operation", "report_id"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "export"}},
                    "required": ["operation", "report_id"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
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
        return self._input_error(
            operation=operation,
            error_code="REPORT_SESSION_OPERATION_INVALID",
            message=f"不支持的 operation: {operation}",
            expected_fields=["operation"],
            recovery_hint="请将 operation 改为 create、patch_section、attach_artifact、get 或 export。",
            minimal_example='{operation: "create", title: "月度分析报告"}',
        )

    def _create_report(self, session: Session, **kwargs: Any) -> ToolResult:
        report_id = str(kwargs.get("report_id", "")).strip() or f"report_{uuid.uuid4().hex[:12]}"
        title = str(kwargs.get("title", "")).strip() or "科研数据分析报告"
        sections = self._normalize_sections(kwargs)
        record = ReportSessionRecord(
            id=report_id,
            session_id=session.id,
            title=title,
            sections=sections,
            evidence_blocks=self._normalize_evidence_blocks(kwargs, report_id=report_id),
            methods_ledger=self._normalize_methods_ledger(kwargs, sections=sections),
        )
        record.methods_v1 = self._resolve_methods_v1(kwargs, record.methods_ledger)
        apply_claim_verification(record)
        filename = self._normalize_markdown_filename(kwargs.get("filename"))
        if filename:
            record.markdown_path = f"notes/reports/{filename}"
        manager = WorkspaceManager(session.id)
        markdown_rel_path = self._write_report_markdown(manager, record)
        record.markdown_path = markdown_rel_path
        self._persist_report_record(manager, record)
        self._update_latest_report_handles(session, record)
        return ToolResult(
            success=True,
            message=f"报告会话已创建：{report_id}",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
            },
        )

    def _patch_section(self, session: Session, **kwargs: Any) -> ToolResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        if not report_id:
            return self._input_error(
                operation="patch_section",
                error_code="REPORT_SESSION_PATCH_REPORT_ID_REQUIRED",
                message="patch_section 操作必须提供 report_id",
                expected_fields=["operation", "report_id", "section_key"],
                recovery_hint="先传入 report_id 和 section_key，再提供 content 与 mode。",
                minimal_example=self._minimal_example_for_operation("patch_section"),
            )
        record = self._load_report_record(session, report_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到报告会话: {report_id}")
        section_key = str(kwargs.get("section_key", "")).strip()
        if not section_key:
            return self._input_error(
                operation="patch_section",
                error_code="REPORT_SESSION_PATCH_SECTION_KEY_REQUIRED",
                message="patch_section 操作必须提供 section_key",
                expected_fields=["operation", "report_id", "section_key"],
                recovery_hint="section_key 必须指向已有章节键，例如 summary 或 methods。",
                minimal_example=self._minimal_example_for_operation("patch_section"),
            )
        mode = str(kwargs.get("mode", "replace")).strip() or "replace"
        content = str(kwargs.get("content", "") or "")
        matched = False
        for section in record.sections:
            if section.key != section_key:
                continue
            section.content = content if mode == "replace" else section.content + content
            self._refresh_section_claim_summary(record, section)
            matched = True
            break
        if not matched:
            return ToolResult(success=False, message=f"未找到章节: {section_key}")
        if section_key == "methods" and not kwargs.get("methods_v1"):
            record.methods_ledger = self._build_default_methods_ledger(record.sections)
            record.methods_v1 = render_methods_v1(record.methods_ledger)
        apply_claim_verification(record)
        manager = WorkspaceManager(session.id)
        markdown_rel_path = self._write_report_markdown(manager, record)
        record.markdown_path = markdown_rel_path
        self._persist_report_record(manager, record)
        self._update_latest_report_handles(session, record)
        return ToolResult(
            success=True,
            message=f"报告章节已更新：{section_key}",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
            },
        )

    def _attach_artifact(self, session: Session, **kwargs: Any) -> ToolResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        artifact_resource_id = str(kwargs.get("artifact_resource_id", "")).strip()
        section_key = str(kwargs.get("section_key", "")).strip()
        if not report_id or not artifact_resource_id or not section_key:
            return self._input_error(
                operation="attach_artifact",
                error_code="REPORT_SESSION_ATTACH_FIELDS_REQUIRED",
                message="attach_artifact 操作必须提供 report_id、section_key 和 artifact_resource_id",
                expected_fields=[
                    "operation",
                    "report_id",
                    "section_key",
                    "artifact_resource_id",
                ],
                recovery_hint="先提供报告 ID 和目标章节，再指定已存在的 artifact_resource_id。",
                minimal_example=self._minimal_example_for_operation("attach_artifact"),
            )
        record = self._load_report_record(session, report_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到报告会话: {report_id}")
        matched = False
        for section in record.sections:
            if section.key != section_key:
                continue
            if artifact_resource_id not in section.attachments:
                section.attachments.append(artifact_resource_id)
            resource = WorkspaceManager(session.id).get_resource_summary(artifact_resource_id)
            if isinstance(resource, dict):
                self._upsert_section_evidence_source(
                    record,
                    section=section,
                    source=normalize_source_record(resource),
                )
            matched = True
            break
        if not matched:
            return ToolResult(success=False, message=f"未找到章节: {section_key}")
        apply_claim_verification(record)
        manager = WorkspaceManager(session.id)
        markdown_rel_path = self._write_report_markdown(manager, record)
        record.markdown_path = markdown_rel_path
        self._persist_report_record(manager, record)
        self._update_latest_report_handles(session, record)
        return ToolResult(
            success=True,
            message=f"已为章节 '{section_key}' 绑定资源",
            data={
                "report_id": report_id,
                "resource_id": report_id,
                "resource_type": "report",
                "record": record.model_dump(mode="json"),
            },
        )

    def _get_report(self, session: Session, **kwargs: Any) -> ToolResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        if not report_id:
            return self._input_error(
                operation="get",
                error_code="REPORT_SESSION_GET_REPORT_ID_REQUIRED",
                message="get 操作必须提供 report_id",
                expected_fields=["operation", "report_id"],
                recovery_hint="先传入要读取的报告会话 report_id。",
                minimal_example=self._minimal_example_for_operation("get"),
            )
        record = self._load_report_record(session, report_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到报告会话: {report_id}")
        manager = WorkspaceManager(session.id)
        return ToolResult(
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

    async def _export_report(self, session: Session, **kwargs: Any) -> ToolResult:
        report_id = str(kwargs.get("report_id", "")).strip()
        if not report_id:
            return self._input_error(
                operation="export",
                error_code="REPORT_SESSION_EXPORT_REPORT_ID_REQUIRED",
                message="export 操作必须提供 report_id",
                expected_fields=["operation", "report_id"],
                recovery_hint="先传入已存在的 report_id，再指定 output_format。",
                minimal_example=self._minimal_example_for_operation("export"),
            )
        record = self._load_report_record(session, report_id)
        if record is None or not record.markdown_path:
            return ToolResult(success=False, message=f"未找到可导出的报告会话: {report_id}")
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
        return ToolResult(**payload)

    def _normalize_sections(self, kwargs: dict[str, Any]) -> list[ReportSection]:
        raw_sections = kwargs.get("sections")
        if isinstance(raw_sections, list) and raw_sections:
            return [
                ReportSection.model_validate(item)
                for item in raw_sections
                if isinstance(item, dict)
            ]

        sections: list[ReportSection] = []
        methods = str(kwargs.get("methods", "") or "").strip()
        summary_text = str(kwargs.get("summary_text", "") or "").strip()
        conclusions = str(kwargs.get("conclusions", "") or "").strip()
        if methods:
            sections.append(ReportSection(key="methods", title="分析方法", content=methods))
        if summary_text:
            sections.append(ReportSection(key="summary", title="分析摘要", content=summary_text))
        if conclusions:
            sections.append(
                ReportSection(key="conclusions", title="结论与建议", content=conclusions)
            )
        if not sections:
            sections.append(ReportSection(key="summary", title="分析摘要", content=""))
        return sections

    def _normalize_evidence_blocks(
        self,
        kwargs: dict[str, Any],
        *,
        report_id: str,
    ) -> list[EvidenceBlock]:
        raw_blocks = kwargs.get("evidence_blocks")
        if not isinstance(raw_blocks, list):
            return []

        normalized: list[EvidenceBlock] = []
        for index, item in enumerate(raw_blocks, 1):
            if not isinstance(item, dict):
                continue
            claim_id = str(item.get("claim_id", "")).strip() or f"{report_id}:claim_{index}"
            claim_summary = str(item.get("claim_summary", "")).strip()
            if not claim_summary:
                continue
            raw_sources = item.get("sources")
            sources = (
                [
                    normalize_source_record(source)
                    for source in raw_sources
                    if isinstance(source, dict)
                ]
                if isinstance(raw_sources, list)
                else []
            )
            normalized.append(
                EvidenceBlock(
                    claim_id=claim_id,
                    claim_summary=claim_summary,
                    section_key=str(item.get("section_key", "")).strip() or None,
                    sources=sources,
                )
            )
        return normalized

    def _normalize_methods_ledger(
        self,
        kwargs: dict[str, Any],
        *,
        sections: list[ReportSection],
    ) -> list[MethodsLedgerEntry]:
        raw_entries = kwargs.get("methods_entries")
        if isinstance(raw_entries, list) and raw_entries:
            return [
                MethodsLedgerEntry.model_validate(item)
                for item in raw_entries
                if isinstance(item, dict)
            ]
        return self._build_default_methods_ledger(sections)

    def _build_default_methods_ledger(
        self,
        sections: list[ReportSection],
    ) -> list[MethodsLedgerEntry]:
        methods_section = next((section for section in sections if section.key == "methods"), None)
        if methods_section is None or not methods_section.content.strip():
            return []
        return [
            MethodsLedgerEntry(
                entry_id="methods_v1_seed",
                step_name="方法说明整理",
                method_name="报告方法摘要整理",
                tool_name="report_session",
                data_sources=[],
                key_parameters={},
                executed_at=utc_now(),
                notes=methods_section.content.strip(),
                missing_fields=["data_sources", "model_version"],
            )
        ]

    def _resolve_methods_v1(
        self,
        kwargs: dict[str, Any],
        methods_ledger: list[MethodsLedgerEntry],
    ) -> str:
        explicit = str(kwargs.get("methods_v1", "") or "").strip()
        if explicit:
            return explicit
        return render_methods_v1(methods_ledger)

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

    def _persist_report_record(
        self, manager: WorkspaceManager, record: ReportSessionRecord
    ) -> None:
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
                "claim_ids": [block.claim_id for block in record.evidence_blocks],
                "evidence_count": len(record.evidence_blocks),
                "verification_counts": {
                    "verified": len(
                        [
                            block
                            for block in record.evidence_blocks
                            if block.verification_status == ClaimVerificationStatus.VERIFIED
                        ]
                    ),
                    "pending_verification": len(
                        [
                            block
                            for block in record.evidence_blocks
                            if block.verification_status
                            == ClaimVerificationStatus.PENDING_VERIFICATION
                        ]
                    ),
                    "conflicted": len(
                        [
                            block
                            for block in record.evidence_blocks
                            if block.verification_status == ClaimVerificationStatus.CONFLICTED
                        ]
                    ),
                },
                "methods_entry_count": len(record.methods_ledger),
                "methods_v1": record.methods_v1,
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
            section_content = section.content or ""
            if section.key == "summary" and record.evidence_blocks:
                section_content = "以下摘要仅纳入已验证结论。"
            lines.append(section_content)
            if section.key == "methods" and record.methods_v1:
                lines.append("")
                lines.append(record.methods_v1)
            if section.key == "summary":
                lines.extend(self._verified_summary_lines(record))
            section_evidence = [
                block for block in record.evidence_blocks if block.section_key == section.key
            ]
            if section_evidence:
                for block in section_evidence:
                    lines.extend(self._evidence_markdown_lines(block))
            if section.attachments:
                lines.append("")
                lines.append("### 关联资源")
                for resource_id in section.attachments:
                    lines.extend(self._resource_markdown_lines(manager, resource_id))
            lines.append("")
        lines.extend(self._verification_appendix_lines(record))
        manager.save_text_file(rel_path, "\n".join(lines).strip() + "\n")
        return rel_path

    def _evidence_markdown_lines(self, block: EvidenceBlock) -> list[str]:
        lines = [
            "",
            "### Evidence Block",
            f"- claim_id: `{block.claim_id}`",
            f"- 结论摘要: {block.claim_summary}",
            f"- 验证状态: {self._status_label(block.verification_status)}",
            f"- 置信度: {block.confidence_score:.2f}",
        ]
        if block.reason_summary:
            lines.append(f"- 原因摘要: {block.reason_summary}")
        if block.conflict_summary:
            lines.append(f"- 冲突摘要: {block.conflict_summary}")
        if not block.sources:
            lines.append("- 来源: 未记录")
            lines.append("")
            return lines
        lines.append("- 来源列表:")
        for source in block.sources:
            lines.append(f"  - {self._format_source_line(source)}")
        lines.append("")
        return lines

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

    def _upsert_section_evidence_source(
        self,
        record: ReportSessionRecord,
        *,
        section: ReportSection,
        source: SourceRecord,
    ) -> None:
        claim_id = f"{record.id}:{section.key}"
        claim_summary = self._summarize_claim(section)
        block = next(
            (
                item
                for item in record.evidence_blocks
                if item.claim_id == claim_id or item.section_key == section.key
            ),
            None,
        )
        if block is None:
            block = EvidenceBlock(
                claim_id=claim_id,
                claim_summary=claim_summary,
                section_key=section.key,
                sources=[],
            )
            record.evidence_blocks.append(block)
        else:
            block.claim_summary = claim_summary
            block.section_key = section.key
        if not any(item.source_id == source.source_id for item in block.sources):
            block.sources.append(source)

    def _refresh_section_claim_summary(
        self,
        record: ReportSessionRecord,
        section: ReportSection,
    ) -> None:
        claim_id = f"{record.id}:{section.key}"
        for block in record.evidence_blocks:
            if block.claim_id == claim_id or block.section_key == section.key:
                block.claim_summary = self._summarize_claim(section)
                block.section_key = section.key

    def _summarize_claim(self, section: ReportSection) -> str:
        content = str(section.content or "").strip()
        if not content:
            return section.title
        compact = " ".join(line.strip() for line in content.splitlines() if line.strip())
        return compact[:160] + ("..." if len(compact) > 160 else "")

    def _format_source_line(self, source: SourceRecord) -> str:
        parts = [source.title, f"[{source.source_type}]"]
        if source.acquisition_method:
            parts.append(f"获取方式: {source.acquisition_method}")
        if source.source_time is not None:
            parts.append(f"来源时间: {source.source_time.isoformat()}")
        if source.accessed_at is not None:
            parts.append(f"获取时间: {source.accessed_at.isoformat()}")
        parts.append(f"source_id: {source.source_id}")
        return "；".join(parts)

    def _verified_summary_lines(self, record: ReportSessionRecord) -> list[str]:
        verified_blocks = [
            block
            for block in record.evidence_blocks
            if block.verification_status == ClaimVerificationStatus.VERIFIED
        ]
        lines = ["", "### 已验证结论摘要"]
        if not verified_blocks:
            lines.append("- 当前没有可写入最终摘要的已验证结论。")
            lines.append("")
            return lines
        for block in verified_blocks:
            lines.append(f"- {block.claim_summary}（置信度 {block.confidence_score:.2f}）")
        lines.append("")
        return lines

    def _verification_appendix_lines(self, record: ReportSessionRecord) -> list[str]:
        pending_blocks = [
            block
            for block in record.evidence_blocks
            if block.verification_status == ClaimVerificationStatus.PENDING_VERIFICATION
        ]
        conflicted_blocks = [
            block
            for block in record.evidence_blocks
            if block.verification_status == ClaimVerificationStatus.CONFLICTED
        ]
        lines: list[str] = []
        if pending_blocks:
            lines.extend(["## 待验证结论", ""])
            for block in pending_blocks:
                lines.append(
                    f"- {block.claim_summary}：{block.reason_summary or '尚缺少足够证据。'}"
                )
            lines.append("")
        if conflicted_blocks:
            lines.extend(["## 证据冲突结论", ""])
            for block in conflicted_blocks:
                reason = block.conflict_summary or block.reason_summary or "存在冲突来源。"
                lines.append(f"- {block.claim_summary}：{reason}")
            lines.append("")
        return lines

    def _status_label(self, status: ClaimVerificationStatus | str) -> str:
        if status == ClaimVerificationStatus.VERIFIED:
            return "已验证"
        if status == ClaimVerificationStatus.CONFLICTED:
            return "证据冲突"
        return "待验证"

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
            "create": '{operation: "create", title: "月度分析报告"}',
            "patch_section": (
                '{operation: "patch_section", report_id: "report_demo", '
                'section_key: "summary", mode: "append", content: "补充说明"}'
            ),
            "attach_artifact": (
                '{operation: "attach_artifact", report_id: "report_demo", '
                'section_key: "summary", artifact_resource_id: "chart_scatter_demo"}'
            ),
            "get": '{operation: "get", report_id: "report_demo"}',
            "export": '{operation: "export", report_id: "report_demo", output_format: "pdf"}',
        }
        return examples.get(operation, '{operation: "create", title: "月度分析报告"}')
