"""
建议持久化服务。
"""
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suggestion import Suggestion
from app.models.analysis_task import AnalysisTask
from app.models.enums import SuggestionStatus
from app.services.observability import log_suggestion_event


def _normalize_payload(payload: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """标准化建议结构。"""
    return {
        "cleaning": list(payload.get("cleaning", [])),
        "statistics": list(payload.get("statistics", [])),
        "chart_recommendations": list(payload.get("chart_recommendations", [])),
        "notes": list(payload.get("notes", [])),
    }


class SuggestionService:
    """建议持久化服务。"""

    async def create_suggestion(self, db: AsyncSession, task: AnalysisTask, payload: Dict[str, List[str]]) -> Suggestion:
        """创建建议记录。"""
        suggestion = Suggestion(
            task_id=task.id,
            payload=_normalize_payload(payload),
            status=SuggestionStatus.PENDING,
        )
        db.add(suggestion)
        await db.flush()
        log_suggestion_event("create", task_id=task.id, suggestion_id=suggestion.id)
        return suggestion

    async def get_latest_suggestion(self, db: AsyncSession, task_id: str) -> Suggestion | None:
        """获取最新建议。"""
        result = await db.execute(
            select(Suggestion).where(Suggestion.task_id == task_id).order_by(Suggestion.created_at.desc())
        )
        return result.scalars().first()

    async def accept(self, db: AsyncSession, task: AnalysisTask) -> None:
        """采纳建议。"""
        task.suggestion_status = SuggestionStatus.ACCEPTED
        await db.flush()
        log_suggestion_event("accept", task_id=task.id)

    async def reject(self, db: AsyncSession, task: AnalysisTask) -> None:
        """拒绝建议。"""
        task.suggestion_status = SuggestionStatus.REJECTED
        await db.flush()
        log_suggestion_event("reject", task_id=task.id)


suggestion_service = SuggestionService()
