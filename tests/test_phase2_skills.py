"""Phase 2 技能链路测试。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.skills.registry import create_default_registry


def test_default_registry_contains_phase2_skills() -> None:
    registry = create_default_registry()
    skills = set(registry.list_skills())
    assert {
        "load_dataset",
        "preview_data",
        "data_summary",
        "t_test",
        "anova",
        "correlation",
        "regression",
        "create_chart",
    }.issubset(skills)


@pytest.mark.asyncio
async def test_create_chart_skill_returns_plotly_json() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["experiment.csv"] = pd.DataFrame(
        {
            "group": ["control", "control", "treatment", "treatment"],
            "value": [1.1, 1.2, 1.8, 2.0],
            "day": [1, 2, 1, 2],
        }
    )

    result = await registry.execute(
        "create_chart",
        session=session,
        dataset_name="experiment.csv",
        chart_type="box",
        y_column="value",
        group_column="group",
        journal_style="nature",
        title="Treatment vs Control",
    )

    assert result["success"] is True
    assert result["has_chart"] is True
    assert isinstance(result["chart_data"], dict)
    assert "data" in result["chart_data"]
    assert "layout" in result["chart_data"]
    artifacts = result.get("artifacts") or []
    assert len(artifacts) == 1
    assert artifacts[0]["format"] == "json"
    assert artifacts[0]["name"].endswith(".plotly.json")
    assert Path(artifacts[0]["path"]).exists()
