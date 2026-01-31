"""
数据版本服务。
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion, DatasetVersionSource
from app.services.retention_service import calculate_expiry


class DatasetVersionService:
    """数据版本服务。"""

    async def create_default_version(self, db: AsyncSession, dataset: Dataset) -> DatasetVersion:
        """为数据集创建默认版本。"""
        expires_at = calculate_expiry(settings.DATA_RETENTION_DAYS, datetime.now(timezone.utc))
        version = DatasetVersion(
            dataset_id=dataset.id,
            source_type=DatasetVersionSource.DEFAULT,
            transformations=None,
            row_count=dataset.row_count,
            column_count=dataset.column_count,
            expires_at=expires_at,
        )
        db.add(version)
        await db.flush()
        return version


dataset_version_service = DatasetVersionService()
