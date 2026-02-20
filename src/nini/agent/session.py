"""会话管理。"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any

import pandas as pd

from nini.agent.task_manager import TaskManager
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
    compressed_context: str = ""
    compressed_rounds: int = 0
    last_compressed_at: str | None = None
    workspace_hydrated: bool = False
    load_persisted_messages: bool = False
    conversation_memory: ConversationMemory = field(init=False, repr=False)
    knowledge_memory: KnowledgeMemory = field(init=False, repr=False)
    task_manager: TaskManager = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.conversation_memory = ConversationMemory(self.id)
        self.knowledge_memory = KnowledgeMemory(self.id)
        self.task_manager = TaskManager()
        if self.load_persisted_messages and not self.messages:
            self.messages.extend(self.conversation_memory.load_messages(resolve_refs=True))

    def add_message(self, role: str, content: str) -> None:
        msg = {"role": role, "content": content}
        self.messages.append(msg)
        self.conversation_memory.append(msg)
        self._check_auto_compress()

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

    def add_tool_result(
        self,
        tool_call_id: str,
        content: str,
        *,
        tool_name: str | None = None,
        status: str | None = None,
        intent: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
        if tool_name:
            msg["tool_name"] = tool_name
        if status:
            msg["status"] = status
        if intent:
            msg["intent"] = intent
        if execution_id:
            msg["execution_id"] = execution_id
        self.messages.append(msg)
        self.conversation_memory.append(msg)

    def rollback_last_turn(self) -> str | None:
        """回滚最后一轮：保留最后一条用户消息，删除其后的 Agent 输出。"""
        last_user_idx = -1
        for idx in range(len(self.messages) - 1, -1, -1):
            if self.messages[idx].get("role") == "user":
                last_user_idx = idx
                break

        if last_user_idx < 0:
            return None

        user_content = self.messages[last_user_idx].get("content")
        if not isinstance(user_content, str) or not user_content.strip():
            return None

        self.messages = self.messages[: last_user_idx + 1]
        self._rewrite_conversation_memory()
        return user_content

    def _rewrite_conversation_memory(self) -> None:
        """根据当前 messages 重写持久化记忆。"""
        self.conversation_memory.clear()
        for msg in self.messages:
            entry = {k: v for k, v in msg.items() if k != "_ts"}
            self.conversation_memory.append(entry)

    def set_compressed_context(self, summary: str) -> None:
        """更新压缩上下文，并记录压缩次数。

        追加后如果超过 compressed_context_max_chars 上限，
        按 ``---`` 分段丢弃最旧的段，直到总长度不超限。
        """
        summary = summary.strip()
        if not summary:
            return
        if self.compressed_context:
            self.compressed_context = f"{self.compressed_context}\n\n---\n\n{summary}"
        else:
            self.compressed_context = summary

        # 截断：超出上限时按 --- 分段丢弃最旧段
        max_chars = settings.compressed_context_max_chars
        if max_chars > 0 and len(self.compressed_context) > max_chars:
            segments = self.compressed_context.split("\n\n---\n\n")
            while len(segments) > 1 and len("\n\n---\n\n".join(segments)) > max_chars:
                segments.pop(0)
            self.compressed_context = "\n\n---\n\n".join(segments)
            # 极端情况：单段仍超限，硬截断保留尾部
            if len(self.compressed_context) > max_chars:
                self.compressed_context = self.compressed_context[-max_chars:]

        self.compressed_rounds += 1
        self.last_compressed_at = datetime.now(timezone.utc).isoformat()

    def _check_auto_compress(self) -> None:
        """检查是否需要自动压缩 memory.jsonl。"""
        if not settings.memory_auto_compress:
            return

        # 检查 memory.jsonl 文件大小
        memory_path = settings.sessions_dir / self.id / "memory.jsonl"
        if not memory_path.exists():
            return

        try:
            size_kb = memory_path.stat().st_size / 1024
            threshold_kb = settings.memory_compress_threshold_kb

            if size_kb > threshold_kb:
                # 触发自动压缩
                self._auto_compress_memory()
        except Exception:
            pass  # 静默失败，不影响正常流程

    def _auto_compress_memory(self) -> None:
        """自动压缩 memory，保留最近的消息，归档旧消息。"""
        from nini.memory.compression import compress_session_history

        keep_recent = settings.memory_keep_recent_messages
        total = len(self.messages)

        if total <= keep_recent:
            return

        # 计算需要归档的比例
        ratio = max(0.1, min(0.9, (total - keep_recent) / total))

        try:
            result = compress_session_history(self, ratio=ratio, min_messages=keep_recent)
            if result.get("success"):
                # 持久化压缩元数据
                from nini.agent.session import session_manager

                session_manager.save_session_compression(
                    self.id,
                    compressed_context=self.compressed_context,
                    compressed_rounds=self.compressed_rounds,
                    last_compressed_at=self.last_compressed_at,
                )
        except Exception as exc:
            # 压缩失败不应阻止正常流程
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"[Session] 自动压缩失败: {exc}")


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
        compressed_context = ""
        compressed_rounds = 0
        last_compressed_at: str | None = None
        if load_persisted_messages:
            meta = self._load_session_meta(sid)
            loaded_title = str(meta.get("title", "")).strip()
            if loaded_title:
                title = loaded_title
            compressed_context = str(meta.get("compressed_context", "") or "")
            compressed_rounds = int(meta.get("compressed_rounds", 0) or 0)
            raw_last_compressed = meta.get("last_compressed_at")
            if isinstance(raw_last_compressed, str) and raw_last_compressed.strip():
                last_compressed_at = raw_last_compressed

        session = Session(
            id=sid,
            title=title,
            compressed_context=compressed_context,
            compressed_rounds=compressed_rounds,
            last_compressed_at=last_compressed_at,
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

    def remove_session(self, session_id: str, *, delete_persistent: bool = False) -> None:
        session = self._sessions.pop(session_id, None)
        # 清理内存资源
        if session is not None:
            # 清理分析记忆
            from nini.memory.compression import clear_session_analysis_memories

            clear_session_analysis_memories(session_id)
        # 清理会话 lane
        from nini.agent.lane_queue import lane_queue

        lane_queue.remove_lane(session_id)
        # 清理 token tracker
        from nini.utils.token_counter import remove_tracker

        remove_tracker(session_id)
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

    def session_exists(self, session_id: str) -> bool:
        """判断会话是否存在（内存或磁盘）。"""
        return session_id in self._sessions or self._session_exists_on_disk(session_id)

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
        self._save_session_meta_fields(session_id, {"title": title})

    def save_session_compression(
        self,
        session_id: str,
        *,
        compressed_context: str,
        compressed_rounds: int,
        last_compressed_at: str | None,
    ) -> None:
        """持久化会话压缩元数据。"""
        self._save_session_meta_fields(
            session_id,
            {
                "compressed_context": compressed_context,
                "compressed_rounds": int(compressed_rounds),
                "last_compressed_at": last_compressed_at,
            },
        )

    def _load_session_title(self, session_id: str) -> str:
        """从元数据文件读取会话标题。"""
        meta = self._load_session_meta(session_id)
        return str(meta.get("title", "新会话") or "新会话")

    def _load_session_meta(self, session_id: str) -> dict[str, Any]:
        meta_path = settings.sessions_dir / session_id / "meta.json"
        if not meta_path.exists():
            return {}
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_session_meta_fields(self, session_id: str, fields: dict[str, Any]) -> None:
        meta_path = settings.sessions_dir / session_id / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = self._load_session_meta(session_id)
        meta.update(fields)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def _session_exists_on_disk(self, session_id: str) -> bool:
        memory_path = settings.sessions_dir / session_id / "memory.jsonl"
        knowledge_path = settings.sessions_dir / session_id / "knowledge.md"
        workspace_dir = settings.sessions_dir / session_id / "workspace"
        return memory_path.exists() or knowledge_path.exists() or workspace_dir.exists()

    def _list_persisted_session_ids(self) -> list[str]:
        """列出有实际消息记录的会话ID（避免列出空目录）。"""
        root = settings.sessions_dir
        if not root.exists():
            return []
        session_ids = []
        for p in root.iterdir():
            if p.is_dir():
                memory_path = p / "memory.jsonl"
                workspace_dir = p / "workspace"
                has_workspace_file = workspace_dir.exists() and any(
                    child.is_file() for child in workspace_dir.rglob("*")
                )
                if memory_path.exists() or has_workspace_file:
                    session_ids.append(p.name)
        return session_ids


# 全局单例
session_manager = SessionManager()
