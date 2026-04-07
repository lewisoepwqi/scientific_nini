"""Phase 2 技能链路测试。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nini.agent.artifact_ref import ArtifactRef
from nini.agent.session import Session
from nini.tools.registry import create_default_tool_registry
from nini.tools.visualization import CreateChartTool


def test_default_registry_contains_phase2_skills() -> None:
    """确认注册表中包含会话工具及保留的原子工具。"""
    registry = create_default_tool_registry()
    skills = set(registry.list_tools())
    # 会话工具（已合并原子工具）
    assert {
        "load_dataset",
        "data_summary",
        "t_test",
        "anova",
        "chart_session",
        "dataset_catalog",
    }.issubset(skills)
    # 原子工具已由会话工具直接实例化，不再注册到注册表
    assert "create_chart" not in skills
    assert "correlation" not in skills
    assert "regression" not in skills
    assert "preview_data" not in skills


@pytest.mark.asyncio
async def test_create_chart_skill_returns_plotly_json() -> None:
    """直接实例化 CreateChartTool 进行单元测试，无需通过注册表。"""
    skill = CreateChartTool()
    session = Session()
    session.datasets["experiment.csv"] = pd.DataFrame(
        {
            "group": ["control", "control", "treatment", "treatment"],
            "value": [1.1, 1.2, 1.8, 2.0],
            "day": [1, 2, 1, 2],
        }
    )

    result = (
        await skill.execute(
            session=session,
            dataset_name="experiment.csv",
            chart_type="box",
            y_column="value",
            group_column="group",
            journal_style="nature",
            title="Treatment vs Control",
        )
    ).to_dict()

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


@pytest.mark.asyncio
async def test_create_line_chart_with_mixed_datetime_types() -> None:
    """直接实例化 CreateChartTool 测试混合日期类型处理。"""
    skill = CreateChartTool()
    session = Session()
    session.datasets["timeline.csv"] = pd.DataFrame(
        {
            "测量时刻": [
                pd.Timestamp("2024-01-02 09:00:00"),
                "2024-01-01 09:00:00",
                pd.Timestamp("2024-01-03 09:00:00"),
            ],
            "收缩压": [120, 118, 122],
        }
    )

    result = (
        await skill.execute(
            session=session,
            dataset_name="timeline.csv",
            chart_type="line",
            x_column="测量时刻",
            y_column="收缩压",
            title="收缩压趋势",
        )
    ).to_dict()

    assert result["success"] is True, result
    assert result["has_chart"] is True
    assert isinstance(result["chart_data"], dict)


@pytest.mark.asyncio
async def test_create_chart_stores_artifact_ref_in_sandbox_mode(tmp_path: Path) -> None:
    """沙箱模式（workspace_root 已设置）下，session.artifacts['latest_chart'] 应为 ArtifactRef。"""
    skill = CreateChartTool()
    session = Session()
    session.workspace_root = tmp_path  # 模拟沙箱模式
    session.datasets["experiment.csv"] = pd.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "value": [1.0, 1.5, 2.0, 2.5],
        }
    )

    result = (
        await skill.execute(
            session=session,
            dataset_name="experiment.csv",
            chart_type="box",
            y_column="value",
            group_column="group",
            title="沙箱图表测试",
        )
    ).to_dict()

    assert result["success"] is True
    ref = session.artifacts.get("latest_chart")
    assert isinstance(ref, ArtifactRef), f"期望 ArtifactRef，实际得到 {type(ref)}"
    assert ref.path, "ArtifactRef.path 不能为空"
    assert ref.type == "chart"
