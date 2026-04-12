"""基础工具层适配测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.models import ResourceType
from nini.tools.base import ToolResult
from nini.tools.fetch_url import FetchURLTool
import nini.tools.report_session as report_session_module
from nini.tools.registry import LLM_EXPOSED_BASE_TOOL_NAMES, create_default_tool_registry
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    yield


def test_task_state_init_update_and_query() -> None:
    registry = create_default_tool_registry()
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
    assert init_result["data"]["pending_count"] == 2
    assert init_result["data"]["tasks"][0]["status"] == "pending"

    # 显式启动任务1
    start_result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[{"id": 1, "status": "in_progress"}],
        )
    )
    assert start_result["success"] is True

    # 显式完成任务1，并启动任务2
    update_result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[
                {"id": 1, "status": "completed"},
                {"id": 2, "status": "in_progress"},
            ],
        )
    )
    assert update_result["success"] is True

    current_result = asyncio.run(
        registry.execute("task_state", session=session, operation="current")
    )
    assert current_result["success"] is True
    assert current_result["data"]["task"]["title"] == "复盘"

    all_result = asyncio.run(registry.execute("task_state", session=session, operation="get"))
    assert all_result["success"] is True
    assert len(all_result["data"]["tasks"]) == 2


def test_task_state_update_no_op_returns_different_message() -> None:
    """重复设置相同状态时，应返回明确的"无需重复"消息。"""
    registry = create_default_tool_registry()
    session = Session()

    # 初始化任务列表；使用 3 个任务以确保推进到任务2时还有 pending 任务
    asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="init",
            tasks=[
                {"id": 1, "title": "数据清洗", "status": "pending"},
                {"id": 2, "title": "统计分析", "status": "pending"},
                {"id": 3, "title": "结果汇总", "status": "pending"},
            ],
        )
    )

    asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[{"id": 1, "status": "in_progress"}],
        )
    )

    # 推进到任务2 — 应返回正常消息（任务1 已显式完成，任务3 仍 pending）
    result1 = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[
                {"id": 1, "status": "completed"},
                {"id": 2, "status": "in_progress"},
            ],
        )
    )
    assert result1["success"] is True
    assert "已标记为进行中" in result1["message"] or "执行中" in result1["message"]
    # 首次推进不应是 no_op
    assert not result1["data"].get("no_op_ids")

    # 重复设置任务2 in_progress — 应返回差异化"已处于请求的状态"消息
    result2 = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[{"id": 2, "status": "in_progress"}],
        )
    )
    assert result2["success"] is True
    assert "已处于请求的状态" in result2["message"]
    assert result2["data"]["no_op_ids"] == [2]


def test_task_state_init_does_not_auto_start_first_task() -> None:
    """init 只声明任务，不应隐式推进首任务状态。"""
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="init",
            tasks=[
                {"id": 1, "title": "数据清洗", "status": "pending", "tool_hint": "dataset_catalog"},
                {"id": 2, "title": "统计分析", "status": "pending"},
                {"id": 3, "title": "复盘", "status": "pending"},
            ],
        )
    )
    assert result["success"] is True
    assert result["data"]["tasks"][0]["status"] == "pending"
    assert result["data"]["pending_count"] == 3
    assert "已自动开始" not in result["message"]
    # 应返回简洁的声明消息，包含建议从哪个任务开始
    assert "已声明" in result["message"]


def test_task_state_update_mixed_noop_and_change_reports_both() -> None:
    """no-op 与实际变更同时出现时，消息应同时报告两者。"""
    registry = create_default_tool_registry()
    session = Session()

    asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="init",
            tasks=[
                {"id": 1, "title": "数据清洗", "status": "pending"},
                {"id": 2, "title": "统计分析", "status": "pending"},
                {"id": 3, "title": "复盘", "status": "pending"},
            ],
        )
    )

    asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[{"id": 1, "status": "in_progress"}],
        )
    )

    # 批量更新：任务1 → in_progress (no-op) + 任务2 → in_progress (实际变更)
    result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[
                {"id": 1, "status": "in_progress"},
                {"id": 2, "status": "in_progress"},
            ],
        )
    )
    assert result["success"] is True
    assert "已处于请求的状态" in result["message"]
    # 应同时报告实际变更
    assert "同时已更新" in result["message"]
    assert 1 in result["data"]["no_op_ids"]


def test_task_state_update_before_init_returns_clear_error() -> None:
    """未初始化时 update 不应隐式创建任务列表。"""
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="update",
            tasks=[{"id": 1, "status": "in_progress"}],
        )
    )
    assert result["success"] is False
    assert "尚未初始化" in result["message"]


def test_task_state_init_normalizes_non_pending_status() -> None:
    """init 误传非 pending 初始状态时应自动归一化，而不是阻塞失败。"""
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="init",
            tasks=[
                {"id": 1, "title": "数据质量审查", "status": "in_progress"},
                {"id": 2, "title": "统计分析", "status": "pending"},
            ],
        )
    )

    assert result["success"] is True
    assert "归一化为 pending" in result["message"]
    assert result["data"]["normalized_task_ids"] == [1]
    assert [task["status"] for task in result["data"]["tasks"]] == ["pending", "pending"]
    assert session.task_manager.tasks[0].status == "pending"


def test_task_state_schema_uses_operation_level_oneof() -> None:
    registry = create_default_tool_registry()
    schema = registry.get("task_state").parameters

    assert set(schema["required"]) == {"operation"}
    assert schema["additionalProperties"] is False
    assert {"operation", "tasks"}.issubset(set(schema["properties"]))
    assert schema["properties"]["operation"]["enum"] == ["init", "update", "get", "current"]

    branch_map = {branch["properties"]["operation"]["const"]: branch for branch in schema["oneOf"]}
    branches = {name: set(branch["required"]) for name, branch in branch_map.items()}
    assert branches["init"] == {"operation", "tasks"}
    assert branches["update"] == {"operation", "tasks"}
    assert branches["get"] == {"operation"}
    assert branches["current"] == {"operation"}

    init_task_item = branch_map["init"]["properties"]["tasks"]["items"]
    update_task_item = branch_map["update"]["properties"]["tasks"]["items"]
    assert init_task_item["additionalProperties"] is False
    assert init_task_item["required"] == ["id", "title", "status"]
    assert init_task_item["properties"]["status"]["enum"] == ["pending"]
    assert update_task_item["additionalProperties"] is False
    assert update_task_item["required"] == ["id", "status"]
    assert "in_progress" in update_task_item["properties"]["status"]["enum"]


def test_task_state_empty_operation_returns_structured_error() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(registry.execute("task_state", session=session))

    assert result["success"] is False
    assert result["data"]["error_code"] == "TASK_STATE_OPERATION_REQUIRED"
    assert result["data"]["expected_fields"] == ["operation"]
    assert "缺少 operation" in result["message"]


def test_task_write_schema_uses_mode_level_oneof_and_init_pending_only() -> None:
    registry = create_default_tool_registry()
    schema = registry.get("task_write").parameters

    assert set(schema["required"]) == {"mode", "tasks"}
    assert schema["additionalProperties"] is False
    assert {"mode", "tasks"}.issubset(set(schema["properties"]))
    assert schema["properties"]["mode"]["enum"] == ["init", "update"]

    branch_map = {branch["properties"]["mode"]["const"]: branch for branch in schema["oneOf"]}
    init_task_item = branch_map["init"]["properties"]["tasks"]["items"]
    update_task_item = branch_map["update"]["properties"]["tasks"]["items"]

    assert init_task_item["required"] == ["id", "title", "status"]
    assert init_task_item["properties"]["status"]["enum"] == ["pending"]
    assert update_task_item["required"] == ["id", "status"]
    assert "completed" in update_task_item["properties"]["status"]["enum"]


def test_task_write_init_normalizes_non_pending_status() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "task_write",
            session=session,
            mode="init",
            tasks=[
                {"id": 1, "title": "澄清问题", "status": "in_progress"},
                {"id": 2, "title": "执行分析", "status": "pending"},
            ],
        )
    )

    assert result["success"] is True
    assert result["data"]["normalized_task_ids"] == [1]
    assert [task["status"] for task in result["data"]["tasks"]] == ["pending", "pending"]


def test_task_write_empty_payload_returns_structured_error() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(registry.execute("task_write", session=session))

    assert result["success"] is False
    assert result["data"]["error_code"] == "TASK_WRITE_MODE_REQUIRED"
    assert result["data"]["expected_fields"] == ["mode", "tasks"]


def test_task_state_missing_tasks_returns_structured_error() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "task_state",
            session=session,
            operation="init",
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "TASK_STATE_TASKS_REQUIRED"
    assert result["data"]["expected_fields"] == ["operation", "tasks"]
    assert "tasks" in result["data"]["minimal_example"]


def test_registry_only_exposes_base_tools_to_llm() -> None:
    registry = create_default_tool_registry()
    definitions = registry.get_tool_definitions()
    names = {tool["function"]["name"] for tool in definitions}

    assert names == LLM_EXPOSED_BASE_TOOL_NAMES
    assert "run_code" not in names
    assert "complete_comparison" not in names


def test_llm_facing_tool_contracts_include_examples_and_discriminators() -> None:
    registry = create_default_tool_registry()
    expectations = {
        "search_tools": False,
        "dataset_transform": True,
        "workspace_session": True,
        "dataset_catalog": True,
        "chart_session": True,
        "report_session": True,
        "code_session": True,
        "task_state": True,
        "stat_test": True,
        "stat_model": False,
    }

    for tool_name, expects_oneof in expectations.items():
        tool = registry.get(tool_name)
        assert tool is not None
        description = str(tool.description)
        schema = tool.parameters

        assert "最小示例" in description
        if expects_oneof:
            assert "oneOf" in schema
            assert schema["additionalProperties"] is False
        else:
            assert "oneOf" not in schema


def test_structured_input_errors_share_standard_payload_shape() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["stats_demo"] = pd.DataFrame(
        {
            "group": ["a", "a", "b", "b"],
            "value": [1.0, 2.0, 3.0, 4.0],
            "x": [1, 2, 3, 4],
            "y": [2, 4, 6, 8],
        }
    )

    cases = [
        ("dataset_catalog", {"operation": "load"}),
        ("chart_session", {"operation": "export"}),
        ("report_session", {"operation": "export"}),
        ("code_session", {"operation": "get_script"}),
        ("task_state", {"operation": "init"}),
        ("search_tools", {"query": "   "}),
        ("stat_test", {"method": "independent_t", "group_column": "group"}),
        (
            "stat_model",
            {"method": "linear_regression", "dataset_name": "stats_demo", "dependent_var": "y"},
        ),
    ]

    for tool_name, kwargs in cases:
        result = asyncio.run(registry.execute(tool_name, session=session, **kwargs))
        assert result["success"] is False
        assert "data" in result
        payload = result["data"]
        for key in ("error_code", "expected_fields", "recovery_hint", "minimal_example"):
            assert key in payload, (tool_name, payload)


def test_dataset_catalog_lists_and_profiles_datasets() -> None:
    registry = create_default_tool_registry()
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


def test_dataset_catalog_schema_uses_operation_level_oneof() -> None:
    registry = create_default_tool_registry()
    schema = registry.get("dataset_catalog").parameters

    assert set(schema["required"]) == {"operation"}
    assert schema["additionalProperties"] is False

    branches = {
        branch["properties"]["operation"]["const"]: set(branch["required"])
        for branch in schema["oneOf"]
    }
    assert branches["list"] == {"operation"}
    assert branches["load"] == {"operation", "dataset_name"}
    assert branches["profile"] == {"operation", "dataset_name"}


def test_dataset_catalog_missing_required_args_returns_expected_fields_and_example() -> None:
    registry = create_default_tool_registry()
    session = Session()

    load_result = asyncio.run(
        registry.execute(
            "dataset_catalog",
            session=session,
            operation="load",
        )
    )
    assert load_result["success"] is False
    assert load_result["data"]["error_code"] == "DATASET_CATALOG_LOAD_DATASET_NAME_REQUIRED"
    assert load_result["data"]["expected_fields"] == ["operation", "dataset_name"]
    assert "dataset_name" in load_result["data"]["minimal_example"]

    profile_result = asyncio.run(
        registry.execute(
            "dataset_catalog",
            session=session,
            operation="profile",
            view="full",
        )
    )
    assert profile_result["success"] is False
    assert profile_result["data"]["error_code"] == "DATASET_CATALOG_PROFILE_DATASET_NAME_REQUIRED"
    assert profile_result["data"]["expected_fields"] == ["operation", "dataset_name"]


def test_dataset_transform_runs_and_supports_step_patch() -> None:
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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


def test_stat_model_returns_structured_error_for_missing_required_param() -> None:
    registry = create_default_tool_registry()
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
            method="linear_regression",
            dataset_name="stats_demo",
            dependent_var="y",
        )
    )

    assert result["success"] is False
    assert result["message"] == "缺少必要参数: independent_vars"
    assert result["data"]["error_code"] == "STAT_MODEL_REQUIRED_PARAM_MISSING"
    assert result["data"]["expected_fields"] == [
        "method",
        "dependent_var",
        "independent_vars",
    ]


def test_stat_test_auto_uses_single_dataset_when_dataset_name_missing() -> None:
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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
    assert result["data"]["error_code"] == "STAT_TEST_REQUIRED_PARAM_MISSING"
    assert result["data"]["expected_fields"] == ["method", "value_column", "group_column"]


def test_stat_model_schema_explicitly_requires_correlation_dataset_and_columns() -> None:
    """stat_model 使用扁平 schema（非 oneOf），method 为唯一 required 字段。"""
    registry = create_default_tool_registry()
    skill = registry.get("stat_model")
    assert skill is not None

    schema = skill.parameters
    # 扁平 schema：不使用 oneOf，避免模型并行调用时参数丢失
    assert "oneOf" not in schema
    assert schema["type"] == "object"
    assert schema["required"] == ["method"]
    props = schema["properties"]
    assert "correlation" in props["method"]["enum"]
    assert "columns" in props
    assert "dependent_var" in props
    assert "independent_vars" in props


def test_stat_test_schema_explicitly_requires_dataset_and_columns_for_independent_t() -> None:
    registry = create_default_tool_registry()
    skill = registry.get("stat_test")
    assert skill is not None

    schema = skill.parameters
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"method"}
    assert schema["additionalProperties"] is False
    assert "oneOf" in schema
    method_schema = schema["properties"]["method"]
    assert "independent_t" in method_schema["enum"]
    assert "paired_t" in method_schema["enum"]
    assert "dataset_name" in schema["properties"]
    assert "value_column" in schema["properties"]
    assert "group_column" in schema["properties"]
    assert "correction_method" in schema["properties"]

    branches = {
        branch["properties"]["method"]["const"]: set(branch["required"])
        for branch in schema["oneOf"]
    }
    assert branches["independent_t"] == {"method", "value_column", "group_column"}
    assert branches["one_sample_t"] == {"method", "value_column", "test_value"}
    assert branches["multiple_comparison_correction"] == {"method", "p_values"}


def test_stat_test_multiple_comparison_supports_correction_method() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "stat_test",
            session=session,
            method="multiple_comparison_correction",
            p_values=[0.01, 0.02, 0.2],
            correction_method="holm",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["requested_method"] == "multiple_comparison_correction"
    assert result["data"]["method"] == "Holm"


def test_workspace_session_schema_requires_file_path_for_read() -> None:
    registry = create_default_tool_registry()
    skill = registry.get("workspace_session")
    assert skill is not None

    schema = skill.parameters
    assert schema["type"] == "object"
    assert "operation" in schema["properties"]
    assert "read" in schema["properties"]["operation"]["enum"]
    assert "file_path" in schema["properties"]
    assert set(schema["required"]) == {"operation"}
    assert "oneOf" in schema

    read_branch = next(
        item for item in schema["oneOf"] if item["properties"]["operation"]["const"] == "read"
    )
    assert set(read_branch["required"]) == {"operation", "file_path"}

    write_branch = next(
        item for item in schema["oneOf"] if item["properties"]["operation"]["const"] == "write"
    )
    assert set(write_branch["required"]) == {"operation", "file_path", "content"}


def test_dataset_transform_schema_op_is_strict_enum() -> None:
    registry = create_default_tool_registry()
    skill = registry.get("dataset_transform")
    assert skill is not None

    step_schema = skill.parameters["properties"]["steps"]["items"]["properties"]["op"]
    assert "enum" in step_schema
    assert "dropna" not in step_schema["enum"]
    assert "concat_datasets" in step_schema["enum"]


def test_dataset_transform_schema_uses_operation_and_step_level_oneof() -> None:
    registry = create_default_tool_registry()
    skill = registry.get("dataset_transform")
    assert skill is not None

    schema = skill.parameters
    assert schema["required"] == ["operation"]
    assert "oneOf" in schema

    step_items = schema["properties"]["steps"]["items"]
    assert "oneOf" in step_items
    derive_variant = next(
        item for item in step_items["oneOf"] if item["properties"]["op"]["const"] == "derive_column"
    )
    assert derive_variant["properties"]["params"]["required"] == ["column", "expr"]


def test_dataset_transform_reports_recovery_hint_for_rename_mapping_error() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw"] = pd.DataFrame({"收缩压/Hgmm": [120, 130]})

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            dataset_name="raw",
            steps=[
                {
                    "id": "rename",
                    "op": "rename_columns",
                    "params": {"收缩压/Hgmm": "收缩压"},
                }
            ],
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "DATASET_TRANSFORM_RENAME_MAPPING_REQUIRED"
    assert "params.mapping" in result["data"]["recovery_hint"]
    assert "mapping" in result["data"]["expected_params"]


def test_dataset_transform_rejects_df_variable_in_expr_with_guidance() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            dataset_name="raw",
            steps=[
                {
                    "id": "derive",
                    "op": "derive_column",
                    "params": {"column": "x2", "expr": "df['x'] * 2"},
                }
            ],
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "DATASET_TRANSFORM_EXPR_DF_UNSUPPORTED"
    assert "code_session" in result["data"]["recovery_hint"]
    assert "x2" not in session.datasets["raw"].columns


def test_dataset_transform_rejects_ifexp_with_guidance() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw"] = pd.DataFrame({"小时": [1, 8, 23]})

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            dataset_name="raw",
            steps=[
                {
                    "id": "derive_period",
                    "op": "derive_column",
                    "params": {
                        "column": "白天标志",
                        "expr": "'白天' if 小时 >= 6 and 小时 < 22 else '夜间'",
                    },
                }
            ],
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "DATASET_TRANSFORM_EXPR_IFEXP_UNSUPPORTED"
    assert "布尔表达式" in result["data"]["recovery_hint"]


def test_dataset_transform_patch_step_requires_transform_id_with_structured_error() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="patch_step",
            step_patch={"step_id": "dedup", "params": {}},
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "DATASET_TRANSFORM_PATCH_TRANSFORM_ID_REQUIRED"
    assert result["data"]["expected_fields"] == ["operation", "transform_id", "step_patch"]
    assert "transform_id" in result["data"]["minimal_example"]


def test_chart_session_persists_spec_and_tracks_exports() -> None:
    registry = create_default_tool_registry()
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


def test_chart_session_schema_uses_operation_level_oneof() -> None:
    registry = create_default_tool_registry()
    schema = registry.get("chart_session").parameters

    assert set(schema["required"]) == {"operation"}
    assert schema["additionalProperties"] is False

    branches = {
        branch["properties"]["operation"]["const"]: set(branch["required"])
        for branch in schema["oneOf"]
    }
    assert branches["create"] == {"operation", "dataset_name", "chart_type"}
    assert branches["update"] == {"operation", "chart_id"}
    assert branches["get"] == {"operation", "chart_id"}
    assert branches["export"] == {"operation", "chart_id"}
    assert schema["properties"]["render_engine"]["enum"] == ["auto", "plotly", "matplotlib"]


def test_chart_session_missing_required_args_returns_expected_fields_and_example() -> None:
    registry = create_default_tool_registry()
    session = Session()

    update_result = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="update",
            title="补标题",
        )
    )
    assert update_result["success"] is False
    assert update_result["data"]["error_code"] == "CHART_SESSION_UPDATE_CHART_ID_REQUIRED"
    assert update_result["data"]["expected_fields"] == ["operation", "chart_id"]
    assert "chart_id" in update_result["data"]["minimal_example"]

    create_result = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="create",
            dataset_name="trend_demo",
        )
    )
    assert create_result["success"] is False
    assert create_result["data"]["error_code"] == "CHART_SESSION_CREATE_FIELDS_REQUIRED"
    assert create_result["data"]["expected_fields"] == [
        "operation",
        "dataset_name",
        "chart_type",
    ]
    assert "chart_type" in create_result["data"]["minimal_example"]

    export_result = asyncio.run(
        registry.execute(
            "chart_session",
            session=session,
            operation="export",
        )
    )
    assert export_result["success"] is False
    assert export_result["data"]["error_code"] == "CHART_SESSION_EXPORT_CHART_ID_REQUIRED"
    assert export_result["data"]["expected_fields"] == ["operation", "chart_id"]


def test_report_session_persists_sections_and_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = create_default_tool_registry()
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
    ) -> ToolResult:
        local_manager = WorkspaceManager(session.id)
        relative_path = f"notes/exports/{filename or 'report-export'}.{output_format}"
        target = local_manager.resolve_workspace_path(relative_path, allow_missing=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake export")
        local_manager.sync_text_document_record(relative_path)
        return ToolResult(
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


def test_report_session_schema_uses_operation_level_oneof() -> None:
    registry = create_default_tool_registry()
    schema = registry.get("report_session").parameters

    assert set(schema["required"]) == {"operation"}
    assert schema["additionalProperties"] is False

    branches = {
        branch["properties"]["operation"]["const"]: set(branch["required"])
        for branch in schema["oneOf"]
    }
    assert branches["create"] == {"operation"}
    assert branches["patch_section"] == {"operation", "report_id", "section_key"}
    assert branches["attach_artifact"] == {
        "operation",
        "report_id",
        "section_key",
        "artifact_resource_id",
    }
    assert branches["get"] == {"operation", "report_id"}
    assert branches["export"] == {"operation", "report_id"}


def test_report_session_missing_required_args_returns_expected_fields_and_example() -> None:
    registry = create_default_tool_registry()
    session = Session()

    patch_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="patch_section",
            section_key="summary",
            content="补充说明",
        )
    )
    assert patch_result["success"] is False
    assert patch_result["data"]["error_code"] == "REPORT_SESSION_PATCH_REPORT_ID_REQUIRED"
    assert patch_result["data"]["expected_fields"] == [
        "operation",
        "report_id",
        "section_key",
    ]

    attach_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="attach_artifact",
            report_id="report_demo",
            section_key="summary",
        )
    )
    assert attach_result["success"] is False
    assert attach_result["data"]["error_code"] == "REPORT_SESSION_ATTACH_FIELDS_REQUIRED"
    assert attach_result["data"]["expected_fields"] == [
        "operation",
        "report_id",
        "section_key",
        "artifact_resource_id",
    ]
    assert "artifact_resource_id" in attach_result["data"]["minimal_example"]

    export_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="export",
        )
    )
    assert export_result["success"] is False
    assert export_result["data"]["error_code"] == "REPORT_SESSION_EXPORT_REPORT_ID_REQUIRED"
    assert export_result["data"]["expected_fields"] == ["operation", "report_id"]


def test_workspace_session_unifies_file_ops_and_fetch_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = create_default_tool_registry()
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

    async def fake_fetch(self: FetchURLTool, session: Session, **kwargs: object) -> ToolResult:
        return ToolResult(
            success=True,
            message="抓取成功",
            data={
                "url": str(kwargs.get("url", "")),
                "content": "# fetched",
                "length": 9,
            },
        )

    monkeypatch.setattr(FetchURLTool, "execute", fake_fetch)

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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
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


def test_workspace_session_missing_required_args_returns_expected_fields_and_example() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "workspace_session",
            session=session,
            operation="write",
            file_path="notes/a.md",
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "WORKSPACE_OPERATION_ARGS_MISSING"
    assert result["data"]["expected_fields"] == ["file_path", "content"]
    assert '"operation":"write"' in result["data"]["minimal_example"]


def test_code_session_persists_scripts_and_execution_history() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
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


def test_code_session_schema_uses_operation_and_patch_level_oneof() -> None:
    registry = create_default_tool_registry()
    schema = registry.get("code_session").parameters

    assert set(schema["required"]) == {"operation"}
    assert schema["additionalProperties"] is False

    branches = {
        branch["properties"]["operation"]["const"]: set(branch["required"])
        for branch in schema["oneOf"]
    }
    assert branches["create_script"] == {"operation", "content"}
    assert branches["get_script"] == {"operation", "script_id"}
    assert branches["patch_script"] == {"operation", "script_id", "patch"}
    assert branches["rerun"] == {"operation", "script_id"}
    assert branches["list_scripts"] == {"operation"}

    patch_schema = schema["properties"]["patch"]
    assert patch_schema["additionalProperties"] is False
    patch_branches = {
        branch["properties"]["mode"]["const"]: set(branch["required"])
        for branch in patch_schema["oneOf"]
    }
    assert patch_branches["append"] == {"mode", "new_string"}
    assert patch_branches["replace_string"] == {"mode", "old_string", "new_string"}
    assert patch_branches["replace_range"] == {
        "mode",
        "start_line",
        "end_line",
        "new_string",
    }


def test_code_session_create_script_auto_runs_by_default() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_auto_run_demo",
            language="python",
            content="result = int(df['x'].sum())",
            dataset_name="raw.csv",
            intent="自动执行脚本",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["auto_run"] is True
    assert result["data"]["execution_id"]
    assert result["data"]["script"]["script_id"] == "script_auto_run_demo"
    assert "代码执行成功" in result["message"]
    assert session.list_pending_actions(action_type="script_not_run") == []


def test_code_session_save_as_supports_result_df_alias() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_result_df_demo",
            language="python",
            dataset_name="raw.csv",
            save_as="scaled.csv",
            content=(
                "result_df = df.copy()\n"
                "result_df['scaled'] = result_df['x'] * 10\n"
                "print('scaled rows', len(result_df))\n"
            ),
        )
    )

    assert result["success"] is True, result
    assert "scaled.csv" in session.datasets
    assert session.datasets["scaled.csv"]["scaled"].tolist() == [10, 20, 30]
    assert "已保存为数据集 'scaled.csv'" in result["message"]


def test_code_session_missing_required_args_returns_expected_fields_and_example() -> None:
    registry = create_default_tool_registry()
    session = Session()

    get_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="get_script",
        )
    )
    assert get_result["success"] is False
    assert get_result["data"]["error_code"] == "CODE_SESSION_GET_SCRIPT_ID_REQUIRED"
    assert get_result["data"]["expected_fields"] == ["operation", "script_id"]

    run_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="run_script",
        )
    )
    assert run_result["success"] is False
    assert run_result["data"]["error_code"] == "CODE_SESSION_RUN_SCRIPT_ID_OR_CONTENT_REQUIRED"
    assert "content" in run_result["message"]

    promote_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="promote_output",
        )
    )
    assert promote_result["success"] is False
    assert promote_result["data"]["error_code"] == "CODE_SESSION_PROMOTE_TARGET_REQUIRED"
    assert "dataset_name" in promote_result["data"]["recovery_hint"]


def test_code_session_create_script_auto_run_failure_registers_pending_action() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            script_id="script_auto_run_failure",
            language="python",
            content="result = 1 / 0",
            intent="自动执行失败样例",
        )
    )

    assert result["success"] is False, result
    pending = session.list_pending_actions(action_type="script_not_run")
    assert len(pending) == 1
    assert pending[0]["key"] == "script_auto_run_failure"


def test_code_session_create_script_without_auto_run_registers_pending_action() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
            script_id="script_manual_followup",
            language="python",
            content="result = 42",
        )
    )

    assert result["success"] is True, result
    pending = session.list_pending_actions(action_type="script_not_run")
    assert len(pending) == 1
    assert pending[0]["key"] == "script_manual_followup"


def test_code_session_supports_patch_rerun_and_promote_output() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
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


def test_code_session_patch_validation_returns_structured_error() -> None:
    registry = create_default_tool_registry()
    session = Session()

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
            script_id="script_patch_validation",
            language="python",
            content="result = 42\n",
        )
    )
    assert create_result["success"] is True, create_result

    patch_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="patch_script",
            script_id="script_patch_validation",
            patch={
                "mode": "replace_string",
                "new_string": "result = 43",
            },
        )
    )
    assert patch_result["success"] is False
    assert patch_result["data"]["error_code"] == "CODE_SESSION_PATCH_OLD_STRING_REQUIRED"
    assert patch_result["data"]["expected_fields"] == [
        "patch.mode",
        "patch.old_string",
        "patch.new_string",
    ]


def test_code_session_records_failure_location_and_retry_link() -> None:
    registry = create_default_tool_registry()
    session = Session()

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
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
    registry = create_default_tool_registry()
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
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["only.csv"] = pd.DataFrame({"x": [2, 4, 6]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
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


def test_code_session_rejects_file_io_when_dataset_name_provided() -> None:
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["all.xlsx"] = pd.DataFrame({"x": [1, 2, 3]})

    create_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="create_script",
            auto_run=False,
            script_id="script_dataset_guard",
            language="python",
            content="import pandas as pd\ndf = pd.read_excel('all.xlsx')\nresult = len(df)\n",
        )
    )
    assert create_result["success"] is True, create_result

    run_result = asyncio.run(
        registry.execute(
            "code_session",
            session=session,
            operation="run_script",
            script_id="script_dataset_guard",
            dataset_name="all.xlsx",
            intent="验证防呆",
        )
    )

    assert run_result["success"] is False, run_result
    assert run_result["error_code"] == "CODE_SESSION_DATASET_IO_CONFLICT"
    assert "直接使用沙箱注入的变量 df" in run_result["message"]


def test_dataset_transform_rejects_lambda_with_code_session_guidance() -> None:
    """lambda 表达式被拒绝时，recovery_hint 应明确引导用户改用 code_session，
    minimal_example 应展示 code_session 中 pd.cut 的用法。"""
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw"] = pd.DataFrame({"小时": [1, 8, 14, 21]})

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            dataset_name="raw",
            steps=[
                {
                    "id": "derive_period",
                    "op": "derive_column",
                    "params": {
                        "column": "时间段",
                        "expr": "小时.apply(lambda h: '早晨' if 6 <= h < 12 else '其他')",
                    },
                }
            ],
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "DATASET_TRANSFORM_EXPR_LAMBDA_UNSUPPORTED"
    assert (
        "code_session" in result["data"]["recovery_hint"]
    ), f"recovery_hint 应提到 code_session，实际: {result['data']['recovery_hint']}"
    assert (
        "pd.cut" in result["data"]["minimal_example"]
        or "np.select" in result["data"]["minimal_example"]
    ), f"minimal_example 应包含 pd.cut 或 np.select，实际: {result['data']['minimal_example']}"


def test_task_write_update_in_progress_message_includes_transition_reminder() -> None:
    """in_progress 任务的确认消息应包含阶段过渡提醒。"""
    from nini.tools.task_write import TaskWriteTool

    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "检查数据质量", "status": "pending", "tool_hint": "dataset_catalog"},
            {"id": 2, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
        ]
    )
    tool = TaskWriteTool()

    result = tool._handle_update(
        session,
        [{"id": 1, "status": "in_progress"}],
    )

    assert result.success is True
    # 消息必须提醒 LLM 完成后更新任务状态
    assert "task_state" in result.message
    assert "completed" in result.message
