"""
图表配置服务。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chart_config import ChartConfig


class ChartConfigService:
    """图表配置服务。"""

    async def clone_config(self, db: AsyncSession, config_id: str) -> ChartConfig:
        """克隆配置并返回新配置。"""
        result = await db.execute(select(ChartConfig).where(ChartConfig.id == config_id))
        config = result.scalar_one_or_none()
        if not config:
            raise ValueError("配置不存在")

        cloned = ChartConfig(
            semantic_config=config.semantic_config,
            style_config=config.style_config,
            export_config=config.export_config,
            version=config.version + 1,
        )
        db.add(cloned)
        await db.flush()
        return cloned


chart_config_service = ChartConfigService()
