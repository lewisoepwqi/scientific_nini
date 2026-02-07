"""会话管理。"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from nini.config import settings
from nini.memory.conversation import ConversationMemory
from nini.memory.knowledge import KnowledgeMemory


@dataclass
class Session:
    """一个对话会话的运行时状态。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "新会话"
    messages: list[dict[str, Any]] = field(default_factory=list)
    datasets: dict[str, pd.DataFrame] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    load_persisted_messages: bool = False
    conversation_memory: ConversationMemory = field(init=False, repr=False)
    knowledge_memory: KnowledgeMemory = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.conversation_memory = ConversationMemory(self.id)
        self.knowledge_memory = KnowledgeMemory(self.id)
        if self.load_persisted_messages and not self.messages:
            self.messages.extend(self.conversation_memory.load_messages())

    def add_message(self, role: str, content: str) -> None:
        msg = {"role": role, "content": content}
        self.messages.append(msg)
        self.conversation_memory.append(msg)

    def add_assistant_event(
        self,
        event_type: str,
        content: str,
        **extra: Any,
    ) -> None:
        """追加 assistant 事件消息（图表/数据预览/产物/图片）。"""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "event_type": event_type,
        }
        for key, value in extra.items():
            if value is not None:
                msg[key] = value
        self.messages.append(msg)
        self.conversation_memory.append(msg)

    def add_tool_call(self, tool_call_id: str, name: str, arguments: str) -> None:
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
        self.messages.append(msg)
        self.conversation_memory.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
        self.messages.append(msg)
        self.conversation_memory.append(msg)


class SessionManager:
    """管理所有活跃会话。"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        session_id: str | None = None,
        *,
        load_persisted_messages: bool = False,
    ) -> Session:
        sid = session_id or uuid.uuid4().hex[:12]
        # 如果需要加载持久化消息，先尝试加载标题
        title = "新会话"
        if load_persisted_messages:
            loaded_title = self._load_session_title(sid)
            if loaded_title:
                title = loaded_title

        session = Session(
            id=sid,
            title=title,
            load_persisted_messages=load_persisted_messages,
        )
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str | None = None) -> Session:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        if session_id:
            if self._session_exists_on_disk(session_id):
                return self.create_session(
                    session_id,
                    load_persisted_messages=True,
                )
            return self.create_session(session_id)

        return self.create_session()

    def remove_session(
        self, session_id: str, *, delete_persistent: bool = False
    ) -> None:
        self._sessions.pop(session_id, None)
        if delete_persistent:
            session_dir = settings.sessions_dir / session_id
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)

    def update_session_title(self, session_id: str, title: str) -> bool:
        """更新会话标题。"""
        session = self._sessions.get(session_id)
        if session:
            session.title = title
            return True
        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: dict[str, dict[str, Any]] = {}

        for sid, session in self._sessions.items():
            sessions[sid] = {
                "id": sid,
                "title": session.title,
                "message_count": len(session.messages),
                "source": "memory",
            }

        for sid in self._list_persisted_session_ids():
            if sid in sessions:
                continue
            mem = ConversationMemory(sid)
            msg_count = len(mem.load_messages())
            # 尝试从元数据文件读取标题
            title = self._load_session_title(sid)
            sessions[sid] = {
                "id": sid,
                "title": title,
                "message_count": msg_count,
                "source": "disk",
            }

        return sorted(
            sessions.values(),
            key=lambda item: item["id"],
            reverse=True,
        )

    def save_session_title(self, session_id: str, title: str) -> None:
        """将会话标题持久化到元数据文件。"""
        import json

        meta_path = settings.sessions_dir / session_id / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        meta["title"] = title
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def _load_session_title(self, session_id: str) -> str:
        """从元数据文件读取会话标题。"""
        import json

        meta_path = settings.sessions_dir / session_id / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                return meta.get("title", "新会话")
            except Exception:
                pass
        return "新会话"

    def _session_exists_on_disk(self, session_id: str) -> bool:
        memory_path = settings.sessions_dir / session_id / "memory.jsonl"
        knowledge_path = settings.sessions_dir / session_id / "knowledge.md"
        return memory_path.exists() or knowledge_path.exists()

    def _list_persisted_session_ids(self) -> list[str]:
        """列出有实际消息记录的会话ID（避免列出空目录）。"""
        root = settings.sessions_dir
        if not root.exists():
            return []
        session_ids = []
        for p in root.iterdir():
            if p.is_dir():
                memory_path = p / "memory.jsonl"
                if memory_path.exists():
                    session_ids.append(p.name)
        return session_ids


# 全局单例
session_manager = SessionManager()
