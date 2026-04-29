"""Provider 标题模型偏好测试。"""

from __future__ import annotations

import pytest

from nini.agent.providers import (
    AnthropicClient,
    DashScopeClient,
    DeepSeekClient,
    MiniMaxClient,
    MoonshotClient,
    OllamaClient,
    OpenAIClient,
    ZhipuClient,
)
from nini.agent.providers.base import match_first_model


def test_match_first_model_prefers_earliest_keyword_group() -> None:
    """匹配器应按偏好组顺序返回第一个命中的模型。"""
    selected = match_first_model(
        ["qwen-max", "qwen-turbo-latest", "qwen-plus"],
        [("turbo",), ("plus",)],
    )

    assert selected == "qwen-turbo-latest"


@pytest.mark.parametrize(
    ("client", "available_models", "expected_model"),
    [
        (
            DeepSeekClient(api_key="sk-test", model="deepseek-coder"),
            ["deepseek-reasoner", "deepseek-chat"],
            "deepseek-chat",
        ),
        (
            ZhipuClient(api_key="sk-test", model="glm-5"),
            ["glm-4", "glm-4-air", "glm-4-flash"],
            "glm-4-flash",
        ),
        (
            DashScopeClient(api_key="sk-test", model="qwen-plus"),
            ["qwen-max", "qwen-plus", "qwen-turbo"],
            "qwen-turbo",
        ),
        (
            OpenAIClient(api_key="sk-test", model="gpt-4o"),
            ["gpt-4o", "gpt-4.1-mini"],
            "gpt-4.1-mini",
        ),
        (
            AnthropicClient(api_key="sk-test", model="claude-3-5-sonnet"),
            ["claude-3-haiku-20240307", "claude-3-5-sonnet-20241022"],
            "claude-3-haiku-20240307",
        ),
        (
            MoonshotClient(api_key="sk-test", model="moonshot-v1-32k"),
            ["moonshot-v1-128k", "moonshot-v1-8k", "kimi-chat"],
            "moonshot-v1-8k",
        ),
        (
            MiniMaxClient(api_key="sk-test", model="abab6-chat"),
            ["minimax-text-01", "abab7-chat-preview", "minimax-m2.5-chat"],
            "abab7-chat-preview",
        ),
        (
            OllamaClient(base_url="http://localhost:11434", model="qwen2.5:latest"),
            ["qwen2.5:latest", "llama3.1:8b"],
            None,
        ),
    ],
)
def test_provider_pick_model_for_title_generation(
    client: object,
    available_models: list[str],
    expected_model: str | None,
) -> None:
    """各 provider 应返回约定的标题模型偏好。"""
    setattr(client, "_available_models_cache", available_models)

    assert client.pick_model_for_purpose("title_generation") == expected_model


@pytest.mark.parametrize(
    "client",
    [
        DeepSeekClient(api_key="sk-test", model="deepseek-coder"),
        ZhipuClient(api_key="sk-test", model="glm-5"),
        DashScopeClient(api_key="sk-test", model="qwen-plus"),
        OpenAIClient(api_key="sk-test", model="gpt-4o"),
        AnthropicClient(api_key="sk-test", model="claude-3-5-sonnet"),
        MoonshotClient(api_key="sk-test", model="moonshot-v1-32k"),
        MiniMaxClient(api_key="sk-test", model="abab6-chat"),
        OllamaClient(base_url="http://localhost:11434", model="qwen2.5:latest"),
    ],
)
def test_provider_pick_model_returns_none_for_non_title_purpose(client: object) -> None:
    """非标题用途不应触发轻量模型偏好。"""
    setattr(client, "_available_models_cache", ["whatever-model"])

    assert client.pick_model_for_purpose("chat") is None


def test_provider_pick_model_returns_none_when_preferred_models_missing() -> None:
    """可用模型不命中偏好列表时，应回退主模型。"""
    client = DashScopeClient(api_key="sk-test", model="qwen-plus")
    setattr(client, "_available_models_cache", ["qwen-max"])

    assert client.pick_model_for_purpose("title_generation") is None
