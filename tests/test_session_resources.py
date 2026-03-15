"""会话资源与执行记录测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.config import settings
from nini.models import ResourceType
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    yield


def test_workspace_manager_initializes_managed_resource_dirs_and_index() -> None:
    manager = WorkspaceManager("session123")
    manager.ensure_dirs()

    assert manager.scripts_dir.exists()
    assert manager.charts_dir.exists()
    assert manager.reports_dir.exists()
    assert manager.transforms_dir.exists()

    manager.list_resource_summaries()
    index = json.loads(manager.index_path.read_text(encoding="utf-8"))
    assert index["version"] == 2
    assert index["resources"] == []


def test_workspace_records_are_registered_as_session_resources() -> None:
    manager = WorkspaceManager("session456")
    manager.ensure_dirs()

    dataset_path = manager.uploads_dir / "demo.csv"
    dataset_path.write_text("a,b\n1,2\n", encoding="utf-8")
    manager.add_dataset_record(
        dataset_id="ds_001",
        name="demo.csv",
        file_path=dataset_path,
        file_type="csv",
        file_size=dataset_path.stat().st_size,
        row_count=1,
        column_count=2,
    )

    artifact_path = manager.artifacts_dir / "trend.html"
    artifact_path.write_text("<html></html>", encoding="utf-8")
    manager.add_artifact_record(
        name="trend.html",
        artifact_type="chart",
        file_path=artifact_path,
        format_hint="html",
    )

    manager.save_text_file("notes/summary.md", "# summary\n")

    resources = manager.list_resource_summaries()
    by_id = {item["id"]: item for item in resources}

    assert by_id["ds_001"]["resource_type"] == ResourceType.DATASET.value
    assert by_id["ds_001"]["source_kind"] == "datasets"
    assert by_id["ds_001"]["metadata"]["row_count"] == 1

    chart_resource = next(item for item in resources if item["name"] == "trend.html")
    assert chart_resource["resource_type"] == ResourceType.CHART.value
    assert chart_resource["source_kind"] == "artifacts"

    note_resource = next(item for item in resources if item["name"] == "summary.md")
    assert note_resource["resource_type"] == ResourceType.FILE.value
    assert note_resource["source_kind"] == "notes"


def test_workspace_supports_temp_dataset_resource_type() -> None:
    manager = WorkspaceManager("session_temp")
    manager.ensure_dirs()

    dataset_path = manager.uploads_dir / "tmp_demo.csv"
    dataset_path.write_text("a\n1\n", encoding="utf-8")
    manager.add_dataset_record(
        dataset_id="tmp_001",
        name="tmp_demo.csv",
        file_path=dataset_path,
        file_type="csv",
        file_size=dataset_path.stat().st_size,
        row_count=1,
        column_count=1,
        resource_type=ResourceType.TEMP_DATASET,
        source_kind="temp_datasets",
        retention="session",
    )

    resource = manager.get_resource_summary("tmp_001")
    assert resource is not None
    assert resource["resource_type"] == ResourceType.TEMP_DATASET.value
    assert resource["source_kind"] == "temp_datasets"
    assert resource["metadata"]["retention"] == "session"


def test_code_execution_record_supports_resource_links_and_recovery_metadata() -> None:
    manager = WorkspaceManager("session789")
    record = manager.save_code_execution(
        code="result = 1 / 0",
        output="ZeroDivisionError",
        status="failed",
        language="python",
        tool_name="code_session",
        script_resource_id="script_001",
        output_resource_ids=["dataset_001"],
        retry_of_execution_id="exec_old",
        recovery_hint="修正除零问题后重跑",
        error_location={"line": 1, "column": 10},
    )

    assert record["script_resource_id"] == "script_001"
    assert record["output_resource_ids"] == ["dataset_001"]
    assert record["retry_of_execution_id"] == "exec_old"
    assert record["recovery_hint"] == "修正除零问题后重跑"
    assert record["error_location"]["line"] == 1

    listed = manager.list_code_executions()
    assert len(listed) == 1
    assert listed[0]["script_resource_id"] == "script_001"
    assert listed[0]["error_location"]["column"] == 10
