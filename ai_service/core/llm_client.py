"""
LLM客户端封装模块
支持OpenAI API和本地模型部署
"""
import os
import asyncio
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import json

import openai
from openai import AsyncOpenAI


class ModelProvider(Enum):
    """模型提供商枚举"""
    OPENAI = "openai"
    AZURE = "azure"
    LOCAL = "local"  # 预留本地模型接口
    ANTHROPIC = "anthropic"  # 预留Claude接口


@dataclass
class LLMConfig:
    """LLM配置类"""
    provider: ModelProvider = ModelProvider.OPENAI
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.3  # 科研场景需要更稳定的输出
    max_tokens: int = 4096
    timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 成本相关配置
    enable_cost_tracking: bool = True
    
    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")


@dataclass
class CostInfo:
    """API调用成本信息"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    
    # OpenAI定价 (2024年，需要定期更新)
    PRICING = {
        "gpt-4": {"input": 0.03, "output": 0.06},  # per 1K tokens
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
    }
    
    def calculate_cost(self, model: str) -> float:
        """计算调用成本"""
        pricing = self.PRICING.get(model, self.PRICING["gpt-4"])
        input_cost = (self.input_tokens / 1000) * pricing["input"]
        output_cost = (self.output_tokens / 1000) * pricing["output"]
        self.cost_usd = input_cost + output_cost
        return self.cost_usd


class LLMClient:
    """
    LLM客户端类
    封装OpenAI API调用，支持流式响应、错误处理和重试
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.client = None
        self._init_client()
        
        # 成本统计
        self.total_cost = 0.0
        self.total_calls = 0
        self.cost_history: List[CostInfo] = []
    
    def _init_client(self):
        """初始化OpenAI客户端"""
        if self.config.provider == ModelProvider.OPENAI:
            client_kwargs = {"api_key": self.config.api_key}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
            self.client = AsyncOpenAI(**client_kwargs)
        else:
            # 预留其他提供商接口
            raise NotImplementedError(f"Provider {self.config.provider} not implemented yet")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        functions: Optional[List[Dict]] = None,
        function_call: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        非流式聊天完成
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            functions: 函数调用定义
            function_call: 函数调用模式
            
        Returns:
            完整的响应结果
        """
        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens
        
        for attempt in range(self.config.max_retries):
            try:
                kwargs = {
                    "model": self.config.model,
                    "messages": messages,
                    "temperature": temp,
                    "max_tokens": max_tok,
                }
                
                if functions:
                    kwargs["functions"] = functions
                    kwargs["function_call"] = function_call
                
                response = await self.client.chat.completions.create(**kwargs)
                
                # 记录成本
                if self.config.enable_cost_tracking:
                    cost_info = CostInfo(
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens
                    )
                    cost_info.calculate_cost(self.config.model)
                    self.cost_history.append(cost_info)
                    self.total_cost += cost_info.cost_usd
                    self.total_calls += 1
                
                return {
                    "content": response.choices[0].message.content,
                    "function_call": response.choices[0].message.function_call,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    },
                    "cost_usd": cost_info.cost_usd if self.config.enable_cost_tracking else 0
                }
                
            except openai.RateLimitError as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except (openai.APIError, openai.APITimeoutError) as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                raise
        
        raise Exception("Max retries exceeded")
    
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天完成
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Yields:
            流式响应的文本片段
        """
        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens
        
        for attempt in range(self.config.max_retries):
            try:
                stream = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tok,
                    stream=True
                )
                
                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                
                return
                
            except openai.RateLimitError as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except (openai.APIError, openai.APITimeoutError) as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                raise
        
        raise Exception("Max retries exceeded")
    
    async def chat_completion_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        带工具调用的聊天完成（用于Agent）
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            temperature: 温度参数
            
        Returns:
            包含工具调用的响应
        """
        temp = temperature if temperature is not None else self.config.temperature
        
        for attempt in range(self.config.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temp,
                    tools=tools,
                    tool_choice="auto"
                )
                
                message = response.choices[0].message
                
                # 记录成本
                if self.config.enable_cost_tracking:
                    cost_info = CostInfo(
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens
                    )
                    cost_info.calculate_cost(self.config.model)
                    self.cost_history.append(cost_info)
                    self.total_cost += cost_info.cost_usd
                    self.total_calls += 1
                
                result = {
                    "content": message.content,
                    "tool_calls": [],
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    },
                    "cost_usd": cost_info.cost_usd if self.config.enable_cost_tracking else 0
                }
                
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        result["tool_calls"].append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                
                return result
                
            except openai.RateLimitError as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except (openai.APIError, openai.APITimeoutError) as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                raise
        
        raise Exception("Max retries exceeded")
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """获取成本统计摘要"""
        return {
            "total_cost_usd": round(self.total_cost, 4),
            "total_calls": self.total_calls,
            "average_cost_per_call": round(self.total_cost / max(self.total_calls, 1), 4),
            "recent_calls": [
                {
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "cost_usd": round(c.cost_usd, 4)
                }
                for c in self.cost_history[-10:]  # 最近10次调用
            ]
        }
    
    def reset_cost_tracking(self):
        """重置成本统计"""
        self.total_cost = 0.0
        self.total_calls = 0
        self.cost_history = []


# 全局LLM客户端实例
_llm_client: Optional[LLMClient] = None


def get_llm_client(config: Optional[LLMConfig] = None) -> LLMClient:
    """获取全局LLM客户端实例（单例模式）"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(config)
    return _llm_client


def reset_llm_client():
    """重置全局LLM客户端实例"""
    global _llm_client
    _llm_client = None
