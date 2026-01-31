"""
枚举定义。
"""
from enum import Enum


class TaskStage(str, Enum):
    """任务阶段。"""

    UPLOADING = "uploading"
    PARSED = "parsed"
    PROFILING = "profiling"
    SUGGESTION_PENDING = "suggestion_pending"
    PROCESSING = "processing"
    ANALYSIS_READY = "analysis_ready"
    VISUALIZATION_READY = "visualization_ready"


class SuggestionStatus(str, Enum):
    """建议状态。"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class SharePermission(str, Enum):
    """分享权限。"""

    VIEW = "view"
    EDIT = "edit"
