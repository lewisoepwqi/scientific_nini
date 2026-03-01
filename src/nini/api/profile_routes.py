"""用户画像和报告路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from nini.models.schemas import (
    APIResponse,
    ReportExportRequest,
    ReportGenerateRequest,
    ResearchProfileData,
    ResearchProfileUpdateRequest,
)

router = APIRouter()


@router.get("/research-profile", response_model=APIResponse)
async def get_research_profile():
    """获取用户研究画像。"""
    from nini.services.profile import ProfileService

    service = ProfileService()
    profile = service.get_profile()

    return APIResponse(success=True, data=profile)


@router.put("/research-profile", response_model=APIResponse)
async def update_research_profile(request: ResearchProfileUpdateRequest):
    """更新用户研究画像。"""
    from nini.services.profile import ProfileService

    service = ProfileService()
    profile = service.update_profile(request.dict(exclude_unset=True))

    return APIResponse(success=True, data=profile)


@router.get("/research-profile/prompt", response_model=APIResponse)
async def get_research_profile_prompt():
    """获取研究画像的系统提示词。"""
    from nini.services.profile import ProfileService

    service = ProfileService()
    prompt = service.get_profile_prompt()

    return APIResponse(success=True, data={"prompt": prompt})


@router.post("/research-profile/record-analysis", response_model=APIResponse)
async def record_analysis(request: dict[str, Any]):
    """记录分析历史到画像。"""
    from nini.services.profile import ProfileService

    method = request.get("method")
    dataset_size = request.get("dataset_size", 0)

    if not method:
        raise HTTPException(status_code=400, detail="方法不能为空")

    service = ProfileService()
    service.record_analysis(method, dataset_size)

    return APIResponse(success=True)


@router.get("/report/templates", response_model=APIResponse)
async def list_report_templates():
    """列出报告模板。"""
    templates = [
        {
            "id": "apa",
            "name": "APA 格式",
            "description": "符合 APA 第7版标准的学术报告格式",
        },
        {
            "id": "compact",
            "name": "简洁报告",
            "description": "适合快速查阅的简洁格式",
        },
        {
            "id": "detailed",
            "name": "详细报告",
            "description": "包含完整分析过程和图表的详细格式",
        },
    ]

    return APIResponse(success=True, data=templates)


@router.post("/report/generate", response_model=APIResponse)
async def generate_report(request: ReportGenerateRequest):
    """生成分析报告。"""
    from nini.tools.report import generate_analysis_report

    try:
        report = generate_analysis_report(
            title=request.title,
            content=request.content,
            template=request.template,
        )
        return APIResponse(success=True, data=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成报告失败: {e}") from e


@router.post("/report/export", response_model=APIResponse)
async def export_report(request: ReportExportRequest):
    """导出报告。"""
    from nini.tools.report import export_report

    try:
        result = export_report(
            report_id=request.report_id,
            format=request.format,
        )
        return APIResponse(success=True, data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出报告失败: {e}") from e


@router.get("/report/preview", response_model=APIResponse)
async def preview_report(report_id: str):
    """预览报告。"""
    from nini.tools.report import get_report_preview

    try:
        preview = get_report_preview(report_id)
        return APIResponse(success=True, data=preview)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"报告不存在: {e}") from e
