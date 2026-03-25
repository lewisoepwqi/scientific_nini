"""证据链与 METHODS 台账回归测试。"""

from __future__ import annotations

import asyncio

from nini.agent.session import Session
from nini.evidence import normalize_source_record
from nini.models import ResourceType
from nini.models.knowledge import KnowledgeDocument
from nini.tools.registry import create_default_tool_registry
from nini.workspace import WorkspaceManager


def test_normalize_source_record_supports_knowledge_and_workspace_sources() -> None:
    knowledge_source = normalize_source_record(
        KnowledgeDocument(
            id="doc-ttest",
            title="t 检验方法",
            content="t 检验用于比较均值。",
            excerpt="t 检验用于比较均值。",
            relevance_score=0.91,
            source_method="hybrid",
            metadata={"url": "https://example.com/ttest"},
        )
    )
    assert knowledge_source.source_id == "knowledge:doc-ttest"
    assert knowledge_source.source_type == "knowledge_document"
    assert knowledge_source.acquisition_method == "hybrid"
    assert knowledge_source.document_id == "doc-ttest"

    workspace_source = normalize_source_record(
        {
            "id": "report_note_1",
            "resource_type": "file",
            "name": "summary.md",
            "source_kind": "notes",
            "created_at": "2026-03-26T12:00:00+00:00",
        }
    )
    assert workspace_source.source_id == "workspace:report_note_1"
    assert workspace_source.source_type == "file"
    assert workspace_source.acquisition_method == "notes"
    assert workspace_source.resource_id == "report_note_1"


def test_report_session_records_evidence_block_and_methods_v1() -> None:
    registry = create_default_tool_registry()
    session = Session()
    manager = WorkspaceManager(session.id)

    note_path = manager.save_text_file("notes/source.md", "# source")
    manager.upsert_managed_resource(
        resource_id="file_source_note",
        resource_type=ResourceType.FILE,
        name="source.md",
        path=note_path,
        source_kind="notes",
        metadata={"title": "源文档"},
    )

    create_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="create",
            report_id="report_trace_demo",
            title="证据链报告",
            sections=[
                {
                    "key": "methods",
                    "title": "分析方法",
                    "content": "使用 Welch t 检验，alpha=0.05。",
                },
                {"key": "conclusions", "title": "结论", "content": "实验组均值显著高于对照组。"},
            ],
        )
    )
    assert create_result["success"] is True, create_result

    attach_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="attach_artifact",
            report_id="report_trace_demo",
            section_key="conclusions",
            artifact_resource_id="file_source_note",
        )
    )
    assert attach_result["success"] is True, attach_result

    get_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="get",
            report_id="report_trace_demo",
        )
    )
    record = get_result["data"]["record"]
    assert record["methods_v1"]
    assert record["methods_ledger"][0]["step_name"] == "方法说明整理"
    assert record["evidence_blocks"][0]["claim_id"] == "report_trace_demo:conclusions"
    assert record["evidence_blocks"][0]["sources"][0]["source_id"] == "workspace:file_source_note"

    markdown_path = manager.resolve_workspace_path(record["markdown_path"], allow_missing=False)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "### METHODS v1" in markdown
    assert "### Evidence Block" in markdown
    assert "workspace:file_source_note" in markdown
