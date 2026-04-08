"""分析阶段检测器测试。"""

from __future__ import annotations

from nini.agent.components.analysis_stage_detector import AnalysisStage, detect_current_stage
from nini.agent.session import Session


def test_detect_current_stage_dispatch_agents_is_analysis() -> None:
    """最后调用的工具是 dispatch_agents 时，应识别为 analysis 阶段。"""
    session = Session()
    session.messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "dispatch_agents"}}]},
    ]
    stage = detect_current_stage(session)
    assert stage == AnalysisStage.ANALYSIS


def test_detect_current_stage_stat_test_is_analysis() -> None:
    """stat_test 应识别为 analysis 阶段。"""
    session = Session()
    session.messages = [
        {"role": "tool", "tool_name": "stat_test"},
    ]
    stage = detect_current_stage(session)
    assert stage == AnalysisStage.ANALYSIS


def test_detect_current_stage_dataset_transform_is_data_prep() -> None:
    """dataset_transform 应识别为 data_prep 阶段。"""
    session = Session()
    session.messages = [
        {"role": "tool", "tool_name": "dataset_transform"},
    ]
    stage = detect_current_stage(session)
    assert stage == AnalysisStage.DATA_PREP


def test_detect_current_stage_empty_messages_is_unknown() -> None:
    """空消息列表应返回 UNKNOWN。"""
    session = Session()
    stage = detect_current_stage(session)
    assert stage == AnalysisStage.UNKNOWN
