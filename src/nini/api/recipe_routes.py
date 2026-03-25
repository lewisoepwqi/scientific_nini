"""Recipe Center 相关接口。"""

from __future__ import annotations

from fastapi import APIRouter

from nini.models.schemas import APIResponse
from nini.recipe import get_recipe_registry

router = APIRouter(prefix="/recipes")


@router.get("", response_model=APIResponse)
async def list_recipes() -> APIResponse:
    """返回 Recipe Center 所需的模板元数据。"""
    registry = get_recipe_registry()
    return APIResponse(success=True, data={"recipes": registry.list_public()})
