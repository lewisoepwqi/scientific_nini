"""导出产物管线回归测试。"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from nini.agent.session import Session, session_manager
from nini.app import create_app
from nini.config import settings
from nini.models import ChartSessionRecord
from nini.tools.base import ToolResult
from nini.tools.chart_session import ChartSessionTool
from nini.tools.registry import create_default_tool_registry
from nini.workspace import WorkspaceManager
from tests.client_utils import LocalASGIClient


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalASGIClient:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    app = create_app()
    client = LocalASGIClient(app)
    yield client
    client.close()
    session_manager._sessions.clear()


def test_project_artifact_versioning_and_zip_download(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["data"]["session_id"]
    manager = WorkspaceManager(session_id)

    first_path = manager.resolve_workspace_path(
        "artifacts/exports/report_v1.tex", allow_missing=True
    )
    first_path.parent.mkdir(parents=True, exist_ok=True)
    first_path.write_text("first", encoding="utf-8")
    first = manager.register_project_artifact(
        artifact_type="report",
        name="report_v1.tex",
        path=first_path,
        format="tex",
        logical_key="report:demo:tex",
        available_formats=["tex"],
    )

    second_path = manager.resolve_workspace_path(
        "artifacts/exports/report_v2.tex", allow_missing=True
    )
    second_path.parent.mkdir(parents=True, exist_ok=True)
    second_path.write_text("second", encoding="utf-8")
    second = manager.register_project_artifact(
        artifact_type="report",
        name="report_v2.tex",
        path=second_path,
        format="tex",
        logical_key="report:demo:tex",
        available_formats=["tex"],
    )

    artifacts = manager.list_project_artifacts()
    assert [item["version"] for item in artifacts] == [2, 1]

    resp = client.post(
        f"/api/workspace/{session_id}/project-artifacts/download-zip",
        json=[first["id"], second["id"]],
    )
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert re.search(rf"project_artifacts_{session_id[:8]}_\d{{8}}_\d{{6}}\.zip", disposition)

    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        names = set(zf.namelist())
        assert "report_v1.tex" in names
        assert "report_v2.tex" in names


def test_export_job_and_project_artifact_are_idempotent(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["data"]["session_id"]
    manager = WorkspaceManager(session_id)

    first_job = manager.create_export_job(
        target_resource_id="report_demo",
        target_resource_type="report",
        output_format="tex",
        source_task_id="task_demo",
        idempotency_key="job:task_demo:report_demo:tex",
        status="running",
    )
    second_job = manager.create_export_job(
        target_resource_id="report_demo",
        target_resource_type="report",
        output_format="tex",
        source_task_id="task_demo",
        idempotency_key="job:task_demo:report_demo:tex",
        status="running",
    )
    assert first_job["id"] == second_job["id"]
    assert len(manager.list_export_jobs()) == 1

    output_path = manager.resolve_workspace_path(
        "artifacts/exports/report_demo.tex", allow_missing=True
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("demo", encoding="utf-8")

    first_artifact = manager.register_project_artifact(
        artifact_type="report",
        name="report_demo.tex",
        path=output_path,
        format="tex",
        source_task_id="task_demo",
        export_job_id=first_job["id"],
        idempotency_key="artifact:task_demo:report_demo:tex",
        logical_key="report:report_demo:tex",
        available_formats=["tex"],
    )
    second_artifact = manager.register_project_artifact(
        artifact_type="report",
        name="report_demo.tex",
        path=output_path,
        format="tex",
        source_task_id="task_demo",
        export_job_id=first_job["id"],
        idempotency_key="artifact:task_demo:report_demo:tex",
        logical_key="report:report_demo:tex",
        available_formats=["tex"],
    )
    assert first_artifact["id"] == second_artifact["id"]
    assert len(manager.list_project_artifacts()) == 1


@pytest.mark.asyncio
async def test_report_session_tex_export_registers_project_artifact_and_keeps_evidence() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.bind_recipe_context(task_kind="deep_task", recipe_id="literature_review")
    session.set_deep_task_state(task_id="task_report_demo")
    manager = WorkspaceManager(session.id)
    note_path = manager.save_text_file("notes/source.md", "# 来源\n实验组显著提高了指标。")
    manager.upsert_managed_resource(
        resource_id="file_source_note",
        resource_type="file",
        name="source.md",
        path=note_path,
        source_kind="notes",
        metadata={"title": "源文档"},
    )

    create_result = await registry.execute(
        "report_session",
        session=session,
        operation="create",
        report_id="report_export_demo",
        title="导出报告",
        sections=[
            {"key": "methods", "title": "分析方法", "content": "使用 Welch t 检验。"},
            {"key": "conclusion", "title": "结论", "content": "实验组显著提高了指标。"},
        ],
        evidence_blocks=[
            {
                "claim_id": "claim_export_demo",
                "claim_summary": "实验组显著提高了指标。",
                "section_key": "conclusion",
                "sources": [
                    {
                        "source_id": "workspace:file_source_note",
                        "source_type": "file",
                        "title": "source.md",
                        "acquisition_method": "notes",
                        "resource_id": "file_source_note",
                        "excerpt": "实验组显著提高了指标。",
                        "metadata": {"claim_stance": "support"},
                    },
                    {
                        "source_id": "knowledge:demo",
                        "source_type": "knowledge_document",
                        "title": "外部来源",
                        "acquisition_method": "hybrid",
                        "excerpt": "实验组显著提高了指标。",
                        "metadata": {"claim_stance": "support"},
                    },
                ],
            }
        ],
    )
    assert create_result["success"] is True, create_result

    export_result = await registry.execute(
        "report_session",
        session=session,
        operation="export",
        report_id="report_export_demo",
        output_format="tex",
    )
    assert export_result["success"] is True, export_result

    output_path = manager.resolve_workspace_path(
        export_result["data"]["output_path"], allow_missing=False
    )
    assert output_path.as_posix().endswith(".tex")
    tex = output_path.read_text(encoding="utf-8")
    assert "METHODS v1" in tex
    assert "Evidence Block" in tex
    assert "验证状态: 已验证" in tex
    assert "file\\_source\\_note" in tex

    project_artifacts = manager.list_project_artifacts()
    assert len(project_artifacts) == 1
    assert project_artifacts[0]["artifact_type"] == "report"
    assert project_artifacts[0]["format"] == "tex"
    assert project_artifacts[0]["export_job_id"] == export_result["data"]["export_job_id"]
    assert project_artifacts[0]["source_task_id"] == "task_report_demo"

    export_jobs = manager.list_export_jobs()
    assert len(export_jobs) == 1
    assert export_jobs[0]["status"] == "completed"
    assert export_jobs[0]["source_task_id"] == "task_report_demo"

    files = manager.list_workspace_files_with_paths()
    exported = next(item for item in files if item["name"].endswith(".tex"))
    assert exported["kind"] == "result"
    assert exported["meta"]["project_artifact"]["format"] == "tex"


@pytest.mark.asyncio
async def test_chart_export_records_metadata_and_degraded_formats() -> None:
    session = Session()
    session.bind_recipe_context(task_kind="deep_task", recipe_id="results_interpretation")
    session.set_deep_task_state(task_id="task_chart_demo")
    manager = WorkspaceManager(session.id)
    tool = ChartSessionTool()

    record = ChartSessionRecord(
        id="chart_export_demo",
        session_id=session.id,
        dataset_name="demo.csv",
        chart_type="scatter",
        spec={
            "dataset_name": "demo.csv",
            "chart_type": "scatter",
            "title": "散点图",
            "journal_style": "nature",
        },
        render_engine="plotly",
    )
    tool._persist_chart_record(manager, record)

    async def fake_create(*args, **kwargs):
        source_path = manager.artifacts_dir / "chart_export_demo.plotly.json"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("{}", encoding="utf-8")
        manager.add_artifact_record(
            name=source_path.name,
            artifact_type="chart",
            file_path=source_path,
            format_hint="json",
        )
        return ToolResult(
            success=True,
            message="created",
            data={"chart_id": "chart_export_demo"},
            artifacts=[{"name": source_path.name, "path": str(source_path)}],
        )

    async def fake_export(*args, **kwargs):
        export_path = manager.artifacts_dir / "chart_export_demo.html"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text("<html></html>", encoding="utf-8")
        manager.add_artifact_record(
            name=export_path.name,
            artifact_type="chart",
            file_path=export_path,
            format_hint="html",
        )
        return ToolResult(
            success=True,
            message="exported",
            data={"format": "html", "filename": export_path.name},
            artifacts=[{"name": export_path.name, "path": str(export_path)}],
        )

    tool._create.execute = fake_create  # type: ignore[method-assign]
    tool._export.execute = fake_export  # type: ignore[method-assign]

    result = await tool.execute(
        session,
        operation="export",
        chart_id="chart_export_demo",
        format="png",
        width=1280,
        height=720,
        scale=1.5,
    )
    assert result.success, result.message
    assert result.data["successful_formats"] == ["html"]
    assert result.data["failed_formats"] == ["png"]

    refreshed = tool._load_chart_record(session, "chart_export_demo")
    assert refreshed is not None
    assert refreshed.last_export_metadata["style_template"] == "nature"
    assert refreshed.last_export_metadata["successful_formats"] == ["html"]
    assert refreshed.last_export_metadata["failed_formats"] == ["png"]
    assert refreshed.last_export_metadata["resolution"] == {
        "width": 1280,
        "height": 720,
        "scale": 1.5,
    }
    artifacts = manager.list_project_artifacts()
    assert artifacts[0]["source_task_id"] == "task_chart_demo"
    jobs = manager.list_export_jobs()
    assert jobs[0]["source_task_id"] == "task_chart_demo"
    assert jobs[0]["metadata"]["external_attempts"][0]["status"] == "success"

    project_artifacts = manager.list_project_artifacts()
    assert len(project_artifacts) == 1
    assert project_artifacts[0]["artifact_type"] == "chart"
    assert project_artifacts[0]["available_formats"] == ["html"]
    assert project_artifacts[0]["failed_formats"] == ["png"]
    assert project_artifacts[0]["metadata"]["style_template"] == "nature"

    export_jobs = manager.list_export_jobs()
    assert len(export_jobs) == 1
    assert export_jobs[0]["status"] == "completed"
