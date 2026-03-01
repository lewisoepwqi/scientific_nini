"""意图分析路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from nini.models.schemas import APIResponse

router = APIRouter()


@router.post("/intent/analyze", response_model=APIResponse)
async def analyze_intent(request: dict[str, Any]):
    """分析用户意图。"""
    from nini.intent import default_intent_analyzer

    query = request.get("query")
    context = request.get("context", {})

    if not query:
        raise HTTPException(status_code=400, detail="查询不能为空")

    try:
        result = await default_intent_analyzer.analyze(query, context)
        return APIResponse(success=True, data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"意图分析失败: {e}") from e


@router.get("/intent/status", response_model=APIResponse)
async def get_intent_status():
    """获取意图分析服务状态。"""
    from nini.intent import default_intent_analyzer

    return APIResponse(
        success=True,
        data={
            "initialized": default_intent_analyzer is not None,
            "status": "ready",
        },
    )
