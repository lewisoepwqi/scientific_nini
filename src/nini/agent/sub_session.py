"""子 Agent 会话。

默认使用内存存储实现隔离；当 persist_runtime_state=True 时，
允许将子会话消息与元信息落盘，便于多 Agent 审计与复盘。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nini.agent.session import Session
from nini.agent.session import register_session_persistence
from nini.agent.session import session_manager
from nini.agent.task_manager import TaskManager
from nini.memory.conversation import InMemoryConversationMemory


@dataclass
class SubSession(Session):
    """子 Agent 会话。

    继承 Session，支持两种运行模式：
    - persist_runtime_state=False：纯内存模式，不写磁盘
    - persist_runtime_state=True：审计模式，落盘消息与元信息，但资源仍归属父会话
    """

    # 父会话 ID，用于溯源和关联
    parent_session_id: str = ""
    persist_runtime_state: bool = False

    def __post_init__(self) -> None:
        """初始化子会话，根据持久化策略选择内存或审计模式。"""
        self.resource_owner_session_id = self.parent_session_id or self.id
        if self.persist_runtime_state:
            register_session_persistence(self.id, True)
            super().__post_init__()
            # 子 Agent 不使用知识库检索，但保留会话级持久化能力。
            self.knowledge_memory = None  # type: ignore[assignment]
            register_session_persistence(self.id, True)
            session_manager.save_subsession_metadata(
                self.id,
                parent_session_id=self.parent_session_id,
                resource_owner_session_id=self.resource_owner_session_id,
            )
            return

        register_session_persistence(self.id, False)
        self.task_manager = TaskManager()
        self.conversation_memory = InMemoryConversationMemory()  # type: ignore[assignment]
        self.knowledge_memory = None  # type: ignore[assignment]
