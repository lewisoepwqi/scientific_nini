"""
FastAPI端点定义
AI分析服务的REST API接口
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
import json
import asyncio

from ai_service.services.ai_analysis_service import (
    AIAnalysisService, 
    get_ai_service
)


router = APIRouter(prefix="/api/ai", tags=["AI Analysis"])


# ==================== 请求模型 ====================

class ChartRecommendationRequest(BaseModel):
    """图表推荐请求"""
    data_description: str = Field(..., description="数据描述")
    data_sample: str = Field(..., description="数据样本（前5行）")
    data_types: Dict[str, str] = Field(..., description="数据类型信息")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="统计分析信息")
    user_requirement: str = Field(default="", description="用户特殊需求")


class DataAnalysisRequest(BaseModel):
    """数据分析请求"""
    context: str = Field(..., description="数据背景")
    data_description: str = Field(..., description="数据描述")
    statistics: Dict[str, Any] = Field(..., description="统计分析结果")
    question: str = Field(default="", description="用户具体问题")


class ExperimentDesignRequest(BaseModel):
    """实验设计请求"""
    background: str = Field(..., description="研究背景")
    objective: str = Field(..., description="研究目的")
    study_type: str = Field(..., description="研究类型")
    primary_endpoint: str = Field(..., description="主要终点指标")
    effect_size: float = Field(..., description="预期效应量")
    alpha: float = Field(default=0.05, description="显著性水平")
    power: float = Field(default=0.8, description="统计功效")
    test_type: str = Field(default="two-sided", description="检验类型")
    num_groups: int = Field(default=2, description="分组数")
    additional_info: str = Field(default="", description="其他信息")


class StatisticalAdviceRequest(BaseModel):
    """统计建议请求"""
    analysis_goal: str = Field(..., description="分析目标")
    data_description: str = Field(..., description="数据描述")
    variable_info: Dict[str, Any] = Field(..., description="变量信息")
    sample_size: int = Field(..., description="样本量")
    distribution_info: Dict[str, Any] = Field(default_factory=dict, description="分布信息")
    special_requirements: str = Field(default="", description="特殊需求")


class OmicsAnalysisRequest(BaseModel):
    """多组学分析请求"""
    omics_type: str = Field(..., description="组学数据类型")
    data_description: str = Field(..., description="数据描述")
    sample_info: Dict[str, Any] = Field(..., description="样本信息")
    analysis_goal: str = Field(..., description="分析目标")
    completed_analysis: str = Field(default="", description="已完成的分析")
    specific_questions: str = Field(default="", description="具体问题")


class ChatRequest(BaseModel):
    """通用聊天请求"""
    messages: List[Dict[str, str]] = Field(..., description="消息列表")
    temperature: Optional[float] = Field(default=None, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, description="最大token数")
    stream: bool = Field(default=False, description="是否流式输出")


# ==================== 响应模型 ====================

class ChartRecommendationResponse(BaseModel):
    """图表推荐响应"""
    primary_recommendation: Dict[str, Any]
    alternative_options: List[Dict[str, Any]]
    visualization_tips: List[str]
    pitfalls_to_avoid: List[str]
    interactive_suggestions: List[str]
    cost_usd: float


class DataAnalysisResponse(BaseModel):
    """数据分析响应"""
    analysis: str
    cost_usd: float
    usage: Dict[str, int]


class ExperimentDesignResponse(BaseModel):
    """实验设计响应"""
    design: str
    cost_usd: float
    usage: Dict[str, int]


class CostSummaryResponse(BaseModel):
    """成本统计响应"""
    total_cost_usd: float
    total_calls: int
    average_cost_per_call: float
    recent_calls: List[Dict[str, Any]]


# ==================== 依赖注入 ====================

async def get_service() -> AIAnalysisService:
    """获取AI服务实例"""
    return get_ai_service()


# ==================== 端点定义 ====================

@router.post("/chart/recommend", response_model=ChartRecommendationResponse)
async def recommend_chart(
    request: ChartRecommendationRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    智能图表推荐
    
    分析数据特征，推荐最适合的可视化方案
    """
    try:
        result = await service.recommend_chart(
            data_description=request.data_description,
            data_sample=request.data_sample,
            data_types=request.data_types,
            statistics=request.statistics,
            user_requirement=request.user_requirement
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chart/recommend/stream")
async def recommend_chart_stream(
    request: ChartRecommendationRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    流式图表推荐
    
    实时返回推荐结果
    """
    async def generate():
        try:
            async for chunk in service.recommend_chart_stream(
                data_description=request.data_description,
                data_sample=request.data_sample,
                data_types=request.data_types,
                statistics=request.statistics,
                user_requirement=request.user_requirement
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/data/analyze", response_model=DataAnalysisResponse)
async def analyze_data(
    request: DataAnalysisRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    AI辅助数据分析
    
    提供数据解读和洞察
    """
    try:
        result = await service.analyze_data(
            context=request.context,
            data_description=request.data_description,
            statistics=request.statistics,
            question=request.question
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/analyze/stream")
async def analyze_data_stream(
    request: DataAnalysisRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    流式数据分析
    
    实时返回分析结果
    """
    async def generate():
        try:
            async for chunk in service.analyze_data_stream(
                context=request.context,
                data_description=request.data_description,
                statistics=request.statistics,
                question=request.question
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/experiment/design", response_model=ExperimentDesignResponse)
async def design_experiment(
    request: ExperimentDesignRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    实验设计助手
    
    提供样本量计算、实验设计优化等建议
    """
    try:
        result = await service.design_experiment(
            background=request.background,
            objective=request.objective,
            study_type=request.study_type,
            primary_endpoint=request.primary_endpoint,
            effect_size=request.effect_size,
            alpha=request.alpha,
            power=request.power,
            test_type=request.test_type,
            num_groups=request.num_groups,
            additional_info=request.additional_info
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiment/design/stream")
async def design_experiment_stream(
    request: ExperimentDesignRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    流式实验设计
    
    实时返回设计建议
    """
    async def generate():
        try:
            async for chunk in service.design_experiment_stream(
                background=request.background,
                objective=request.objective,
                study_type=request.study_type,
                primary_endpoint=request.primary_endpoint,
                effect_size=request.effect_size,
                alpha=request.alpha,
                power=request.power,
                test_type=request.test_type,
                num_groups=request.num_groups,
                additional_info=request.additional_info
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/statistical/advice")
async def get_statistical_advice(
    request: StatisticalAdviceRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    统计方法建议
    
    推荐最适合的统计分析方法
    """
    try:
        result = await service.get_statistical_advice(
            analysis_goal=request.analysis_goal,
            data_description=request.data_description,
            variable_info=request.variable_info,
            sample_size=request.sample_size,
            distribution_info=request.distribution_info,
            special_requirements=request.special_requirements
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/omics/analyze")
async def analyze_omics(
    request: OmicsAnalysisRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    多组学数据分析
    
    提供组学数据分析建议
    """
    try:
        result = await service.analyze_omics(
            omics_type=request.omics_type,
            data_description=request.data_description,
            sample_info=request.sample_info,
            analysis_goal=request.analysis_goal,
            completed_analysis=request.completed_analysis,
            specific_questions=request.specific_questions
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat(
    request: ChatRequest,
    service: AIAnalysisService = Depends(get_service)
):
    """
    通用聊天接口
    
    支持流式和非流式输出
    """
    if request.stream:
        async def generate():
            try:
                async for chunk in service.llm.chat_completion_stream(
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens
                ):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        try:
            result = await service.llm.chat_completion(
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    service: AIAnalysisService = Depends(get_service)
):
    """
    获取API调用成本统计
    
    返回累计成本和调用统计
    """
    return service.get_cost_summary()


@router.post("/cost/reset")
async def reset_cost_tracking(
    service: AIAnalysisService = Depends(get_service)
):
    """
    重置成本统计
    """
    service.reset_cost_tracking()
    return {"message": "Cost tracking reset successfully"}


# ==================== 健康检查 ====================

@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "ai-analysis"}
