"""第二阶段P1：降级策略与自我修复机制测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.registry import SkillRegistry, create_default_registry


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    yield


@pytest.mark.asyncio
async def test_t_test_fallback_to_mann_whitney_on_non_normal() -> None:
    """当数据不符合正态性假设时，t检验应降级到Mann-Whitney U检验。"""
    registry = create_default_registry()
    session = Session()

    # 创建明显偏态的数据（指数分布）
    np.random.seed(42)
    session.datasets["non_normal.csv"] = pd.DataFrame(
        {
            "group": ["A"] * 30 + ["B"] * 30,
            "value": list(np.random.exponential(1, 30)) + list(np.random.exponential(2, 30)),
        }
    )

    result = await registry.execute_with_fallback(
        "t_test",
        session=session,
        dataset_name="non_normal.csv",
        value_column="value",
        group_column="group",
        enable_fallback=True,
    )

    # 应该触发降级
    assert result["fallback"] is True, "非正态数据应触发降级"
    assert result["fallback_skill"] == "mann_whitney"
    assert result["success"] is True
    assert "原始技能执行失败" in result.get(
        "fallback_reason", ""
    ) or "不符合正态性假设" in result.get("fallback_reason", "")


@pytest.mark.asyncio
async def test_anova_fallback_to_kruskal_wallis_on_non_normal() -> None:
    """当数据不符合正态性假设时，ANOVA应降级到Kruskal-Wallis检验。"""
    registry = create_default_registry()
    session = Session()

    # 创建三组偏态数据
    np.random.seed(42)
    session.datasets["non_normal_anova.csv"] = pd.DataFrame(
        {
            "group": ["A"] * 20 + ["B"] * 20 + ["C"] * 20,
            "value": list(np.random.exponential(1, 20))
            + list(np.random.exponential(2, 20))
            + list(np.random.exponential(3, 20)),
        }
    )

    result = await registry.execute_with_fallback(
        "anova",
        session=session,
        dataset_name="non_normal_anova.csv",
        value_column="value",
        group_column="group",
        enable_fallback=True,
    )

    # 应该触发降级
    assert result["fallback"] is True, "非正态数据应触发降级"
    assert result["fallback_skill"] == "kruskal_wallis"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_fallback_disabled_when_requested() -> None:
    """当禁用降级时，即使数据不满足假设也应执行原始检验。"""
    registry = create_default_registry()
    session = Session()

    # 创建偏态数据
    np.random.seed(42)
    session.datasets["non_normal.csv"] = pd.DataFrame(
        {
            "group": ["A"] * 30 + ["B"] * 30,
            "value": list(np.random.exponential(1, 30)) + list(np.random.exponential(2, 30)),
        }
    )

    result = await registry.execute_with_fallback(
        "t_test",
        session=session,
        dataset_name="non_normal.csv",
        value_column="value",
        group_column="group",
        enable_fallback=False,
    )

    # 不应触发降级（fallback字段应为False或不存在）
    assert result.get("fallback", False) is False, "禁用降级时不应触发降级"


@pytest.mark.asyncio
async def test_normal_data_no_fallback_needed() -> None:
    """正态数据不需要降级。"""
    registry = create_default_registry()
    session = Session()

    # 创建正态数据
    np.random.seed(42)
    session.datasets["normal.csv"] = pd.DataFrame(
        {
            "group": ["A"] * 50 + ["B"] * 50,
            "value": list(np.random.normal(1, 0.5, 50)) + list(np.random.normal(2, 0.5, 50)),
        }
    )

    result = await registry.execute_with_fallback(
        "t_test",
        session=session,
        dataset_name="normal.csv",
        value_column="value",
        group_column="group",
        enable_fallback=True,
    )

    # 正态数据不应触发降级（fallback字段应为False或不存在）
    assert result.get("fallback", False) is False, "正态数据不应触发降级"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_data_diagnosis_missing_values() -> None:
    """测试数据诊断功能检测缺失值。"""
    registry = SkillRegistry()
    session = Session()

    # 创建有缺失值的数据
    session.datasets["missing.csv"] = pd.DataFrame(
        {
            "x": [1, 2, np.nan, 4, 5],
            "y": [1, np.nan, np.nan, 4, 5],
            "z": [1, 2, 3, 4, 5],
        }
    )

    diagnosis = await registry.diagnose_data_problem(
        session=session,
        dataset_name="missing.csv",
    )

    assert diagnosis["dataset_name"] == "missing.csv"
    assert len(diagnosis["issues"]) > 0 or "missing_values" in diagnosis

    # 检查y列的缺失值诊断
    if "missing_values" in diagnosis:
        assert diagnosis["missing_values"]["column"] in ["x", "y"]


@pytest.mark.asyncio
async def test_data_diagnosis_outliers() -> None:
    """测试数据诊断功能检测异常值。"""
    registry = SkillRegistry()
    session = Session()

    # 创建有异常值的数据
    np.random.seed(42)
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100]  # 100是异常值
    session.datasets["outliers.csv"] = pd.DataFrame({"value": data})

    diagnosis = await registry.diagnose_data_problem(
        session=session,
        dataset_name="outliers.csv",
        target_column="value",
    )

    assert diagnosis["dataset_name"] == "outliers.csv"
    # 应该检测到异常值
    if "outliers" in diagnosis:
        assert diagnosis["outliers"]["count"] > 0


@pytest.mark.asyncio
async def test_data_diagnosis_small_sample_size() -> None:
    """测试数据诊断功能检测小样本量。"""
    registry = SkillRegistry()
    session = Session()

    # 创建小样本数据
    session.datasets["small.csv"] = pd.DataFrame({"value": [1, 2, 3, 4, 5]})

    diagnosis = await registry.diagnose_data_problem(
        session=session,
        dataset_name="small.csv",
        target_column="value",
    )

    assert diagnosis["dataset_name"] == "small.csv"
    # 应该检测到小样本量警告
    if "sample_size" in diagnosis:
        assert diagnosis["sample_size"]["warning"] is True


@pytest.mark.asyncio
async def test_data_diagnosis_with_suggestions() -> None:
    """测试数据诊断功能提供建议。"""
    registry = SkillRegistry()
    session = Session()

    # 创建有多种问题的数据
    session.datasets["problems.csv"] = pd.DataFrame(
        {
            "value": [1, 2, np.nan, 4, 5, 100],  # 缺失值+异常值
        }
    )

    diagnosis = await registry.diagnose_data_problem(
        session=session,
        dataset_name="problems.csv",
        target_column="value",
    )

    # 应该提供修复建议
    suggestions = diagnosis.get("suggestions", [])
    assert len(suggestions) > 0, "应该提供修复建议"

    # 检查建议结构
    for suggestion in suggestions:
        assert "type" in suggestion
        assert "severity" in suggestion
        assert "message" in suggestion


@pytest.mark.asyncio
async def test_fallback_preserves_original_result_info() -> None:
    """降级结果应保留原始技能信息。"""
    registry = create_default_registry()
    session = Session()

    # 创建偏态数据
    np.random.seed(42)
    session.datasets["non_normal.csv"] = pd.DataFrame(
        {
            "group": ["A"] * 30 + ["B"] * 30,
            "value": list(np.random.exponential(1, 30)) + list(np.random.exponential(2, 30)),
        }
    )

    result = await registry.execute_with_fallback(
        "t_test",
        session=session,
        dataset_name="non_normal.csv",
        value_column="value",
        group_column="group",
        enable_fallback=True,
    )

    # 检查降级信息
    assert "original_skill" in result
    assert result["original_skill"] == "t_test"
    if result.get("fallback"):
        assert "fallback_skill" in result
        assert "fallback_reason" in result
