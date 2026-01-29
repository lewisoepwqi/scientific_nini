"""
AI分析服务
提供图表推荐、数据分析、实验设计等AI功能
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime

from ai_service.core.llm_client import LLMClient, LLMConfig, get_llm_client
from ai_service.core.prompts import (
    PromptManager, 
    AnalysisType, 
    get_prompt_manager
)


class AIAnalysisService:
    """
    AI分析服务类
    封装所有AI分析功能
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or get_llm_client()
        self.prompt_manager = get_prompt_manager()
    
    # ==================== 图表推荐 ====================
    
    async def recommend_chart(
        self,
        data_description: str,
        data_sample: str,
        data_types: Dict[str, str],
        statistics: Dict[str, Any],
        user_requirement: str = ""
    ) -> Dict[str, Any]:
        """
        智能图表推荐
        
        Args:
            data_description: 数据描述
            data_sample: 数据样本（前5行）
            data_types: 数据类型信息
            statistics: 统计分析信息
            user_requirement: 用户特殊需求
            
        Returns:
            图表推荐结果
        """
        prompts = self.prompt_manager.get_chart_recommendation_prompt(
            data_description=data_description,
            data_sample=data_sample,
            data_types=data_types,
            statistics=statistics,
            user_requirement=user_requirement
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        response = await self.llm.chat_completion(messages)
        
        # 解析JSON响应
        try:
            content = response["content"]
            # 提取JSON部分
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            
            result = json.loads(json_str.strip())
            result["cost_usd"] = response.get("cost_usd", 0)
            return result
            
        except json.JSONDecodeError as e:
            return {
                "error": "Failed to parse recommendation",
                "raw_response": response["content"],
                "cost_usd": response.get("cost_usd", 0)
            }
    
    async def recommend_chart_stream(
        self,
        data_description: str,
        data_sample: str,
        data_types: Dict[str, str],
        statistics: Dict[str, Any],
        user_requirement: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        流式图表推荐
        
        Yields:
            JSON格式的推荐结果片段
        """
        prompts = self.prompt_manager.get_chart_recommendation_prompt(
            data_description=data_description,
            data_sample=data_sample,
            data_types=data_types,
            statistics=statistics,
            user_requirement=user_requirement
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        async for chunk in self.llm.chat_completion_stream(messages):
            yield chunk
    
    # ==================== 数据分析 ====================
    
    async def analyze_data(
        self,
        context: str,
        data_description: str,
        statistics: Dict[str, Any],
        question: str = ""
    ) -> Dict[str, Any]:
        """
        AI辅助数据分析
        
        Args:
            context: 数据背景
            data_description: 数据描述
            statistics: 统计分析结果
            question: 用户具体问题
            
        Returns:
            分析结果
        """
        prompts = self.prompt_manager.get_data_analysis_prompt(
            context=context,
            data_description=data_description,
            statistics=statistics,
            question=question
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        response = await self.llm.chat_completion(messages)
        
        return {
            "analysis": response["content"],
            "cost_usd": response.get("cost_usd", 0),
            "usage": response.get("usage", {})
        }
    
    async def analyze_data_stream(
        self,
        context: str,
        data_description: str,
        statistics: Dict[str, Any],
        question: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        流式数据分析
        
        Yields:
            分析文本片段
        """
        prompts = self.prompt_manager.get_data_analysis_prompt(
            context=context,
            data_description=data_description,
            statistics=statistics,
            question=question
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        async for chunk in self.llm.chat_completion_stream(messages):
            yield chunk
    
    # ==================== 实验设计 ====================
    
    async def design_experiment(
        self,
        background: str,
        objective: str,
        study_type: str,
        primary_endpoint: str,
        effect_size: float,
        alpha: float = 0.05,
        power: float = 0.8,
        test_type: str = "two-sided",
        num_groups: int = 2,
        additional_info: str = ""
    ) -> Dict[str, Any]:
        """
        实验设计助手
        
        Args:
            background: 研究背景
            objective: 研究目的
            study_type: 研究类型
            primary_endpoint: 主要终点指标
            effect_size: 预期效应量
            alpha: 显著性水平
            power: 统计功效
            test_type: 检验类型
            num_groups: 分组数
            additional_info: 其他信息
            
        Returns:
            实验设计建议
        """
        prompts = self.prompt_manager.get_experiment_design_prompt(
            background=background,
            objective=objective,
            study_type=study_type,
            primary_endpoint=primary_endpoint,
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            test_type=test_type,
            num_groups=num_groups,
            additional_info=additional_info
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        response = await self.llm.chat_completion(messages)
        
        return {
            "design": response["content"],
            "cost_usd": response.get("cost_usd", 0),
            "usage": response.get("usage", {})
        }
    
    async def design_experiment_stream(
        self,
        background: str,
        objective: str,
        study_type: str,
        primary_endpoint: str,
        effect_size: float,
        alpha: float = 0.05,
        power: float = 0.8,
        test_type: str = "two-sided",
        num_groups: int = 2,
        additional_info: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        流式实验设计
        
        Yields:
            设计建议文本片段
        """
        prompts = self.prompt_manager.get_experiment_design_prompt(
            background=background,
            objective=objective,
            study_type=study_type,
            primary_endpoint=primary_endpoint,
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            test_type=test_type,
            num_groups=num_groups,
            additional_info=additional_info
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        async for chunk in self.llm.chat_completion_stream(messages):
            yield chunk
    
    # ==================== 统计建议 ====================
    
    async def get_statistical_advice(
        self,
        analysis_goal: str,
        data_description: str,
        variable_info: Dict[str, Any],
        sample_size: int,
        distribution_info: Dict[str, Any],
        special_requirements: str = ""
    ) -> Dict[str, Any]:
        """
        获取统计方法建议
        
        Args:
            analysis_goal: 分析目标
            data_description: 数据描述
            variable_info: 变量信息
            sample_size: 样本量
            distribution_info: 分布信息
            special_requirements: 特殊需求
            
        Returns:
            统计方法建议
        """
        prompts = self.prompt_manager.get_prompt(
            AnalysisType.STATISTICAL_ADVICE,
            user_vars={
                "analysis_goal": analysis_goal,
                "data_description": data_description,
                "variable_info": self.prompt_manager._format_dict(variable_info),
                "sample_size": sample_size,
                "distribution_info": self.prompt_manager._format_dict(distribution_info),
                "special_requirements": special_requirements or "无"
            }
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        response = await self.llm.chat_completion(messages)
        
        return {
            "advice": response["content"],
            "cost_usd": response.get("cost_usd", 0),
            "usage": response.get("usage", {})
        }
    
    # ==================== 多组学分析 ====================
    
    async def analyze_omics(
        self,
        omics_type: str,
        data_description: str,
        sample_info: Dict[str, Any],
        analysis_goal: str,
        completed_analysis: str = "",
        specific_questions: str = ""
    ) -> Dict[str, Any]:
        """
        多组学数据分析
        
        Args:
            omics_type: 组学数据类型
            data_description: 数据描述
            sample_info: 样本信息
            analysis_goal: 分析目标
            completed_analysis: 已完成的分析
            specific_questions: 具体问题
            
        Returns:
            分析建议
        """
        prompts = self.prompt_manager.get_prompt(
            AnalysisType.OMICS_ANALYSIS,
            user_vars={
                "omics_type": omics_type,
                "data_description": data_description,
                "sample_info": self.prompt_manager._format_dict(sample_info),
                "analysis_goal": analysis_goal,
                "completed_analysis": completed_analysis or "无",
                "specific_questions": specific_questions or "无"
            }
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]}
        ]
        
        response = await self.llm.chat_completion(messages)
        
        return {
            "analysis": response["content"],
            "cost_usd": response.get("cost_usd", 0),
            "usage": response.get("usage", {})
        }
    
    # ==================== 成本管理 ====================
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """获取成本统计摘要"""
        return self.llm.get_cost_summary()
    
    def reset_cost_tracking(self):
        """重置成本统计"""
        self.llm.reset_cost_tracking()


# ==================== 便捷函数 ====================

_ai_service: Optional[AIAnalysisService] = None


def get_ai_service(llm_client: Optional[LLMClient] = None) -> AIAnalysisService:
    """获取全局AI服务实例"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIAnalysisService(llm_client)
    return _ai_service


def reset_ai_service():
    """重置全局AI服务实例"""
    global _ai_service
    _ai_service = None
