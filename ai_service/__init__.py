"""
AI服务模块

提供科研数据分析的AI能力：
- 智能图表推荐
- AI辅助数据分析
- 实验设计助手
- 多组学数据分析
- Agent自动分析（预留）
"""

from ai_service.core.llm_client import (
    LLMClient,
    LLMConfig,
    ModelProvider,
    CostInfo,
    get_llm_client,
    reset_llm_client
)

from ai_service.core.prompts import (
    PromptManager,
    PromptTemplates,
    AnalysisType,
    get_prompt_manager
)

from ai_service.services.ai_analysis_service import (
    AIAnalysisService,
    get_ai_service,
    reset_ai_service
)

__all__ = [
    # LLM客户端
    "LLMClient",
    "LLMConfig", 
    "ModelProvider",
    "CostInfo",
    "get_llm_client",
    "reset_llm_client",
    
    # Prompt管理
    "PromptManager",
    "PromptTemplates",
    "AnalysisType",
    "get_prompt_manager",
    
    # AI服务
    "AIAnalysisService",
    "get_ai_service",
    "reset_ai_service",
]

__version__ = "0.1.0"
