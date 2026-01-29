"""
API v1 router configuration.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import datasets, analysis, visualizations, health

api_router = APIRouter(prefix="/api/v1")

# Include endpoint routers
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(visualizations.router, prefix="/visualizations", tags=["visualizations"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
