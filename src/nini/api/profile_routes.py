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
    profile = await service.get_profile()

    return APIResponse(success=True, data=profile)


@router.put("/research-profile", response_model=APIResponse)
async def update_research_profile(request: ResearchProfileUpdateRequest):
    """更新用户研究画像。"""
    from nini.services.profile import ProfileService

    service = ProfileService()
    profile = await service.update_profile(request.model_dump(exclude_unset=True))

    return APIResponse(success=True, data=profile)


@router.get("/research-profile/narrative", response_model=APIResponse)
async def get_research_profile_narrative(profile_id: str = "default"):
    """获取研究画像 Markdown 叙述层内容。

    返回完整 MD 文件内容及各段落解析结果，供前端"研究日志"Tab 展示。
    """
    from nini.memory.profile_narrative import get_profile_narrative_manager

    manager = get_profile_narrative_manager()
    content = manager.read_narrative(profile_id)
    sections = manager.read_sections(profile_id)

    return APIResponse(
        success=True,
        data={
            "profile_id": profile_id,
            "content": content,
            "sections": {
                "auto": sections.get("研究偏好摘要", ""),
                "agent": sections.get("分析习惯与观察", ""),
                "user": sections.get("备注", ""),
            },
        },
    )


@router.get("/research-profile/prompt", response_model=APIResponse)
async def get_research_profile_prompt():
    """获取研究画像的系统提示词。"""
    from nini.services.profile import ProfileService

    service = ProfileService()
    prompt = await service.get_profile_prompt()

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
    await service.record_analysis(method, dataset_size)

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
    sections_markdown = "\n\n".join(f"## {section}\n" for section in request.sections)
    markdown = f"# {request.title}\n\n{sections_markdown}".strip() + "\n"
    return APIResponse(
        success=True,
        data={
            "title": request.title,
            "template": request.template,
            "detail_level": request.detail_level,
            "include_figures": request.include_figures,
            "include_tables": request.include_tables,
            "dataset_names": request.dataset_names or [],
            "markdown": markdown,
        },
    )


@router.post("/report/export", response_model=APIResponse)
async def export_report(request: ReportExportRequest):
    """导出报告。"""
    return APIResponse(
        success=False,
        error=(
            "报告导出接口待迁移，请使用 report_session + export_document 工作流。"
            f"当前请求参数: format={request.format}, report_id={request.report_id or ''}"
        ),
    )


@router.get("/report/preview", response_model=APIResponse)
async def preview_report(report_id: str):
    """预览报告。"""
    return APIResponse(
        success=False,
        error=f"报告预览接口待迁移，暂不支持 report_id={report_id}",
    )
