"""ExportDocumentSkill 单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nini.agent.session import Session
from nini.tools.export_document import ExportDocumentSkill
from nini.workspace import WorkspaceManager


@pytest.fixture()
def skill() -> ExportDocumentSkill:
    return ExportDocumentSkill()


@pytest.mark.asyncio
async def test_export_document_exports_workspace_markdown_to_pdf(tmp_path: Path, skill: ExportDocumentSkill):
    session = Session()
    sessions_dir = tmp_path / "sessions"

    with patch("nini.tools.export_report.settings") as export_settings, patch(
        "nini.workspace.manager.settings"
    ) as manager_settings:
        export_settings.sessions_dir = sessions_dir
        manager_settings.sessions_dir = sessions_dir
        manager = WorkspaceManager(session.id)
        manager.save_text_file("blood_pressure.md", "# 血压分析\n\n正文\n")

        fake_weasyprint = MagicMock()
        fake_html = MagicMock()
        fake_html.write_pdf.return_value = b"%PDF-1.4 fake"
        fake_weasyprint.HTML.return_value = fake_html

        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            result = await skill.execute(
                session,
                source_path="blood_pressure.md",
                format="pdf",
            )

        assert result.success, result.message
        assert result.data["source_path"] == "blood_pressure.md"
        assert result.data["output_path"] == "blood_pressure.pdf"
        assert result.artifacts[0]["download_url"].endswith(
            f"/api/workspace/{session.id}/files/blood_pressure.pdf"
        )
        files = WorkspaceManager(session.id).list_workspace_files_with_paths()
        exported = next(item for item in files if item["name"] == "blood_pressure.pdf")
        assert exported["kind"] == "document"
        assert exported["meta"]["subtype"] == "pdf_export"


@pytest.mark.asyncio
async def test_export_document_rejects_non_document_source(tmp_path: Path, skill: ExportDocumentSkill):
    session = Session()
    sessions_dir = tmp_path / "sessions"

    with patch("nini.tools.export_report.settings") as export_settings, patch(
        "nini.workspace.manager.settings"
    ) as manager_settings:
        export_settings.sessions_dir = sessions_dir
        manager_settings.sessions_dir = sessions_dir
        manager = WorkspaceManager(session.id)
        chart_path = manager.artifacts_dir / "chart.png"
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        chart_path.write_bytes(b"PNG")
        manager.add_artifact_record(
            name="chart.png",
            artifact_type="chart",
            file_path=chart_path,
            format_hint="png",
        )

        result = await skill.execute(
            session,
            source_path="artifacts/chart.png",
            format="pdf",
        )

        assert not result.success
        assert "可导出的文档" in result.message or "文档" in result.message
