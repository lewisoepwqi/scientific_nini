"""数据模型模块。"""

from nini.models.execution_plan import (
    ActionType,
    ExecutionPlan,
    PlanAction,
    PlanPhase,
    PlanStatus,
    PhaseType,
)
from nini.models.user_profile import UserProfile

# Database models（如果存在）
try:
    from nini.models.database import (
        AnalysisHistoryModel,
        ChartConfigModel,
        DatasetModel,
        UserModel,
    )
except ImportError:
    pass

# Schemas（如果存在）
try:
    from nini.models.schemas import (
        AnalysisRequest,
        AnalysisResult,
        ChartConfig,
        DatasetInfo,
        DatasetUploadResponse,
    )
except ImportError:
    pass

__all__ = [
    # Execution plan
    "ExecutionPlan",
    "PlanAction",
    "PlanPhase",
    "PlanStatus",
    "ActionType",
    "PhaseType",
    # User profile
    "UserProfile",
]
