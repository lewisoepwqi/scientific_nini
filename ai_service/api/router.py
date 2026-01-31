"""AI 服务路由聚合。"""
from fastapi import APIRouter

from ai_service.api.endpoints import router as endpoints_router
from ai_service.api.suggestions import router as suggestions_router

api_router = APIRouter()
api_router.include_router(endpoints_router)
api_router.include_router(suggestions_router)
