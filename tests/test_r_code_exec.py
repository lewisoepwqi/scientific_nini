"""run_r_code 技能测试。"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.sandbox.r_executor import detect_r_installation
from nini.skills.r_code_exec import RunRCodeSkill
from nini.skills.registry import create_default_registry


def test_registry_registers_run_r_code_conditionally() -> None:
    registry = create_default_registry()
    has_skill = "run_r_code" in registry.list_skills()
    r_available = bool(detect_r_installation().get("available"))

    if r_available:
        assert has_skill is True
    else:
        assert has_skill is False


def test_run_r_code_skill_blocks_policy_violation() -> None:
    skill = RunRCodeSkill()
    session = Session()

    result = asyncio.run(skill.execute(session=session, code="system('ls')"))
    payload = result.to_dict()
    assert payload["success"] is False
    assert "策略拦截" in payload["message"]


@pytest.mark.skipif(
    not bool(detect_r_installation().get("available")),
    reason="Rscript 不可用，跳过 run_r_code 集成测试",
)
def test_run_r_code_skill_returns_dataframe_and_save_as() -> None:
    skill = RunRCodeSkill()
    session = Session()
    session.datasets["raw.csv"] = pd.DataFrame({"x": [1, 2, 3]})

    result = asyncio.run(
        skill.execute(
            session=session,
            dataset_name="raw.csv",
            save_as="normalized.csv",
            code="""
output_df <- df
output_df$z <- output_df$x * 10
result <- nrow(output_df)
""",
        )
    )

    payload = result.to_dict()
    assert payload["success"] is True, payload
    assert payload.get("has_dataframe") is True
    assert "normalized.csv" in session.datasets
    assert "z" in session.datasets["normalized.csv"].columns
