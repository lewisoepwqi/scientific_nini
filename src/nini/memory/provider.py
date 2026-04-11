"""记忆 Provider 抽象接口。对齐 hermes-agent MemoryProvider 生命周期。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class MemoryProvider(ABC):
    """记忆 Provider 抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称标识符（内置 Provider 返回 'builtin'）。"""

    @abstractmethod
    async def initialize(self, session_id: str, **kwargs: Any) -> None:
        """初始化 Provider，建立连接，执行数据迁移。"""

    def system_prompt_block(self) -> str:
        """返回注入 system prompt 的静态文本块（会话开始时快照，不中途变化）。"""
        return ""

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """每轮 LLM 调用前：检索相关记忆，返回原始上下文文本（不带 fencing）。"""
        return ""

    async def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
    ) -> None:
        """每轮结束后：持久化本轮对话摘要/发现。"""

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """会话结束：从完整历史提取关键记忆沉淀。"""

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """上下文压缩前：提取关键数值，返回追加到压缩 prompt 的文本。"""
        return ""

    @abstractmethod
    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """返回暴露给 LLM 的工具 schema 列表（无工具时返回空列表）。"""

    async def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        """处理 LLM 工具调用，返回 JSON 字符串结果。"""
        raise NotImplementedError(f"Provider {self.name} 未实现工具 {tool_name}")

    async def shutdown(self) -> None:
        """关闭 Provider，释放资源。"""
