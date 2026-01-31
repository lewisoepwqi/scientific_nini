"""
分享包服务。
"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.export_package import ExportPackage
from app.models.visualization import Visualization
from app.services.observability import log_export_event
from app.services.retention_service import calculate_expiry


class ExportService:
    """分享包服务。"""

    async def create_export(self, db: AsyncSession, visualization_id: str) -> ExportPackage:
        """创建分享包。"""
        result = await db.execute(select(Visualization).where(Visualization.id == visualization_id))
        visualization = result.scalar_one_or_none()
        if not visualization:
            raise ValueError("图表不存在")

        expires_at = calculate_expiry(settings.EXPORT_RETENTION_DAYS, datetime.now(timezone.utc))
        export = ExportPackage(
            visualization_id=visualization.id,
            dataset_version_ref=visualization.dataset_version_id or "",
            config_snapshot=visualization.config or {},
            render_log_snapshot=visualization.render_log or {},
            expires_at=expires_at,
        )
        db.add(export)
        await db.flush()
        log_export_event(
            "create",
            export_id=export.id,
            visualization_id=visualization.id,
            dataset_version_ref=export.dataset_version_ref,
        )
        return export

    async def get_export(self, db: AsyncSession, export_id: str) -> ExportPackage | None:
        """获取分享包。"""
        result = await db.execute(select(ExportPackage).where(ExportPackage.id == export_id))
        return result.scalar_one_or_none()


export_service = ExportService()
