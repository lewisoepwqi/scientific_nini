"""Phase 3：run_code 与沙箱策略测试。"""

from __future__ import annotations

import asyncio

import pandas as pd

from nini.agent.session import Session
from nini.skills.registry import create_default_registry


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
