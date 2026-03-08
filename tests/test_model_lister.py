"""模型列表获取回归测试。"""

from __future__ import annotations

import pytest

from nini.agent.model_lister import list_available_models


@pytest.mark.asyncio
async def test_dashscope_coding_plan_returns_static_models_without_remote_call() -> None:
    """阿里 Coding Plan 不支持 /models，应直接回退官方静态模型列表。"""
    result = await list_available_models(
        provider_id="dashscope",
        api_key="sk-test",
        base_url="https://coding.dashscope.aliyuncs.com/v1",
    )

    assert result["source"] == "static"
    assert result["supports_remote_listing"] is False
    assert "qwen3-coder-plus" in result["models"]
    assert "qwen3-max-2026-01-23" in result["models"]
