"""MemoryManager：编排内置 Provider 与可选外部 Provider 的生命周期。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from nini.memory.provider import MemoryProvider

logger = logging.getLogger(__name__)

_FENCE_TAG_RE = re.compile(r"</?\s*memory-context\s*>", re.IGNORECASE)


def sanitize_context(text: str) -> str:
    """移除 fence 转义序列，防止 Provider 输出的文本注入 fencing 结构。"""
    return _FENCE_TAG_RE.sub("", text)


def build_memory_context_block(raw_context: str) -> str:
    """将召回记忆包裹在 fence 标签内，防止 LLM 把历史记忆误当当前输入。"""
    if not raw_context or not raw_context.strip():
        return ""
    clean = sanitize_context(raw_context)
    return (
        "<memory-context>\n"
        "[系统注记：以下是召回的记忆上下文，非用户新输入，仅作参考背景。]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )


class MemoryManager:
    """编排所有 MemoryProvider 的生命周期。

    支持 1 个内置 Provider（name='builtin'）和任意数量外部 Provider。
    Provider 间完全异常隔离：任何 Provider 的任何钩子抛出异常，
    仅记录警告，不影响其他 Provider 和 agent 主循环。
    """

    def __init__(self) -> None:
        self._providers: list[MemoryProvider] = []
        self._tool_to_provider: dict[str, MemoryProvider] = {}

    @property
    def providers(self) -> list[MemoryProvider]:
        return list(self._providers)

    def add_provider(self, provider: MemoryProvider) -> None:
        """注册 Provider（允许任意数量）。"""
        self._providers.append(provider)
        for schema in provider.get_tool_schemas():
            tool_name = schema.get("name", "")
            if tool_name and tool_name not in self._tool_to_provider:
                self._tool_to_provider[tool_name] = provider
        logger.info(
            "Memory Provider '%s' 已注册（%d 个工具）",
            provider.name,
            len(provider.get_tool_schemas()),
        )

    def build_system_prompt(self) -> str:
        """收集所有 Provider 的 system prompt 块。"""
        blocks: list[str] = []
        for provider in self._providers:
            try:
                block = provider.system_prompt_block()
                if block and block.strip():
                    blocks.append(block)
            except Exception as exc:
                logger.warning("Provider '%s' system_prompt_block 失败: %s", provider.name, exc)
        return "\n\n".join(blocks)

    async def prefetch_all(self, query: str, *, session_id: str = "") -> str:
        """汇总所有 Provider 的召回结果（原始文本，不含 fencing）。"""
        parts: list[str] = []
        for provider in self._providers:
            try:
                result = await provider.prefetch(query, session_id=session_id)
                if result and result.strip():
                    parts.append(result)
            except Exception as exc:
                logger.warning("Provider '%s' prefetch 失败（已跳过）: %s", provider.name, exc)
        return "\n\n".join(parts)

    async def sync_all(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """通知所有 Provider 持久化本轮对话。"""
        for provider in self._providers:
            try:
                await provider.sync_turn(user_content, assistant_content, session_id=session_id)
            except Exception as exc:
                logger.warning("Provider '%s' sync_turn 失败: %s", provider.name, exc)

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """通知所有 Provider 会话结束（重度沉淀）。"""
        for provider in self._providers:
            try:
                await provider.on_session_end(messages)
            except Exception as exc:
                logger.warning("Provider '%s' on_session_end 失败: %s", provider.name, exc)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """收集所有 Provider 的压缩前提示。"""
        parts: list[str] = []
        for provider in self._providers:
            try:
                result = provider.on_pre_compress(messages)
                if result and result.strip():
                    parts.append(result)
            except Exception as exc:
                logger.warning("Provider '%s' on_pre_compress 失败: %s", provider.name, exc)
        return "\n\n".join(parts)

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        """收集所有 Provider 的工具 schema（去重）。"""
        schemas: list[dict[str, Any]] = []
        seen: set[str] = set()
        for provider in self._providers:
            try:
                for schema in provider.get_tool_schemas():
                    name = schema.get("name", "")
                    if name and name not in seen:
                        schemas.append(schema)
                        seen.add(name)
            except Exception as exc:
                logger.warning("Provider '%s' get_tool_schemas 失败: %s", provider.name, exc)
        return schemas

    def has_tool(self, tool_name: str) -> bool:
        """检查指定工具名是否已注册。"""
        return tool_name in self._tool_to_provider

    async def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        """路由工具调用到对应 Provider，返回 JSON 字符串。"""
        provider = self._tool_to_provider.get(tool_name)
        if provider is None:
            return json.dumps(
                {"error": f"没有 Provider 处理工具 '{tool_name}'"}, ensure_ascii=False
            )
        try:
            return await provider.handle_tool_call(tool_name, args, **kwargs)
        except Exception as exc:
            logger.error(
                "Provider '%s' handle_tool_call(%s) 失败: %s", provider.name, tool_name, exc
            )
            return json.dumps({"error": f"工具 '{tool_name}' 执行失败: {exc}"}, ensure_ascii=False)

    async def initialize_all(self, session_id: str, **kwargs: Any) -> None:
        """初始化所有 Provider。"""
        for provider in self._providers:
            try:
                await provider.initialize(session_id=session_id, **kwargs)
            except Exception as exc:
                logger.warning("Provider '%s' initialize 失败: %s", provider.name, exc)

    async def shutdown_all(self) -> None:
        """关闭所有 Provider（逆序）。"""
        for provider in reversed(self._providers):
            try:
                await provider.shutdown()
            except Exception as exc:
                logger.warning("Provider '%s' shutdown 失败: %s", provider.name, exc)


# ---- 全局单例 ----

_memory_manager_instance: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """获取全局 MemoryManager 单例（未设置时返回空实例）。"""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance


def set_memory_manager(mgr: MemoryManager) -> None:
    """设置全局 MemoryManager 单例（agent 初始化时调用）。"""
    global _memory_manager_instance
    _memory_manager_instance = mgr
