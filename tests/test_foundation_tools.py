"""基础工具层适配测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.models import ResourceType
from nini.tools.base import SkillResult
from nini.tools.fetch_url import FetchURLSkill
import nini.tools.report_session as report_session_module
from nini.tools.registry import LLM_EXPOSED_BASE_TOOL_NAMES, create_default_registry
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    yield


def test_task_state_init_update_and_query() -> None:
    registry = create_default_registry()
    session = Session()

    init_result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="init",
            tasks=[
                {"id": 1, "title": "加载数据", "status": "pending"},
                {"id": 2, "title": "复盘", "status": "pending"},
            ],
        )
    )
    assert init_result["success"] is True

    update_result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[{"id": 1, "status": "in_progress"}],
        )
    )
    assert update_result["success"] is True

    current_result = asyncio.run(
        registry.execute("task_state", session=session, operation="current")
    )
    assert current_result["success"] is True
    assert current_result["data"]["task"]["title"] == "加载数据"

    all_result = asyncio.run(registry.execute("task_state", session=session, operation="get"))
    assert all_result["success"] is True
    assert len(all_result["data"]["tasks"]) == 2


def test_registry_only_exposes_base_tools_to_llm() -> None:
    registry = create_default_registry()
    definitions = registry.get_tool_definitions()
    names = {tool["function"]["name"] for tool in definitions}

    assert names == LLM_EXPOSED_BASE_TOOL_NAMES
    assert "run_code" not in names
    assert "complete_comparison" not in names


def test_dataset_catalog_lists_and_profiles_datasets() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["demo"] = pd.DataFrame({"group": ["a", "b"], "value": [1.0, 2.0]})

    manager = WorkspaceManager(session.id)
    dataset_path = manager.uploads_dir / "demo.csv"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text("group,value\na,1\nb,2\n", encoding="utf-8")
    manager.add_dataset_record(
        dataset_id="ds_demo",
        name="demo",
        file_path=dataset_path,
        file_type="csv",
        file_size=dataset_path.stat().st_size,
        row_count=2,
        column_count=2,
    )

    list_result = asyncio.run(
        registry.execute("dataset_catalog", session=session, operation="list")
    )
    assert list_result["success"] is True
    listed = list_result["data"]["datasets"]
    assert listed[0]["resource_type"] == "dataset"

    profile_result = asyncio.run(
        registry.execute(
            "dataset_catalog",
            session=session,
            operation="profile",
            dataset_name="demo",
            view="full",
            n_rows=2,
        )
    )
    assert profile_result["success"] is True
    assert profile_result["data"]["resource_id"] == "ds_demo"
    assert "preview" in profile_result["data"]
    assert "summary" in profile_result["data"]
    assert "quality" in profile_result["data"]


def test_dataset_transform_runs_and_supports_step_patch() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["jan"] = pd.DataFrame({"group": ["a", "b"], "value": [1, 2]})
    session.datasets["feb"] = pd.DataFrame({"group": ["a", "b"], "value": [3, 4]})

    run_result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            input_datasets=["jan", "feb"],
            steps=[
                {"id": "concat", "op": "concat_datasets", "params": {"datasets": ["jan", "feb"]}},
                {
                    "id": "derive",
                    "op": "derive_column",
                    "params": {"column": "scaled", "expr": "value * 2"},
                },
                {
                    "id": "agg",
                    "op": "group_aggregate",
                    "params": {"by": ["group"], "metrics": {"scaled": "sum"}},
                },
            ],
            output_dataset_name="agg_result",
        )
    )

    assert run_result["success"] is True, run_result
    assert "agg_result" in session.datasets
    assert session.datasets["agg_result"]["scaled"].tolist() == [8, 12]
    transform_id = run_result["data"]["transform_id"]

    patch_result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="patch_step",
            transform_id=transform_id,
            step_patch={
                "step_id": "derive",
                "params": {"column": "scaled", "expr": "value * 3"},
            },
        )
    )

    assert patch_result["success"] is True, patch_result
    assert session.datasets["agg_result"]["scaled"].tolist() == [12, 18]

    manager = WorkspaceManager(session.id)
    plan = manager.get_resource_summary(transform_id)
    assert plan is not None
    assert plan["source_kind"] == "transforms"


def test_dataset_transform_preview_rows_match_payload() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw"] = pd.DataFrame({"x": list(range(50)), "y": list(range(50))})

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            dataset_name="raw",
            steps=[
                {"id": "derive", "op": "derive_column", "params": {"column": "z", "expr": "x + y"}}
            ],
            output_dataset_name="raw_plus",
        )
    )

    assert result["success"] is True, result
    preview = result["dataframe_preview"]
    assert preview["preview_rows"] == 20
    assert len(preview["data"]) == 20


def test_stat_facade_tools_delegate_existing_statistics() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["stats_demo"] = pd.DataFrame(
        {
            "group": ["a", "a", "a", "b", "b", "b"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    test_result = asyncio.run(
        registry.execute(
            "stat_test",
            session=session,
            method="independent_t",
            dataset_name="stats_demo",
            value_column="value",
            group_column="group",
        )
    )
    assert test_result["success"] is True, test_result
    assert test_result["data"]["requested_method"] == "independent_t"

    model_result = asyncio.run(
        registry.execute(
            "stat_model",
            session=session,
            method="correlation",
            dataset_name="stats_demo",
            columns=["x", "y"],
        )
    )
    assert model_result["success"] is True, model_result
    assert model_result["data"]["requested_method"] == "correlation"

    interpret_result = asyncio.run(
        registry.execute(
            "stat_interpret",
            session=session,
            test_type="t_test",
            result=test_result["data"],
        )
    )
    assert interpret_result["success"] is True, interpret_result
    assert "interpretation" in interpret_result["data"]


def test_stat_model_auto_uses_single_dataset_when_dataset_name_missing() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["stats_demo"] = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    result = asyncio.run(
        registry.execute(
            "stat_model",
            session=session,
            method="correlation",
            columns=["x", "y"],
        )
    )

    assert result["success"] is True, result
    assert result["data"]["requested_method"] == "correlation"


def test_stat_model_accepts_stringified_columns_array() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["stats_demo"] = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    result = asyncio.run(
        registry.execute(
            "stat_model",
            session=session,
            method="correlation",
            dataset_name="stats_demo",
            columns='["x", "y"]',
        )
    )

    assert result["success"] is True, result
    assert result["data"]["requested_method"] == "correlation"


def test_stat_model_requires_dataset_name_when_multiple_datasets_exist() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["a"] = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    session.datasets["b"] = pd.DataFrame({"x": [1, 2, 3], "y": [2, 3, 4]})

    result = asyncio.run(
        registry.execute(
            "stat_model",
            session=session,
            method="correlation",
            columns=["x", "y"],
        )
    )

    assert result["success"] is False
    assert "缺少 dataset_name" in result["message"]


def test_stat_test_auto_uses_single_dataset_when_dataset_name_missing() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["stats_demo"] = pd.DataFrame(
        {
            "group": ["a", "a", "a", "b", "b", "b"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )

    result = asyncio.run(
        registry.execute(
            "stat_test",
            session=session,
            method="independent_t",
            value_column="value",
            group_column="group",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["requested_method"] == "independent_t"


def test_stat_test_requires_dataset_name_when_multiple_datasets_exist() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["a"] = pd.DataFrame({"group": ["g1", "g1", "g2", "g2"], "value": [1, 2, 3, 4]})
    session.datasets["b"] = pd.DataFrame({"group": ["g1", "g1", "g2", "g2"], "value": [2, 3, 4, 5]})

    result = asyncio.run(
        registry.execute(
            "stat_test",
            session=session,
            method="independent_t",
            value_column="value",
            group_column="group",
        )
    )

    assert result["success"] is False
    assert "缺少 dataset_name" in result["message"]


def test_stat_test_returns_friendly_error_for_missing_required_param() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["stats_demo"] = pd.DataFrame(
        {
            "group": ["a", "a", "a", "b", "b", "b"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )

    result = asyncio.run(
        registry.execute(
            "stat_test",
            session=session,
            method="independent_t",
            group_column="group",
        )
    )

    assert result["success"] is False
    assert result["message"] == "缺少必要参数: value_column"


def test_stat_model_schema_explicitly_requires_correlation_dataset_and_columns() -> None:
    registry = create_default_registry()
    skill = registry.get("stat_model")
    assert skill is not None

    schema = skill.parameters
    assert "oneOf" in schema
    branches = schema["oneOf"]
    corr_branch = next(b for b in branches if "correlation" in b["properties"]["method"]["enum"])
    assert set(corr_branch["required"]) == {"method", "dataset_name", "columns"}
    assert corr_branch["properties"]["columns"]["minItems"] == 2


def test_stat_test_schema_explicitly_requires_dataset_and_columns_for_independent_t() -> None:
    registry = create_default_registry()
    skill = registry.get("stat_test")
    assert skill is not None

    schema = skill.parameters
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"method"}
    method_schema = schema["properties"]["method"]
    assert "independent_t" in method_schema["enum"]
    assert "paired_t" in method_schema["enum"]
    assert "dataset_name" in schema["properties"]
    assert "value_column" in schema["properties"]
    assert "group_column" in schema["properties"]


def test_workspace_session_schema_requires_file_path_for_read() -> None:
    registry = create_default_registry()
    skill = registry.get("workspace_session")
    assert skill is not None

    schema = skill.parameters
    assert schema["type"] == "object"
    assert "operation" in schema["properties"]
    assert "read" in schema["properties"]["operation"]["enum"]
    assert "file_path" in schema["properties"]
    assert set(schema["required"]) == {"operation"}


def test_dataset_transform_schema_op_is_strict_enum() -> None:
    registry = create_default_registry()
    skill = registry.get("dataset_transform")
    assert skill is not None

    step_schema = skill.parameters["properties"]["steps"]["items"]["properties"]["op"]
    assert "enum" in step_schema
    assert "dropna" not in step_schema["enum"]
    assert "concat_datasets" in step_schema["enum"]


def test_chart_session_persists_spec_and_tracks_exports() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["trend_demo"] = pd.DataFrame(
        {"month": ["1月", "2月", "3月"], "value": [10, 12, 9]}
    )

    create_result = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="create",
            chart_id="chart_trend_demo",
            dataset_name="trend_demo",
            chart_type="line",
            x_column="month",
            y_column="value",
            title="月度趋势",
            render_engine="plotly",
        )
    )

    assert create_result["success"] is True, create_result
    assert create_result["data"]["resource_id"] == "chart_trend_demo"

    manager = WorkspaceManager(session.id)
    summary = manager.get_resource_summary("chart_trend_demo")
    assert summary is not None
    assert summary["resource_type"] == "chart"
    assert summary["metadata"]["title"] == "月度趋势"

    get_result = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="get",
            chart_id="chart_trend_demo",
        )
    )
    assert get_result["success"] is True, get_result
    assert get_result["data"]["record"]["artifact_ids"]

    export_result = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="export",
            chart_id="chart_trend_demo",
            format="json",
            filename="monthly-trend",
        )
    )
    assert export_result["success"] is True, export_result
    record = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="get",
            chart_id="chart_trend_demo",
        )
    )["data"]["record"]
    assert record["last_export_ids"]


def test_report_session_persists_sections_and_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = create_default_registry()
    session = Session()
    manager = WorkspaceManager(session.id)

    attachment_path = manager.save_text_file("notes/source.md", "# source")
    manager.upsert_managed_resource(
        resource_id="file_source_note",
        resource_type=ResourceType.FILE,
        name="source.md",
        path=attachment_path,
        source_kind="notes",
        metadata={"title": "源文档"},
    )

    chart_path = manager.resolve_workspace_path("artifacts/scatter.plotly.json", allow_missing=True)
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text("{}", encoding="utf-8")
    manager.upsert_managed_resource(
        resource_id="chart_scatter_demo",
        resource_type=ResourceType.CHART,
        name="scatter.plotly.json",
        path=chart_path,
        source_kind="artifacts",
        metadata={"title": "散点图"},
    )

    import base64

    png_path = manager.resolve_workspace_path("artifacts/scatter.png", allow_missing=True)
    png_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGNgYPgPAAEDAQAIicLsAAAABJRU5ErkJggg=="
        )
    )
    manager.upsert_managed_resource(
        resource_id="file_scatter_png",
        resource_type=ResourceType.FILE,
        name="scatter.png",
        path=png_path,
        source_kind="artifacts",
        metadata={"title": "散点图 PNG", "mime_type": "image/png"},
    )

    async def fake_export_workspace_document(
        session: Session,
        source_ref: str | None,
        output_format: str,
        filename: str | None = None,
        prefer_latest_report: bool = False,
    ) -> SkillResult:
        local_manager = WorkspaceManager(session.id)
        relative_path = f"notes/exports/{filename or 'report-export'}.{output_format}"
        target = local_manager.resolve_workspace_path(relative_path, allow_missing=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake export")
        local_manager.sync_text_document_record(relative_path)
        return SkillResult(
            success=True,
            message="导出成功",
            data={
                "filename": target.name,
                "format": output_format,
                "source_path": source_ref or "",
                "output_path": relative_path,
            },
            artifacts=[
                {
                    "name": target.name,
                    "type": f"{output_format}_export",
                    "format": output_format,
                    "path": str(target),
                    "download_url": local_manager.build_workspace_file_download_url(relative_path),
                    "kind": "document",
                }
            ],
        )

    monkeypatch.setattr(
        report_session_module,
        "export_workspace_document",
        fake_export_workspace_document,
    )

    create_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="create",
            report_id="report_demo",
            title="月度分析报告",
            sections=[
                {"key": "summary", "title": "摘要", "content": "初稿摘要"},
                {"key": "conclusion", "title": "结论", "content": "初稿结论"},
            ],
        )
    )
    assert create_result["success"] is True, create_result

    patch_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="patch_section",
            report_id="report_demo",
            section_key="summary",
            mode="append",
            content="\n补充说明。",
        )
    )
    assert patch_result["success"] is True, patch_result

    attach_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="attach_artifact",
            report_id="report_demo",
            section_key="summary",
            artifact_resource_id="file_source_note",
        )
    )
    assert attach_result["success"] is True, attach_result

    chart_attach_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="attach_artifact",
            report_id="report_demo",
            section_key="summary",
            artifact_resource_id="chart_scatter_demo",
        )
    )
    assert chart_attach_result["success"] is True, chart_attach_result

    png_attach_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="attach_artifact",
            report_id="report_demo",
            section_key="summary",
            artifact_resource_id="file_scatter_png",
        )
    )
    assert png_attach_result["success"] is True, png_attach_result

    get_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="get",
            report_id="report_demo",
        )
    )
    assert get_result["success"] is True, get_result
    assert get_result["data"]["resource"]["metadata"]["section_count"] == 2

    markdown_path = manager.resolve_workspace_path(
        get_result["data"]["record"]["markdown_path"],
        allow_missing=False,
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "补充说明" in markdown
    assert "- [source.md](" in markdown
    assert "![scatter.plotly.json](" in markdown
    assert "![scatter.png](" in markdown

    export_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="export",
            report_id="report_demo",
            output_format="docx",
            filename="report-demo-export",
        )
    )
    assert export_result["success"] is True, export_result

    final_record = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="get",
            report_id="report_demo",
        )
    )["data"]["record"]
    assert final_record["export_ids"]


def test_workspace_session_unifies_file_ops_and_fetch_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = create_default_registry()
    session = Session()

    write_result = asyncio.run(
        registry.execute(
            "workspace_session",
            session=session,
            operation="write",
            file_path="notes/summary.md",
            content="# summary",
        )
    )
    assert write_result["success"] is True, write_result

    read_result = asyncio.run(
        registry.execute(
            "workspace_session",
            session=session,
            operation="read",
            file_path="notes/summary.md",
        )
    )
    assert read_result["success"] is True, read_result
    assert "# summary" in read_result["data"]["content"]

    async def fake_fetch(self: FetchURLSkill, session: Session, **kwargs: object) -> SkillResult:
        return SkillResult(
            success=True,
            message="抓取成功",
            data={
                "url": str(kwargs.get("url", "")),
                "content": "# fetched",
                "length": 9,
            },
        )

    monkeypatch.setattr(FetchURLSkill, "execute", fake_fetch)

    fetch_result = asyncio.run(
        registry.execute(
            "workspace_session",
            session=session,
            operation="fetch_url",
            url="https://example.com/demo",
            save_to="notes/fetched.md",
        )
    )
    assert fetch_result["success"] is True, fetch_result
    assert fetch_result["data"]["saved_file"]["path"] == "notes/fetched.md"

    manager = WorkspaceManager(session.id)
    fetched_path = manager.resolve_workspace_path("notes/fetched.md", allow_missing=False)
    assert fetched_path.read_text(encoding="utf-8") == "# fetched"


def test_workspace_session_missing_operation_is_auto_normalized_to_list() -> None:
    registry = create_default_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "workspace_session",
            session=session,
        )
    )

    assert result["success"] is True, result
    metadata = result.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("normalized") is True
    assert "normalization_reason" in metadata


def test_workspace_session_missing_operation_unsafe_inference_is_rejected() -> None:
    registry = create_default_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "workspace_session",
            session=session,
            file_path="notes/a.md",
        )
    )

    assert result["success"] is False
    assert result.get("error_code") == "WORKSPACE_OPERATION_REQUIRED"
    metadata = result.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("normalized") is False


def test_code_session_persists_scripts_and_execution_history() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_demo",
            language="python",
            content=(
                "output_df = df.copy()\n"
                "output_df['double'] = output_df['x'] * 2\n"
                "result = int(output_df['double'].sum())\n"
            ),
        )
    )
    assert create_result["success"] is True, create_result

    get_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="get_script",
            script_id="script_demo",
        )
    )
    assert get_result["success"] is True, get_result
    assert "double" in get_result["data"]["content"]
    assert get_result["data"]["resource"]["resource_type"] == "script"

    run_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="run_script",
            script_id="script_demo",
            dataset_name="raw.csv",
            save_as="double.csv",
            intent="生成翻倍列",
        )
    )
    assert run_result["success"] is True, run_result
    assert "double.csv" in session.datasets
    assert run_result["data"]["execution_id"]

    history_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="get_script",
            script_id="script_demo",
        )
    )
    assert history_result["success"] is True, history_result
    assert len(history_result["data"]["history"]) == 1
    assert history_result["data"]["history"][0]["script_resource_id"] == "script_demo"


def test_code_session_supports_patch_rerun_and_promote_output() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_patch_demo",
            language="python",
            content=(
                "output_df = df.copy()\n"
                "output_df['scaled'] = output_df['x'] * 2\n"
                "result = int(output_df['scaled'].sum())\n"
            ),
        )
    )
    assert create_result["success"] is True, create_result

    patch_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="patch_script",
            script_id="script_patch_demo",
            patch={
                "mode": "replace_string",
                "old_string": "output_df['x'] * 2",
                "new_string": "output_df['x'] * 3",
            },
        )
    )
    assert patch_result["success"] is True, patch_result

    rerun_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="rerun",
            script_id="script_patch_demo",
            dataset_name="raw.csv",
            save_as="scaled.csv",
            intent="重跑修补脚本",
        )
    )
    assert rerun_result["success"] is True, rerun_result
    assert session.datasets["scaled.csv"]["scaled"].tolist() == [3, 6, 9]

    promote_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="promote_output",
            dataset_name="scaled.csv",
            resource_id="ds_scaled_demo",
            resource_name="scaled_output",
        )
    )
    assert promote_result["success"] is True, promote_result
    assert promote_result["data"]["resource_id"] == "ds_scaled_demo"

    manager = WorkspaceManager(session.id)
    promoted = manager.get_resource_summary("ds_scaled_demo")
    assert promoted is not None
    assert promoted["resource_type"] == "dataset"

    script_state = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="get_script",
            script_id="script_patch_demo",
        )
    )
    assert script_state["success"] is True, script_state
    assert len(script_state["data"]["history"]) == 1


def test_code_session_records_failure_location_and_retry_link() -> None:
    registry = create_default_registry()
    session = Session()

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_failure_demo",
            language="python",
            content="result = 1 / 0\n",
        )
    )
    assert create_result["success"] is True, create_result

    failed_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="run_script",
            script_id="script_failure_demo",
            intent="制造失败样例",
        )
    )
    assert failed_result["success"] is False, failed_result
    assert failed_result["data"]["error_location"]["line"] == 1
    assert "重试" in failed_result["data"]["recovery_hint"]

    first_execution_id = failed_result["data"]["execution_id"]
    manager = WorkspaceManager(session.id)
    first_execution = manager.get_code_execution(first_execution_id)
    assert first_execution is not None
    assert first_execution["error_location"]["line"] == 1
    assert first_execution["recovery_hint"]

    patch_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="patch_script",
            script_id="script_failure_demo",
            patch={
                "mode": "replace_string",
                "old_string": "1 / 0",
                "new_string": "1 / 1",
            },
        )
    )
    assert patch_result["success"] is True, patch_result

    rerun_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="rerun",
            script_id="script_failure_demo",
            intent="修复后重跑",
        )
    )
    assert rerun_result["success"] is True, rerun_result
    second_execution = manager.get_code_execution(rerun_result["data"]["execution_id"])
    assert second_execution is not None
    assert second_execution["retry_of_execution_id"] == first_execution_id


def test_code_session_run_script_falls_back_to_ad_hoc_when_content_provided() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="run_script",
            language="python",
            content="result = int(df['x'].sum())",
            dataset_name="raw.csv",
            intent="临时脚本回退执行",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["result"] == 6
    assert result["data"]["script_id"].startswith("script_")


def test_code_session_run_script_auto_uses_single_dataset_when_dataset_name_missing() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["only.csv"] = pd.DataFrame({"x": [2, 4, 6]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_auto_dataset",
            language="python",
            content="result = int(df['x'].sum())",
        )
    )
    assert create_result["success"] is True, create_result

    run_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="run_script",
            script_id="script_auto_dataset",
        )
    )
    assert run_result["success"] is True, run_result
    assert run_result["data"]["result"] == 12
