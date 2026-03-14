"""Phase 3：run_code 与沙箱策略测试。"""

from __future__ import annotations

import asyncio

import pandas as pd

from nini.agent.session import Session
from nini.tools.registry import create_default_registry
from nini.workspace import WorkspaceManager


def test_registry_contains_run_code() -> None:
    registry = create_default_registry()
    assert "run_code" in registry.list_skills()


def test_run_code_returns_scalar_result_and_stdout() -> None:
    registry = create_default_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            code="print('hello')\nresult = 1 + 2",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["result"] == 3
    assert "hello" in result["message"]


def test_run_code_blocks_disallowed_import() -> None:
    registry = create_default_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            code="import os\nresult = 1",
        )
    )

    assert result["success"] is False
    assert "沙箱策略拦截" in result["message"]
    assert "不允许导入模块" in result["message"]
    assert "高风险模块" in result["message"]


def test_run_code_returns_review_request_for_reviewable_import() -> None:
    registry = create_default_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            code="import sympy\nresult = 1",
        )
    )

    assert result["success"] is False
    assert result["data"]["_sandbox_review_required"] is True
    assert result["data"]["requested_packages"] == ["sympy"]


def test_run_code_persist_df_overwrites_dataset() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2], "y": [10, 20]})

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            dataset_name="raw.csv",
            persist_df=True,
            code="df['z'] = df['x'] + df['y']\nresult = df.shape[1]",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["result"] == 3
    assert "z" in session.datasets["raw.csv"].columns


def test_run_code_output_df_can_save_as_dataset() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            dataset_name="raw.csv",
            save_as="normalized.csv",
            code=(
                "output_df = df.copy()\n"
                "output_df['x_norm'] = (output_df['x'] - output_df['x'].mean()) / output_df['x'].std()\n"
            ),
        )
    )

    assert result["success"] is True
    assert result["has_dataframe"] is True
    assert "normalized.csv" in session.datasets
    assert "x_norm" in session.datasets["normalized.csv"].columns


def test_run_code_large_output_df_does_not_timeout() -> None:
    registry = create_default_registry()
    session = Session()
    row_count = 20000
    session.datasets["raw.csv"] = pd.DataFrame(
        {
            "x": list(range(row_count)),
            "y": list(range(row_count)),
        }
    )

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            dataset_name="raw.csv",
            code="output_df = df[['x', 'y']].copy()",
        )
    )

    assert result["success"] is True, result
    assert result["has_dataframe"] is True
    assert result["dataframe_preview"]["total_rows"] == row_count
    assert "超时" not in result["message"]


def test_run_code_auto_persists_temp_dataset_when_no_save_as() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            dataset_name="raw.csv",
            code="output_df = df.assign(x2=df['x'] * 2)",
        )
    )

    assert result["success"] is True, result
    output_resources = result["data"].get("output_resources", [])
    assert isinstance(output_resources, list) and output_resources
    assert output_resources[-1]["resource_type"] == "temp_dataset"
    output_name = result["data"].get("output_dataset_name")
    assert isinstance(output_name, str) and output_name in session.datasets


def test_run_code_routes_through_code_session_history() -> None:
    registry = create_default_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            code="result = 40 + 2",
            intent="计算答案",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["result"] == 42
    assert result["data"]["script_id"].startswith("script_")
    assert result["data"]["execution_id"]

    manager = WorkspaceManager(session.id)
    script_resource = manager.get_resource_summary(result["data"]["script_id"])
    assert script_resource is not None
    assert script_resource["resource_type"] == "script"

    execution = manager.get_code_execution(result["data"]["execution_id"])
    assert execution is not None
    assert execution["script_resource_id"] == result["data"]["script_id"]
    assert execution["tool_name"] == "run_code"


def test_execute_r_code_limits_dataframe_preview_rows(monkeypatch) -> None:
    from nini.tools import code_runtime as code_runtime_module

    session = Session()

    async def _fake_r_execute(**kwargs):
        return {
            "success": True,
            "stdout": "",
            "stderr": "",
            "datasets": {},
            "figures": [],
            "output_df": pd.DataFrame({"x": list(range(35))}),
        }

    monkeypatch.setattr(code_runtime_module.r_sandbox_executor, "execute", _fake_r_execute)
    monkeypatch.setattr(
        code_runtime_module,
        "_persist_runtime_dataset",
        lambda _session, **kwargs: {
            "id": "tmp_ds_1",
            "resource_type": "temp_dataset",
            "name": kwargs["dataset_name"],
        },
    )

    result = asyncio.run(
        code_runtime_module.execute_r_code(session=session, code="output_df <- data.frame(x=1:35)")
    )

    assert result.success is True
    assert result.has_dataframe is True
    preview = result.dataframe_preview
    assert isinstance(preview, dict)
    assert preview["preview_rows"] == 20
    assert len(preview["data"]) == 20
