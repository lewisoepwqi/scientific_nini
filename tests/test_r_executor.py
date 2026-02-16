"""R 执行器测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.sandbox.r_executor import RSandboxPolicyError, detect_r_installation, r_sandbox_executor

_R_AVAILABLE = bool(detect_r_installation().get("available"))
pytestmark = pytest.mark.skipif(not _R_AVAILABLE, reason="Rscript 不可用，跳过 R 执行器测试")


@pytest.mark.asyncio
async def test_r_executor_scalar_result() -> None:
    session = Session()
    payload = await r_sandbox_executor.execute(
        code="result <- 6 * 7\ncat('hello from R')",
        session_id=session.id,
        datasets=session.datasets,
        dataset_name=None,
        persist_df=False,
    )

    assert payload["success"] is True, payload
    assert payload["result"] == 42
    assert "hello from R" in payload["stdout"]


@pytest.mark.asyncio
async def test_r_executor_output_df_and_persist_dataset() -> None:
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    payload = await r_sandbox_executor.execute(
        code="""
df$y <- df$x * 2
output_df <- df
result <- nrow(df)
""",
        session_id=session.id,
        datasets=session.datasets,
        dataset_name="raw.csv",
        persist_df=True,
    )

    assert payload["success"] is True, payload
    assert isinstance(payload.get("output_df"), pd.DataFrame)
    assert list(payload["output_df"].columns) == ["x", "y"]
    assert "raw.csv" in payload.get("datasets", {})
    assert "y" in payload["datasets"]["raw.csv"].columns


@pytest.mark.asyncio
async def test_r_executor_blocks_policy_violation() -> None:
    session = Session()
    with pytest.raises(RSandboxPolicyError):
        await r_sandbox_executor.execute(
            code="system('ls')",
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )
