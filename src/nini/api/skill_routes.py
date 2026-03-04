"""技能和工具路由（辅助模块）。

注意：本模块提供 /capabilities 路由的备用实现。主要路由逻辑由 routes.py 驱动，
通过 _get_skill_registry() 访问共享注册表。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from nini.models.schemas import APIResponse

router = APIRouter()


@router.get("/capabilities", response_model=APIResponse)
async def list_capabilities():
    """列出所有可用能力。"""
    from nini.capabilities.defaults import create_default_capabilities

    capabilities = create_default_capabilities()

    return APIResponse(
        success=True,
        data={
            "capabilities": [
                {
                    "name": c.name,
                    "display_name": c.display_name,
                    "description": c.description,
                    "icon": c.icon,
                    "is_executable": c.is_executable,
                    "execution_message": c.execution_message,
                    "required_tools": c.required_tools,
                }
                for c in capabilities
            ]
        },
    )


@router.get("/capabilities/{name}", response_model=APIResponse)
async def get_capability(name: str):
    """获取单个能力详情。"""
    from nini.capabilities.defaults import create_default_capabilities

    capabilities = {c.name: c for c in create_default_capabilities()}
    capability = capabilities.get(name)

    if not capability:
        raise HTTPException(status_code=404, detail="能力不存在")

    return APIResponse(
        success=True,
        data={
            "name": capability.name,
            "display_name": capability.display_name,
            "description": capability.description,
            "icon": capability.icon,
            "is_executable": capability.is_executable,
            "required_tools": capability.required_tools,
            "suggested_workflow": capability.suggested_workflow,
        },
    )
