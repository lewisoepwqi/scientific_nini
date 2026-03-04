"""意图分析路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from nini.models.schemas import APIResponse

router = APIRouter()


# 共享注册表缓存
_capability_registry = None


def _get_capability_registry():
    """获取或创建能力注册表。"""
    global _capability_registry
    if _capability_registry is None:
        from nini.capabilities import CapabilityRegistry, create_default_capabilities

        _capability_registry = CapabilityRegistry()
        for cap in create_default_capabilities():
            _capability_registry.register(cap)
    return _capability_registry


def _get_skill_registry():
    """获取全局技能注册表（从 WebSocket 模块）。"""
    from nini.api.websocket import get_skill_registry

    registry = get_skill_registry()
    if registry is None:
        raise HTTPException(status_code=503, detail="技能注册中心尚未初始化")
    return registry


@router.post("/intent/analyze", response_model=APIResponse)
async def analyze_intent(
    user_message: str = "",
    capabilities: list[dict[str, Any]] | None = None,
    semantic_skills: list[dict[str, Any]] | None = None,
    analysis_mode: str = "rule",
):
    """分析用户意图并返回结构化结果。

    请求参数:
        - user_message: 用户输入消息
        - capabilities: 可选的能力目录列表（默认使用系统 capabilities）
        - semantic_skills: 可选的语义技能目录列表（默认使用已加载的 skills）
        - analysis_mode: 分析模式（rule/hybrid，默认 rule）
    """
    from nini.intent import default_intent_analyzer

    # 如果没有提供 capabilities，使用默认 capabilities
    if capabilities is None:
        cap_registry = _get_capability_registry()
        capabilities = [cap.to_dict() for cap in cap_registry.list_capabilities()]

    # 如果没有提供 semantic_skills，从 skill registry 获取
    if semantic_skills is None:
        try:
            skill_registry = _get_skill_registry()
            semantic_skills = skill_registry.get_semantic_catalog()
        except Exception:
            semantic_skills = []

    if analysis_mode == "hybrid":
        # 使用增强版语义分析
        try:
            from nini.intent import get_enhanced_intent_analyzer

            enhanced = get_enhanced_intent_analyzer()

            # 先获取规则分析结果
            rule_analysis = default_intent_analyzer.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
            )

            # 应用语义增强
            analysis = enhanced.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
                rule_based_analysis=rule_analysis,
            )
        except Exception as exc:
            # 语义分析失败，回退到规则分析
            analysis = default_intent_analyzer.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
            )
    else:
        # 使用规则分析
        analysis = default_intent_analyzer.analyze(
            user_message,
            capabilities=capabilities,
            semantic_skills=semantic_skills,
        )

    return APIResponse(
        success=True,
        data=analysis.to_dict(),
    )


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
