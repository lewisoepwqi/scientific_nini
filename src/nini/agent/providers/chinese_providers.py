"""Chinese LLM Providers.

Moonshot, Kimi Coding, Zhipu, DeepSeek, DashScope, MiniMax adapters.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from nini.config import settings

from .base import LLMChunk
from .base import match_first_model
from .openai_provider import OpenAICompatibleClient


class MoonshotClient(OpenAICompatibleClient):
    """Moonshot AI (Kimi) 适配器，兼容 OpenAI 协议。"""

    provider_id = "moonshot"
    provider_name = "Moonshot AI (Kimi)"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.moonshot_api_key,
            base_url=base_url or "https://api.moonshot.cn/v1",
            model=model or settings.moonshot_model,
        )

    def _supports_stream_usage(self) -> bool:
        # Moonshot API 不支持 stream_options.include_usage
        return False

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("-8k",), ("-32k",), ("kimi", "chat")],
        )

    def _normalize_messages_for_provider(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized = super()._normalize_messages_for_provider(messages)
        for message in normalized:
            if message.get("role") == "assistant" and message.get("tool_calls"):
                # kimi-k2.5 在 thinking 模式下会校验该字段是否存在。
                message.setdefault("reasoning_content", "")
        return normalized

    @staticmethod
    def _sanitize_tools_for_moonshot(
        tools: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]] | None:
        """适配 Moonshot 的 anyOf 校验。

        Moonshot 拒绝在含 ``anyOf`` 的父 schema 上声明 ``type``，要求 ``type``
        写在每个 anyOf 项内（错误信息：``when using anyOf, type should be
        defined in anyOf items instead of the parent schema``）。本函数递归
        将父级 ``type`` 下放到每个未声明 ``type`` 的 anyOf 项中，并从父级
        移除 ``type``，使其它 provider 通用的 JSON Schema 也能被 Moonshot 接受。
        """
        if not tools:
            return tools

        def fix(node: Any) -> Any:
            if isinstance(node, dict):
                new_node: dict[str, Any] = {k: fix(v) for k, v in node.items()}
                any_of = new_node.get("anyOf")
                parent_type = new_node.get("type")
                if isinstance(any_of, list) and parent_type is not None:
                    fixed_items: list[Any] = []
                    for item in any_of:
                        if isinstance(item, dict) and "type" not in item:
                            fixed_items.append({"type": parent_type, **item})
                        else:
                            fixed_items.append(item)
                    new_node["anyOf"] = fixed_items
                    new_node.pop("type", None)
                return new_node
            if isinstance(node, list):
                return [fix(v) for v in node]
            return node

        return [fix(tool) for tool in tools]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMChunk, None]:
        """Kimi 模型流式聊天，处理 temperature 限制。"""
        # kimi-k2.5 等模型只支持 temperature=1
        model = self._model or ""
        if "k2.5" in model:
            temperature = 1.0
        sanitized_tools = self._sanitize_tools_for_moonshot(tools)
        async for chunk in super().chat(
            messages, sanitized_tools, temperature=temperature, max_tokens=max_tokens
        ):
            yield chunk


class KimiCodingClient(OpenAICompatibleClient):
    """Kimi Coding Plan 适配器（api.kimi.com），兼容 OpenAI 协议。

    Kimi Coding API 通过 User-Agent 头识别编码工具客户端，
    未携带合法标识会返回 403 access_terminated_error。
    """

    provider_id = "kimi_coding"
    provider_name = "Kimi Coding"

    # Kimi 白名单校验所需的 User-Agent 标识
    _USER_AGENT = "ClaudeCode/1.0.0"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key or settings.kimi_coding_api_key,
            base_url=base_url or settings.kimi_coding_base_url,
            model=model or settings.kimi_coding_model,
        )

    def _ensure_client(self) -> None:
        if self._client is None:
            from openai import AsyncOpenAI, DefaultAsyncHttpxClient

            kwargs: dict[str, Any] = {"api_key": self._api_key}
            kwargs["max_retries"] = max(0, int(settings.llm_max_retries))
            kwargs["timeout"] = max(1, int(settings.llm_timeout))
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._http_client is None:
                self._http_client = DefaultAsyncHttpxClient(trust_env=settings.llm_trust_env_proxy)
            kwargs["http_client"] = self._http_client
            kwargs["default_headers"] = {
                "User-Agent": self._USER_AGENT,
                "X-Title": "Nini",
            }
            self._client = AsyncOpenAI(**kwargs)

    def _supports_stream_usage(self) -> bool:
        # Kimi Coding API 不支持 stream_options.include_usage
        return False


class ZhipuClient(OpenAICompatibleClient):
    """智谱 AI (GLM) 适配器，兼容 OpenAI 协议。

    默认使用 Coding Plan 端点 (open.bigmodel.cn/api/coding/paas/v4)，
    与标准 API 端点共用同一 API Key，但计费走 Coding 订阅通道。
    """

    provider_id = "zhipu"
    provider_name = "智谱 AI (GLM)"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.zhipu_api_key,
            base_url=base_url or settings.zhipu_base_url,
            model=model or settings.zhipu_model,
        )

    def _supports_stream_usage(self) -> bool:
        # 智谱 Coding Plan 端点不支持 stream_options.include_usage
        return False

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("glm-4-flash",), ("glm-4-air",), ("glm-4",)],
        )

    def _normalize_messages_for_provider(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """智谱 Coding Plan 端点对 tool 历史兼容性较差，统一降级为纯文本上下文。

        处理策略：
        - assistant + tool_calls → 仅保留文本，丢弃 tool_calls（防止 GLM-5 模仿生成纯文本调用）
        - tool (工具结果)       → 转换为 user 消息（工具结果是环境观测值，语义上属于外部输入）
          使用 user 而非 assistant，使 ReAct 轨迹形成 assistant→user 交替结构，
          满足 GLM-5 对消息序列合法性的要求（不允许连续相同角色）
        - 最终应用 _fix_consecutive_roles 合并相邻同角色消息，确保序列合法
        """
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "").strip()
            content = "" if message.get("content") is None else str(message.get("content"))

            if role == "assistant" and message.get("tool_calls"):
                # 不注入历史工具调用/结果文本标签：注入 "[历史工具调用]" 或 "[历史工具结果]"
                # 格式会导致 GLM-5 通过上下文模仿学习到该格式，下一轮用纯文本输出"工具调用/结果"
                # 而非真正的 function call，从而使 ReAct 循环提前退出。
                # 工具的执行结果已通过后续 tool_result 消息提供，模型无需再看调用指令。
                stripped = content.strip()
                if stripped:
                    normalized.append({"role": "assistant", "content": stripped})
                continue

            if role == "tool":
                # 工具结果作为"环境观测"归入 user 角色，使 ReAct 轨迹形成合法的 assistant→user 交替
                normalized.append(
                    {
                        "role": "user",
                        "content": self._summarize_tool_result(content),
                    }
                )
                continue

            if role in {"system", "user", "assistant"}:
                normalized.append({"role": role, "content": content})

        # 合并相邻同角色消息，消除 context_builder 注入的多条连续 assistant 消息
        normalized = self._fix_consecutive_roles(normalized)

        # 确保 system 后至少有一条 user 消息（GLM-5 要求序列必须含 user）
        has_user = any(m.get("role") == "user" for m in normalized)
        if not has_user:
            insert_pos = next(
                (i for i, m in enumerate(normalized) if m.get("role") != "system"),
                len(normalized),
            )
            normalized.insert(insert_pos, {"role": "user", "content": "请继续。"})

        return normalized

    @staticmethod
    def _fix_consecutive_roles(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """合并相邻同角色的消息（system 除外），消除连续相同角色导致的 API 校验失败。"""
        merged: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            content = str(msg.get("content") or "")
            if merged and merged[-1].get("role") == role and role != "system":
                prev_content = str(merged[-1].get("content") or "")
                merged[-1]["content"] = (
                    (prev_content + "\n\n" + content).strip() if prev_content else content
                )
            else:
                merged.append(dict(msg))
        return merged

    @staticmethod
    def _summarize_tool_calls(tool_calls: Any) -> str:
        """将历史 tool_calls 压成智谱可接受的简短文本。"""
        if not isinstance(tool_calls, list):
            return ""

        lines: list[str] = ["[历史工具调用]"]
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function_raw = tool_call.get("function")
            if not isinstance(function_raw, dict):
                continue

            name = str(function_raw.get("name") or "").strip() or "unknown_tool"
            arguments = function_raw.get("arguments")
            if arguments is None:
                arguments_text = ""
            elif isinstance(arguments, str):
                arguments_text = arguments
            else:
                arguments_text = json.dumps(arguments, ensure_ascii=False, default=str)

            if len(arguments_text) > 600:
                arguments_text = arguments_text[:600] + "...(截断)"
            lines.append(f"- {name}: {arguments_text}")

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _summarize_tool_result(content: str) -> str:
        """压缩历史工具结果，避免将完整结构再次送入智谱校验。"""
        compact = content.strip()
        if len(compact) > 1200:
            compact = compact[:1200] + "...(截断)"
        return compact  # 不加 [历史工具结果] 前缀，防止 GLM-5 模仿学习


class DeepSeekClient(OpenAICompatibleClient):
    """DeepSeek 适配器，兼容 OpenAI 协议。"""

    provider_id = "deepseek"
    provider_name = "DeepSeek"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
            model=model or settings.deepseek_model,
        )

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("deepseek-chat",)],
        )


class DashScopeClient(OpenAICompatibleClient):
    """阿里百炼（通义千问）适配器，兼容 OpenAI 协议。"""

    provider_id = "dashscope"
    provider_name = "阿里百炼（通义千问）"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.dashscope_api_key,
            base_url=base_url or settings.dashscope_base_url,
            model=model or settings.dashscope_model,
        )

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("qwen-turbo",), ("qwen-plus",)],
        )


class MiniMaxClient(OpenAICompatibleClient):
    """MiniMax 文本模型适配器，兼容 OpenAI 协议。"""

    provider_id = "minimax"
    provider_name = "MiniMax"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.minimax_api_key,
            base_url=base_url or settings.minimax_base_url,
            model=model or settings.minimax_model,
        )

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("abab",), ("m2.1",), ("m2.5",)],
        )
