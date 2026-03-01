"""LLM Provider Adapters.

Unified adapters for OpenAI, Anthropic, Ollama, and Chinese LLM providers.
"""

from __future__ import annotations

from .base import BaseLLMClient, LLMChunk, LLMResponse, PurposeRoute, ReasoningStreamParser
from .openai_provider import OpenAIClient, OpenAICompatibleClient
from .anthropic_provider import AnthropicClient
from .ollama_provider import OllamaClient
from .chinese_providers import (
    MoonshotClient,
    KimiCodingClient,
    ZhipuClient,
    DeepSeekClient,
    DashScopeClient,
    MiniMaxClient,
)

__all__ = [
    # Base
    "BaseLLMClient",
    "LLMChunk",
    "LLMResponse",
    "PurposeRoute",
    "ReasoningStreamParser",
    # OpenAI compatible
    "OpenAICompatibleClient",
    "OpenAIClient",
    # Anthropic
    "AnthropicClient",
    # Local
    "OllamaClient",
    # Chinese providers
    "MoonshotClient",
    "KimiCodingClient",
    "ZhipuClient",
    "DeepSeekClient",
    "DashScopeClient",
    "MiniMaxClient",
]
