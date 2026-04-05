"""子 Agent 会话。

提供 SubSession 数据类，继承 Session 但使用内存存储，
不写磁盘，专用于子 Agent 隔离执行上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nini.agent.session import Session
from nini.agent.session import register_session_persistence
from nini.agent.task_manager import TaskManager
from nini.memory.conversation import InMemoryConversationMemory


@dataclass
class SubSession(Session):
    """子 Agent 会话。

    继承 Session，覆盖 __post_init__ 以使用内存存储，
    避免在 data/sessions/ 下创建任何磁盘文件。
    """

    # 父会话 ID，用于溯源和关联
    parent_session_id: str = ""
    persist_runtime_state: bool = False

    def __post_init__(self) -> None:
        """初始化子会话，使用内存存储替代磁盘存储。

        - conversation_memory 使用 InMemoryConversationMemory（不写磁盘）
        - knowledge_memory 设为 None（子 Agent 不需要 RAG）
        - task_manager 正常初始化
        - 不调用父类 __post_init__，避免触发磁盘 IO
        """
        register_session_persistence(self.id, False)
        self.resource_owner_session_id = self.parent_session_id or self.id
        # 初始化任务管理器
        self.task_manager = TaskManager()
        # 使用内存会话记忆，不写磁盘
        self.conversation_memory = InMemoryConversationMemory()  # type: ignore[assignment]
        # 子 Agent 不使用知识库检索
        self.knowledge_memory = None  # type: ignore[assignment]
