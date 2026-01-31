"""
AI 建议端点。
"""
from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter(prefix="/api/ai", tags=["AI Suggestions"])


class SuggestionRequest(BaseModel):
    """建议请求。"""
    summary: Dict[str, Any] | None = None


class SuggestionResponse(BaseModel):
    """建议响应。"""
    cleaning: List[str]
    statistics: List[str]
    chart_recommendations: List[str]
    notes: List[str]


@router.post("/suggestions", response_model=SuggestionResponse)
async def generate_suggestions(request: SuggestionRequest):
    """生成结构化建议（占位实现）。"""
    _ = request.summary
    return SuggestionResponse(
        cleaning=["检查缺失值与异常值"],
        statistics=["补充描述性统计"],
        chart_recommendations=["尝试散点图或箱线图"],
        notes=["注意样本量与分布假设"],
    )
