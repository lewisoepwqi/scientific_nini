"""
任务服务。
"""
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_task import AnalysisTask
from app.models.dataset import Dataset
from app.models.enums import TaskStage, SuggestionStatus
from app.services.dataset_version_service import dataset_version_service
from app.services.observability import log_task_event

logger = logging.getLogger(__name__)


class TaskService:
    """任务服务。"""

    async def create_task(self, db: AsyncSession, dataset_id: str, owner_id: str) -> AnalysisTask:
        """创建分析任务。"""
        result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise ValueError("数据集不存在")

        version = await dataset_version_service.create_default_version(db, dataset)
        task = AnalysisTask(
            dataset_id=dataset.id,
            owner_id=owner_id,
            stage=TaskStage.PARSED,
            suggestion_status=SuggestionStatus.PENDING,
            active_version_id=version.id,
        )
        db.add(task)
        await db.flush()
        logger.info("创建任务", extra={"task_id": task.id, "dataset_id": dataset.id})
        log_task_event("create", task_id=task.id, owner_id=owner_id, dataset_id=dataset.id)
        return task

    async def list_tasks(self, db: AsyncSession, owner_id: Optional[str]) -> List[AnalysisTask]:
        """查询任务列表。"""
        stmt = select(AnalysisTask)
        if owner_id:
            stmt = stmt.where(AnalysisTask.owner_id == owner_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_task(self, db: AsyncSession, task_id: str) -> Optional[AnalysisTask]:
        """获取任务详情。"""
        result = await db.execute(select(AnalysisTask).where(AnalysisTask.id == task_id))
        return result.scalar_one_or_none()


task_service = TaskService()
