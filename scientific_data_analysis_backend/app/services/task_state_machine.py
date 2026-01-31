"""
任务状态机辅助方法。
"""
from typing import Dict, List

from app.models.enums import TaskStage


_ALLOWED_TRANSITIONS: Dict[TaskStage, List[TaskStage]] = {
    TaskStage.UPLOADING: [TaskStage.PARSED],
    TaskStage.PARSED: [TaskStage.PROFILING, TaskStage.SUGGESTION_PENDING],
    TaskStage.PROFILING: [TaskStage.SUGGESTION_PENDING, TaskStage.PROCESSING],
    TaskStage.SUGGESTION_PENDING: [TaskStage.PROCESSING, TaskStage.ANALYSIS_READY],
    TaskStage.PROCESSING: [TaskStage.ANALYSIS_READY],
    TaskStage.ANALYSIS_READY: [TaskStage.VISUALIZATION_READY],
    TaskStage.VISUALIZATION_READY: [],
}


def can_transition(current: TaskStage, target: TaskStage) -> bool:
    """判断任务是否允许从当前阶段迁移到目标阶段。"""
    return target in _ALLOWED_TRANSITIONS.get(current, [])


def assert_transition(current: TaskStage, target: TaskStage) -> None:
    """校验任务阶段迁移是否合法。"""
    if not can_transition(current, target):
        raise ValueError(f"不允许从 {current.value} 迁移到 {target.value}")


def next_stages(current: TaskStage) -> List[TaskStage]:
    """获取当前阶段的可选下一阶段。"""
    return list(_ALLOWED_TRANSITIONS.get(current, []))
