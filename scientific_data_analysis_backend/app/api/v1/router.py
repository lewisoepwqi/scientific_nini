"""
API v1 router configuration.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    datasets,
    analysis,
    visualizations,
    health,
    tasks,
    chart_configs,
    suggestions,
    exports,
    shares,
)

api_router = APIRouter(prefix="/api/v1")

# Include endpoint routers
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(visualizations.router, prefix="/visualizations", tags=["visualizations"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(chart_configs.router, prefix="/chart-configs", tags=["chart-configs"])
api_router.include_router(suggestions.router, tags=["suggestions"])
api_router.include_router(exports.router, tags=["exports"])
api_router.include_router(shares.router, tags=["shares"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
