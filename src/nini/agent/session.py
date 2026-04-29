"""会话管理。"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SESSION_PERSISTENCE_REGISTRY: dict[str, bool] = {}

import pandas as pd

from nini.agent.task_manager import TaskManager
from nini.config import settings
from nini.memory.conversation import ConversationMemory
from nini.memory.knowledge import KnowledgeMemory


def register_session_persistence(session_id: str, enabled: bool) -> None:
    """注册会话是否允许持久化运行时状态。"""
    normalized = str(session_id or "").strip()
    if not normalized:
        return
    _SESSION_PERSISTENCE_REGISTRY[normalized] = bool(enabled)


def _normalize_session_identifier(value: Any) -> str:
    """仅接受真实字符串形式的会话标识，避免将 Mock 等对象误转为路径。"""
    if isinstance(value, str):
        return value.strip()
    return ""


def session_persistence_enabled(session_or_id: str | Any) -> bool:
    """判断会话是否允许持久化运行时状态。"""
    if isinstance(session_or_id, str):
        normalized = session_or_id.strip()
        if not normalized:
            return True
        return _SESSION_PERSISTENCE_REGISTRY.get(normalized, True)

    session_id = _normalize_session_identifier(getattr(session_or_id, "id", ""))
    if not session_id:
        return True
    session_flag = getattr(session_or_id, "persist_runtime_state", None)
    if isinstance(session_flag, bool):
        register_session_persistence(session_id, session_flag)
        return session_flag
    return _SESSION_PERSISTENCE_REGISTRY.get(session_id, True)


def resolve_session_resource_id(session_or_id: str | Any) -> str:
    """解析会话资源应归属的 session_id。"""
    if isinstance(session_or_id, str):
        return session_or_id.strip()

    owner_id = _normalize_session_identifier(
        getattr(session_or_id, "resource_owner_session_id", "")
    )
    if owner_id:
        return owner_id

    parent_id = _normalize_session_identifier(getattr(session_or_id, "parent_session_id", ""))
    if parent_id:
        return parent_id

    return _normalize_session_identifier(getattr(session_or_id, "id", ""))


@dataclass
class Session:
    """一个对话会话的运行时状态。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "新会话"
    messages: list[dict[str, Any]] = field(default_factory=list)
    datasets: dict[str, pd.DataFrame] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    # 最后一个任务进入 in_progress 时记录其 id，供 turn 结束后由 runner 自动关闭
    pending_auto_complete_task_id: int | None = None
    documents: dict[str, Any] = field(default_factory=dict)
    tool_approval_grants: dict[str, str] = field(default_factory=dict)
    sandbox_approved_imports: set[str] = field(default_factory=set)
    compressed_context: str = ""
    compressed_rounds: int = 0
    last_compressed_at: str | None = None
    compression_segments: list[dict[str, Any]] = field(default_factory=list)
    research_profile_id: str = "default"
    persist_runtime_state: bool = True
    resource_owner_session_id: str | None = None
    workspace_hydrated: bool = False
    # 沙箱工作区根目录（子 Agent 执行期间由 spawner 设置，指向 sandbox_tmp/{run_id}/）
    workspace_root: Path | None = None
    load_persisted_messages: bool = False
    harness_runtime_context: str = ""
    dispatch_runtime_state: dict[str, Any] = field(default_factory=dict)
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    # 图表输出格式偏好："interactive"（Plotly）/ "image"（Matplotlib/PNG）/ None（未设置）
    chart_output_preference: str | None = None
    task_kind: str = "quick_task"
    recipe_id: str | None = None
    recipe_inputs: dict[str, Any] = field(default_factory=dict)
    deep_task_state: dict[str, Any] = field(default_factory=dict)
    runtime_stop_event: Any = field(default=None, repr=False)
    runtime_chat_task: Any = field(default=None, repr=False)
    subagent_stop_events: dict[str, Any] = field(default_factory=dict, repr=False)
    sub_agent_snapshots: list[Any] = field(default_factory=list, repr=False)
    conversation_memory: ConversationMemory = field(init=False, repr=False)
    knowledge_memory: KnowledgeMemory = field(init=False, repr=False)
    task_manager: TaskManager = field(init=False, repr=False)
    evidence_collector: Any = field(init=False, repr=False)
    # 工具执行期间的事件回调，允许工具流式发送进度更新
    event_callback: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        from nini.agent.evidence_collector import EvidenceCollector

        register_session_persistence(self.id, self.persist_runtime_state)
        if not self.resource_owner_session_id:
            self.resource_owner_session_id = self.id
        self.conversation_memory = ConversationMemory(self.id)
        self.knowledge_memory = KnowledgeMemory(self.id)
        self.task_manager = TaskManager()
        self.evidence_collector = EvidenceCollector(self.id)
        # 防御：meta.json 中 null 值或类型错误时重置为空列表
        if not isinstance(self.compression_segments, list):
            self.compression_segments = []
        if not isinstance(self.pending_actions, list):
            self.pending_actions = []
        if self.load_persisted_messages and not self.messages:
            self.messages.extend(self.conversation_memory.load_messages(resolve_refs=True))
        if self.messages:
            self._reconstruct_task_manager_from_messages()

    def _reconstruct_task_manager_from_messages(self) -> None:
        """从消息历史重建 task_manager（中断恢复场景）。

        遍历 assistant 消息中的 tool_calls，找到 task_write / task_state 工具调用，
        按顺序重放 init 和 update 操作，还原中断前的任务状态。
        """
        rebuilt = TaskManager()
        for msg in self.messages:
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                continue
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                if name not in ("task_write", "task_state"):
                    continue
                try:
                    args = json.loads(func.get("arguments", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                operation = args.get("operation") or args.get("mode")
                if operation == "init":
                    raw_tasks = args.get("tasks", [])
                    if raw_tasks:
                        rebuilt = rebuilt.init_tasks(raw_tasks)
                elif operation == "update":
                    updates = args.get("tasks", [])
                    if updates and rebuilt.initialized:
                        result = rebuilt.update_tasks(updates)
                        rebuilt = result.manager
        if rebuilt.initialized:
            self.task_manager = rebuilt

    def supports_persistent_state(self) -> bool:
        """返回当前会话是否允许写入持久化运行时状态。"""
        return session_persistence_enabled(self)

    def get_resource_session_id(self) -> str:
        """返回当前会话资源应归属的 session_id。"""
        return resolve_session_resource_id(self)

    def _append_entry(self, entry: dict[str, Any], *, auto_compress: bool = False) -> None:
        """追加一条规范化消息记录并同步持久化。"""
        materialized_entry = dict(entry)
        materialized_entry.setdefault("_ts", datetime.now(timezone.utc).isoformat())
        self.messages.append(materialized_entry)
        self.conversation_memory.append(materialized_entry)
        if auto_compress:
            self._check_auto_compress()

    def add_message(self, role: str, content: str, **extra: Any) -> None:
        msg: dict[str, Any] = {"role": role, "content": content}
        if role == "user":
            msg["event_type"] = "message"
        elif role == "assistant":
            msg["event_type"] = "text"
            msg["operation"] = "complete"
        elif role == "tool":
            msg["event_type"] = "tool_result"
            msg["operation"] = "complete"
        for key, value in extra.items():
            if value is not None:
                msg[key] = value
        self._append_entry(msg, auto_compress=True)

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
            "operation": "complete",
        }
        for key, value in extra.items():
            if value is not None:
                msg[key] = value
        self._append_entry(msg)

    def add_tool_call(self, tool_call_id: str, name: str, arguments: str, **extra: Any) -> None:
        msg = {
            "role": "assistant",
            "content": None,
            "event_type": "tool_call",
            "operation": "complete",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
        for key, value in extra.items():
            if value is not None:
                msg[key] = value
        self._append_entry(msg)

    def add_tool_result(
        self,
        tool_call_id: str,
        content: str,
        *,
        tool_name: str | None = None,
        status: str | None = None,
        intent: str | None = None,
        execution_id: str | None = None,
        **extra: Any,
    ) -> None:
        msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
            "event_type": "tool_result",
            "operation": "complete",
        }
        if tool_name:
            msg["tool_name"] = tool_name
        if status:
            msg["status"] = status
        if intent:
            msg["intent"] = intent
        if execution_id:
            msg["execution_id"] = execution_id
        for key, value in extra.items():
            if value is not None and key not in msg:
                msg[key] = value
        self._append_entry(msg)

    def list_pending_actions(
        self,
        *,
        status: str | None = None,
        action_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """返回待处理动作列表。"""
        items = [dict(item) for item in self.pending_actions if isinstance(item, dict)]
        if action_type:
            normalized_type = str(action_type).strip()
            items = [item for item in items if str(item.get("type", "")).strip() == normalized_type]
        if status:
            normalized_status = str(status).strip()
            items = [
                item for item in items if str(item.get("status", "")).strip() == normalized_status
            ]
        return items

    def upsert_pending_action(
        self,
        *,
        action_type: str,
        key: str,
        summary: str,
        source_tool: str,
        status: str = "pending",
        blocking: bool = True,
        failure_category: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """新增或更新待处理动作。"""
        normalized_type = str(action_type or "").strip()
        normalized_key = str(key or "").strip()
        if not normalized_type or not normalized_key:
            raise ValueError("pending action 必须提供 action_type 和 key")

        now_iso = datetime.now(timezone.utc).isoformat()
        normalized_summary = str(summary or "").strip()
        normalized_source = str(source_tool or "").strip() or "system"
        normalized_status = str(status or "").strip() or "pending"
        payload = {
            "type": normalized_type,
            "key": normalized_key,
            "status": normalized_status,
            "summary": normalized_summary,
            "source_tool": normalized_source,
            "blocking": bool(blocking),
            "failure_category": str(failure_category or "").strip() or None,
            "created_at": now_iso,
            "updated_at": now_iso,
            "metadata": dict(metadata or {}),
        }
        replaced = False
        next_items: list[dict[str, Any]] = []
        for item in self.pending_actions:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("type", "")).strip() == normalized_type
                and str(item.get("key", "")).strip() == normalized_key
            ):
                payload["created_at"] = str(item.get("created_at") or now_iso)
                next_items.append({**item, **payload})
                replaced = True
            else:
                next_items.append(dict(item))
        if not replaced:
            next_items.append(payload)
        self.pending_actions = next_items
        if self.supports_persistent_state():
            session_manager.save_session_pending_actions(self.id, self.pending_actions)
        return dict(payload)

    def resolve_pending_action(
        self,
        *,
        action_type: str,
        key: str,
        final_status: str = "resolved",
        resolution_note: str | None = None,
    ) -> bool:
        """将待处理动作标记为已解决并从账本移除。"""
        normalized_type = str(action_type or "").strip()
        normalized_key = str(key or "").strip()
        if not normalized_type or not normalized_key:
            return False

        matched = False
        next_items: list[dict[str, Any]] = []
        for item in self.pending_actions:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("type", "")).strip() == normalized_type
                and str(item.get("key", "")).strip() == normalized_key
            ):
                matched = True
                continue
            next_items.append(dict(item))
        if matched:
            self.pending_actions = next_items
            if self.supports_persistent_state():
                session_manager.save_session_pending_actions(self.id, self.pending_actions)
        return matched

    def clear_pending_actions(self, *, action_type: str | None = None) -> int:
        """批量清理待处理动作。"""
        normalized_type = str(action_type or "").strip()
        before = len(self.pending_actions)
        if normalized_type:
            self.pending_actions = [
                dict(item)
                for item in self.pending_actions
                if isinstance(item, dict) and str(item.get("type", "")).strip() != normalized_type
            ]
        else:
            self.pending_actions = []
        removed = before - len(self.pending_actions)
        if removed > 0:
            if self.supports_persistent_state():
                session_manager.save_session_pending_actions(self.id, self.pending_actions)
        return removed

    def build_pending_actions_summary(self, *, max_items: int = 5) -> str:
        """构建运行时上下文使用的待处理动作摘要。"""
        items = self.list_pending_actions(status="pending")[:max_items]
        if not items:
            return ""
        lines = []
        for item in items:
            summary = str(item.get("summary", "")).strip()
            source_tool = str(item.get("source_tool", "")).strip()
            tone = "阻塞" if item.get("blocking", True) else "提醒"
            suffix = f"（来源: {source_tool}）" if source_tool else ""
            # 为 tool_failure 类型追加 recovery_hint（帮助 LLM 理解如何处理）
            metadata = item.get("metadata", {})
            if isinstance(metadata, dict):
                if item.get("type") == "tool_failure_unresolved":
                    recovery_hint = str(metadata.get("recovery_hint", "")).strip()
                    if recovery_hint:
                        suffix += f"| 建议: {recovery_hint[:150]}"
                    recovery_action = str(metadata.get("recovery_action", "")).strip()
                    if recovery_action:
                        suffix += f"| 恢复动作: {recovery_action}"
                    current_task_id = str(metadata.get("current_in_progress_task_id", "")).strip()
                    if current_task_id:
                        suffix += f"| 当前任务: {current_task_id}"
                    pending_wave_ids = metadata.get("current_pending_wave_task_ids")
                    if isinstance(pending_wave_ids, list) and pending_wave_ids:
                        suffix += f"| 当前 wave: {','.join(str(item) for item in pending_wave_ids)}"
                elif item.get("type") == "script_not_run":
                    script_id = str(item.get("key", "")).strip()
                    last_error = str(metadata.get("last_error", "")).strip()
                    reason = str(metadata.get("reason", "")).strip()
                    if reason == "auto_run_failed" and last_error:
                        suffix += (
                            f"| 建议: 修复脚本 {script_id} 的错误后使用 run_script 或 rerun 重试"
                        )
                    elif reason == "run_failed":
                        suffix += f"| 建议: 修复脚本 {script_id} 后使用 rerun 重试"
                    elif script_id:
                        suffix += f"| 建议: 使用 run_script 执行脚本 {script_id}"
            lines.append(f"- [{tone}/{item.get('type', 'unknown')}] {summary}{suffix}")
        remaining = len(self.list_pending_actions(status="pending")) - len(items)
        if remaining > 0:
            lines.append(f"- ... 另有 {remaining} 个待处理动作未展开")
        return "\n".join(lines)

    def stop_all_subagents(self) -> int:
        """向当前会话下所有仍在运行的子 Agent 广播停止信号。"""
        stop_events = self.subagent_stop_events
        if not isinstance(stop_events, dict):
            return 0

        stopped = 0
        for event in stop_events.values():
            if isinstance(event, asyncio.Event) and not event.is_set():
                event.set()
                stopped += 1
        return stopped

    def add_reasoning(
        self,
        content: str,
        reasoning_type: str | None = None,
        key_decisions: list[str] | None = None,
        confidence_score: float | None = None,
        reasoning_id: str | None = None,
        **extra: Any,
    ) -> None:
        """添加 reasoning 消息（思考过程）到会话历史。

        Args:
            content: 思考内容
            reasoning_type: 推理类型 (analysis/decision/planning/reflection)
            key_decisions: 关键决策点列表
            confidence_score: 置信度分数
            reasoning_id: 推理节点唯一标识
            **extra: 其他元数据
        """
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "event_type": "reasoning",
            "operation": "complete",
        }
        if reasoning_type:
            msg["reasoning_type"] = reasoning_type
        if key_decisions:
            msg["key_decisions"] = key_decisions
        if confidence_score is not None:
            msg["confidence_score"] = confidence_score
        if reasoning_id:
            msg["reasoning_id"] = reasoning_id
        for key, value in extra.items():
            if value is not None and key not in msg:
                msg[key] = value
        self._append_entry(msg)

    def grant_tool_approval(self, approval_key: str, *, scope: str = "session") -> None:
        """记录工具授权状态。"""
        key = str(approval_key or "").strip()
        normalized_scope = str(scope or "").strip().lower()
        if not key or normalized_scope != "session":
            return
        self.tool_approval_grants[key] = normalized_scope
        if self.supports_persistent_state():
            session_manager.save_session_tool_approvals(self.id, self.tool_approval_grants)

    def has_tool_approval(self, approval_key: str) -> bool:
        """检查当前会话是否已放行指定工具。"""
        key = str(approval_key or "").strip()
        return bool(key) and self.tool_approval_grants.get(key) == "session"

    def grant_sandbox_import_approval(
        self,
        packages: list[str] | set[str] | tuple[str, ...],
        *,
        scope: str = "session",
    ) -> None:
        """记录沙盒扩展包授权。"""
        normalized_packages = session_manager._normalize_sandbox_import_approvals(packages)
        normalized_scope = str(scope or "").strip().lower()
        if not normalized_packages:
            return
        if normalized_scope == "always":
            from nini.sandbox.approval_manager import approval_manager

            approval_manager.grant_approved_imports(normalized_packages)
            normalized_scope = "session"
        if normalized_scope != "session":
            return
        self.sandbox_approved_imports.update(normalized_packages)
        if self.supports_persistent_state():
            session_manager.save_session_sandbox_import_approvals(
                self.id,
                self.sandbox_approved_imports,
            )

    def has_sandbox_import_approval(self, package: str) -> bool:
        """检查当前会话是否已授权指定扩展包。"""
        normalized = session_manager._normalize_sandbox_import_approvals([package])
        return any(item in self.sandbox_approved_imports for item in normalized)

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

        将新摘要封装为 CompressionSegment（depth=0）追加到 compression_segments。
        当段数超过 compressed_context_max_segments 时，直接丢弃最旧段（两条路径均执行）。
        压缩上下文由剩余段的 summary join 重建；compressed_context_max_chars 仅作为
        极端兜底（单段超限时硬截断）。
        """
        from nini.memory.compression import CompressionSegment

        summary = summary.strip()
        if not summary:
            return

        # 创建新段并追加
        seg = CompressionSegment(
            summary=summary,
            archived_count=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            depth=0,
        ).to_dict()
        self.compression_segments.append(seg)

        # 段数超限时丢弃最旧段（无论哪条调用路径）
        max_segs = settings.compressed_context_max_segments
        if max_segs > 0 and len(self.compression_segments) > max_segs:
            self.compression_segments.pop(0)

        # 从剩余 segments 重新 join 重建 compressed_context
        self.compressed_context = "\n\n---\n\n".join(
            s["summary"] for s in self.compression_segments
        )

        # 极端兜底：单段仍超出字符上限时硬截断（轻量路径保底）
        max_chars = settings.compressed_context_max_chars
        if max_chars > 0 and len(self.compressed_context) > max_chars:
            self.compressed_context = self.compressed_context[-max_chars:]

        self.compressed_rounds += 1
        self.last_compressed_at = datetime.now(timezone.utc).isoformat()

    def set_research_profile_id(self, profile_id: str) -> None:
        """设置研究画像标识。"""
        normalized = str(profile_id or "").strip() or "default"
        self.research_profile_id = normalized

    def bind_recipe_context(
        self,
        *,
        task_kind: str,
        recipe_id: str | None,
        recipe_inputs: dict[str, Any] | None = None,
    ) -> None:
        """绑定当前会话的任务分类与 Recipe 上下文。"""
        self.task_kind = str(task_kind or "").strip() or "quick_task"
        self.recipe_id = str(recipe_id or "").strip() or None
        self.recipe_inputs = (
            {str(key): value for key, value in (recipe_inputs or {}).items() if str(key).strip()}
            if recipe_inputs
            else {}
        )

    def set_deep_task_state(self, **state: Any) -> None:
        """更新 deep task 状态。"""
        next_state = dict(self.deep_task_state)
        next_state.update({key: value for key, value in state.items() if value is not None})
        self.deep_task_state = next_state

    def _check_auto_compress(self) -> None:
        """检查是否需要自动压缩（基于 Token 数估算）。"""
        if not settings.memory_auto_compress:
            return

        if not self.messages:
            return

        try:
            from nini.utils.token_counter import count_messages_tokens

            token_count = count_messages_tokens(self.messages)
            if token_count > settings.memory_compress_threshold_tokens:
                self._auto_compress_memory()
        except Exception:
            logger.warning("自动压缩检查失败", exc_info=True)

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
                import nini.agent.session as _self_mod

                if self.supports_persistent_state():
                    _self_mod.session_manager.save_session_compression(
                        self.id,
                        compressed_context=self.compressed_context,
                        compressed_rounds=self.compressed_rounds,
                        last_compressed_at=self.last_compressed_at,
                        compression_segments=self.compression_segments,
                    )
        except Exception as exc:
            # 压缩失败不应阻止正常流程
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"[Session] 自动压缩失败: {exc}")


class SessionManager:
    """管理所有活跃会话。"""

    def __init__(self) -> None:
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
        research_profile_id = "default"
        tool_approval_grants: dict[str, str] = {}
        sandbox_approved_imports: set[str] = self._load_persistent_sandbox_import_approvals()
        chart_output_preference: str | None = None
        task_kind = "quick_task"
        recipe_id: str | None = None
        recipe_inputs: dict[str, Any] = {}
        deep_task_state: dict[str, Any] = {}
        compression_segments: list[dict[str, Any]] = []
        pending_actions: list[dict[str, Any]] = []
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
            loaded_profile_id = str(meta.get("research_profile_id", "") or "").strip()
            if loaded_profile_id:
                research_profile_id = loaded_profile_id
            tool_approval_grants = self._normalize_tool_approval_grants(
                meta.get("tool_approval_grants")
            )
            session_level_imports = self._normalize_sandbox_import_approvals(
                meta.get("sandbox_approved_imports")
            )
            sandbox_approved_imports |= session_level_imports
            raw_pref = meta.get("chart_output_preference")
            if raw_pref in ("interactive", "image"):
                chart_output_preference = raw_pref
            loaded_task_kind = str(meta.get("task_kind", "") or "").strip()
            if loaded_task_kind:
                task_kind = loaded_task_kind
            loaded_recipe_id = str(meta.get("recipe_id", "") or "").strip()
            if loaded_recipe_id:
                recipe_id = loaded_recipe_id
            raw_recipe_inputs = meta.get("recipe_inputs")
            if isinstance(raw_recipe_inputs, dict):
                recipe_inputs = {
                    str(key): value for key, value in raw_recipe_inputs.items() if str(key).strip()
                }
            raw_deep_task_state = meta.get("deep_task_state")
            if isinstance(raw_deep_task_state, dict):
                deep_task_state = dict(raw_deep_task_state)
            raw_pending_actions = meta.get("pending_actions")
            if isinstance(raw_pending_actions, list):
                pending_actions = [item for item in raw_pending_actions if isinstance(item, dict)]
            # 加载 compression_segments；向后兼容旧格式
            raw_segs = meta.get("compression_segments")
            if isinstance(raw_segs, list) and raw_segs:
                compression_segments = [s for s in raw_segs if isinstance(s, dict)]
            elif not raw_segs and compressed_context:
                # 旧格式：有 compressed_context 但无 compression_segments，in-memory 构造单段
                compression_segments = [
                    {
                        "summary": compressed_context,
                        "archived_count": 0,
                        "created_at": "",
                        "depth": 0,
                    }
                ]

        session = Session(
            id=sid,
            title=title,
            tool_approval_grants=tool_approval_grants,
            sandbox_approved_imports=sandbox_approved_imports,
            compressed_context=compressed_context,
            compressed_rounds=compressed_rounds,
            last_compressed_at=last_compressed_at,
            research_profile_id=research_profile_id,
            chart_output_preference=chart_output_preference,
            task_kind=task_kind,
            recipe_id=recipe_id,
            recipe_inputs=recipe_inputs,
            deep_task_state=deep_task_state,
            pending_actions=pending_actions,
            compression_segments=compression_segments,
            load_persisted_messages=load_persisted_messages,
        )
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    _SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

    def load_existing(
        self,
        session_id: str,
        *,
        load_persisted_messages: bool = True,
    ) -> Session | None:
        """加载已存在的会话，不存在时返回 None。"""
        if not self._SESSION_ID_RE.match(session_id):
            raise ValueError(f"无效的 session_id 格式: {session_id!r}")
        if session_id in self._sessions:
            return self._sessions[session_id]
        if not self._session_exists_on_disk(session_id):
            return None
        return self.create_session(
            session_id,
            load_persisted_messages=load_persisted_messages,
        )

    def get_or_create(self, session_id: str | None = None) -> Session:
        if session_id and not self._SESSION_ID_RE.match(session_id):
            raise ValueError(f"无效的 session_id 格式: {session_id!r}")
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        if session_id:
            session = self.load_existing(session_id, load_persisted_messages=True)
            if session is not None:
                return session
            return self.create_session(session_id)

        return self.create_session()

    def remove_session(self, session_id: str, *, delete_persistent: bool = False) -> None:
        session = self._sessions.pop(session_id, None)
        # 清理内存资源
        if session is not None:
            # 清理分析记忆
            from nini.memory.compression import clear_session_analysis_memory_cache

            clear_session_analysis_memory_cache(session_id)
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

    def list_sessions(self, *, include_subsessions: bool = False) -> list[dict[str, Any]]:
        sessions: dict[str, dict[str, Any]] = {}

        for sid, session in list(self._sessions.items()):
            if (
                not include_subsessions
                and str(getattr(session, "parent_session_id", "") or "").strip()
            ):
                continue
            updated_at = self._get_session_updated_at_in_memory(session)
            created_at = self._get_session_created_at_in_memory(session)
            sessions[sid] = {
                "id": sid,
                "title": session.title,
                "message_count": self.get_total_message_count(sid, session=session),
                "source": "memory",
                "created_at": created_at,
                "updated_at": updated_at,
                "last_message_at": updated_at,
            }

        for sid in self._list_persisted_session_ids():
            if sid in sessions:
                continue
            meta = self._load_session_meta(sid)
            if not include_subsessions and bool(meta.get("is_subsession")):
                continue
            message_count = self.get_total_message_count(sid, meta=meta)
            title = str(meta.get("title", "新会话") or "新会话")
            updated_at = self._derive_session_updated_at_iso(sid, meta)
            created_at = self._derive_session_created_at_iso(sid, meta, updated_at)
            sessions[sid] = {
                "id": sid,
                "title": title,
                "message_count": message_count,
                "source": "disk",
                "created_at": created_at,
                "updated_at": updated_at,
                "last_message_at": updated_at,
            }

        return sorted(
            sessions.values(),
            key=lambda item: (self._session_sort_timestamp(item), str(item["id"])),
            reverse=True,
        )

    def get_total_message_count(
        self,
        session_id: str,
        *,
        session: Session | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """返回会话总消息数（活动消息 + 已归档消息）。"""
        next_meta = meta if meta is not None else self._load_session_meta(session_id)
        active_count = (
            len(session.messages)
            if session is not None
            else self._load_cached_message_count(session_id, next_meta)
        )
        archived_count = self._load_archived_message_count(session_id)
        return active_count + archived_count

    def _get_session_updated_at_in_memory(self, session: Session) -> str:
        for message in reversed(session.messages):
            raw_ts = message.get("_ts")
            if isinstance(raw_ts, str) and raw_ts:
                return raw_ts
        return datetime.now(timezone.utc).isoformat()

    def _get_session_created_at_in_memory(self, session: Session) -> str:
        for message in session.messages:
            raw_ts = message.get("_ts")
            if isinstance(raw_ts, str) and raw_ts:
                return raw_ts
        return datetime.now(timezone.utc).isoformat()

    def _memory_path(self, session_id: str) -> Path:
        return settings.sessions_dir / session_id / "memory.jsonl"

    def _agent_runs_path(self, session_id: str) -> Path:
        return settings.sessions_dir / session_id / "agent_runs.jsonl"

    def append_agent_run_event(self, session_id: str, event: dict[str, Any]) -> None:
        """追加一条子运行事件到独立日志文件。"""
        if not session_id:
            return
        target_path = self._agent_runs_path(session_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(event)
        payload.setdefault("_ts", datetime.now(timezone.utc).isoformat())
        with target_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def load_agent_run_events(
        self,
        session_id: str,
        *,
        turn_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        tail: bool = False,
    ) -> list[dict[str, Any]]:
        """读取会话的子运行事件，支持按 turn_id/run_id 过滤与分页。"""
        target_path = self._agent_runs_path(session_id)
        if not target_path.exists():
            return []
        events: list[dict[str, Any]] = []
        normalized_run_id = str(run_id or "").strip() or None
        normalized_limit = limit if isinstance(limit, int) and limit > 0 else None
        normalized_offset = max(0, offset)
        try:
            with target_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(parsed, dict):
                        continue
                    event_turn_id = str(parsed.get("turn_id") or "").strip() or None
                    metadata = parsed.get("metadata")
                    if event_turn_id is None and isinstance(metadata, dict):
                        event_turn_id = str(metadata.get("turn_id") or "").strip() or None
                    if turn_id and event_turn_id != turn_id:
                        continue
                    event_run_id = (
                        str(metadata.get("run_id") or "").strip()
                        if isinstance(metadata, dict)
                        else ""
                    )
                    if normalized_run_id and event_run_id != normalized_run_id:
                        continue
                    events.append(parsed)
        except OSError:
            return []
        if normalized_offset:
            events = events[normalized_offset:]
        if normalized_limit is not None:
            events = events[-normalized_limit:] if tail else events[:normalized_limit]
        return events

    def _load_cached_message_count(self, session_id: str, meta: dict[str, Any]) -> int:
        memory_path = self._memory_path(session_id)
        if not memory_path.exists():
            return 0

        current_mtime = memory_path.stat().st_mtime
        cached_mtime = meta.get("_memory_mtime")
        cached_count = meta.get("message_count")
        if isinstance(cached_mtime, (float, int)) and isinstance(cached_count, int):
            if abs(float(cached_mtime) - current_mtime) < 1e-6:
                return cached_count

        count = self._count_message_entries(memory_path)
        updated_at = datetime.fromtimestamp(current_mtime, timezone.utc).isoformat()
        updated_meta = dict(meta)
        updated_meta["message_count"] = count
        updated_meta["_memory_mtime"] = current_mtime
        updated_meta["updated_at"] = updated_at
        updated_meta["created_at"] = self._derive_session_created_at_iso(
            session_id,
            updated_meta,
            updated_at,
        )
        meta.clear()
        meta.update(updated_meta)
        self._save_session_meta_fields(session_id, updated_meta)
        return count

    def _count_message_entries(self, memory_path: Path) -> int:
        """按行快速统计带 role 字段的记录数，避免全量 canonicalize。"""
        count = 0
        try:
            with memory_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if '"role"' in line:
                        count += 1
        except Exception:
            return 0
        return count

    def _load_archived_message_count(self, session_id: str) -> int:
        """统计已压缩归档的消息条数。优先读取 SQLite，回退 archive 文件。"""
        session_dir = settings.sessions_dir / session_id

        try:
            from nini.memory.db import get_session_db

            conn = get_session_db(session_dir, create=False)
            if conn is not None:
                try:
                    row = conn.execute("SELECT COUNT(*) FROM archived_messages").fetchone()
                    if row is not None:
                        return int(row[0] or 0)
                except sqlite3.OperationalError:
                    pass
                finally:
                    conn.close()
        except Exception:
            pass

        archive_dir = session_dir / "archive"
        if not archive_dir.exists():
            return 0

        count = 0
        for archive_file in sorted(archive_dir.glob("compressed_*.json")):
            try:
                raw = json.loads(archive_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            archive_messages = raw if isinstance(raw, list) else raw.get("messages", [])
            if not isinstance(archive_messages, list):
                continue
            count += sum(
                1 for entry in archive_messages if isinstance(entry, dict) and "role" in entry
            )
        return count

    def _parse_session_timestamp(self, value: Any) -> datetime | None:
        """解析会话时间戳，统一转换为 UTC aware datetime。"""
        if not isinstance(value, str) or not value.strip():
            return None
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _read_first_message_timestamp_iso(self, session_id: str) -> str | None:
        """从 memory.jsonl 读取首条有效消息时间，作为旧会话 created_at 的可靠来源。"""
        memory_path = self._memory_path(session_id)
        if not memory_path.exists():
            return None
        try:
            with memory_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict) or "role" not in entry:
                        continue
                    parsed = self._parse_session_timestamp(entry.get("_ts"))
                    if parsed is not None:
                        return parsed.isoformat()
        except OSError:
            return None
        return None

    def _session_sort_timestamp(self, item: dict[str, Any]) -> float:
        """返回会话排序时间戳；无效时间排到最后。"""
        parsed = self._parse_session_timestamp(item.get("updated_at"))
        if parsed is None:
            return 0.0
        return parsed.timestamp()

    def _derive_session_updated_at_iso(self, session_id: str, meta: dict[str, Any]) -> str:
        raw_updated = meta.get("updated_at")
        if isinstance(raw_updated, str) and raw_updated:
            return raw_updated

        memory_path = self._memory_path(session_id)
        if memory_path.exists():
            return datetime.fromtimestamp(memory_path.stat().st_mtime, timezone.utc).isoformat()

        session_dir = settings.sessions_dir / session_id
        if session_dir.exists():
            return datetime.fromtimestamp(session_dir.stat().st_mtime, timezone.utc).isoformat()

        return datetime.now(timezone.utc).isoformat()

    def _derive_session_created_at_iso(
        self,
        session_id: str,
        meta: dict[str, Any],
        fallback_updated: str,
    ) -> str:
        fallback_updated_dt = self._parse_session_timestamp(fallback_updated)
        raw_created = meta.get("created_at")
        created_dt = self._parse_session_timestamp(raw_created)
        if created_dt is not None:
            if fallback_updated_dt is None or created_dt <= fallback_updated_dt:
                return created_dt.isoformat()

        first_message_ts = self._read_first_message_timestamp_iso(session_id)
        first_message_dt = self._parse_session_timestamp(first_message_ts)
        if first_message_dt is not None:
            if fallback_updated_dt is None or first_message_dt <= fallback_updated_dt:
                return first_message_dt.isoformat()

        session_dir = settings.sessions_dir / session_id
        if session_dir.exists():
            dir_created = datetime.fromtimestamp(session_dir.stat().st_ctime, timezone.utc)
            if fallback_updated_dt is None or dir_created <= fallback_updated_dt:
                return dir_created.isoformat()
        return fallback_updated

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
        compression_segments: list[dict] | None = None,
    ) -> None:
        """持久化会话压缩元数据。"""
        fields: dict[str, Any] = {
            "compressed_context": compressed_context,
            "compressed_rounds": int(compressed_rounds),
            "last_compressed_at": last_compressed_at,
        }
        if compression_segments is not None:
            fields["compression_segments"] = compression_segments
        self._save_session_meta_fields(session_id, fields)

    def save_session_research_profile(self, session_id: str, research_profile_id: str) -> None:
        """持久化会话关联的研究画像标识。"""
        self._save_session_meta_fields(
            session_id,
            {"research_profile_id": str(research_profile_id or "").strip() or "default"},
        )

    def save_session_chart_preference(self, session_id: str, preference: str) -> None:
        """持久化会话图表输出格式偏好。"""
        if preference in ("interactive", "image"):
            self._save_session_meta_fields(session_id, {"chart_output_preference": preference})

    def save_session_recipe_context(
        self,
        session_id: str,
        *,
        task_kind: str,
        recipe_id: str | None,
        recipe_inputs: dict[str, Any] | None = None,
    ) -> None:
        """持久化 Recipe 绑定信息。"""
        self._save_session_meta_fields(
            session_id,
            {
                "task_kind": str(task_kind or "").strip() or "quick_task",
                "recipe_id": str(recipe_id or "").strip() or None,
                "recipe_inputs": recipe_inputs or {},
            },
        )

    def save_session_deep_task_state(
        self,
        session_id: str,
        deep_task_state: dict[str, Any],
    ) -> None:
        """持久化 deep task 状态。"""
        self._save_session_meta_fields(session_id, {"deep_task_state": deep_task_state})

    def save_session_pending_actions(
        self,
        session_id: str,
        pending_actions: list[dict[str, Any]],
    ) -> None:
        """持久化待处理动作账本。"""
        normalized = [dict(item) for item in pending_actions if isinstance(item, dict)]
        self._save_session_meta_fields(session_id, {"pending_actions": normalized})

    def save_subsession_metadata(
        self,
        session_id: str,
        *,
        parent_session_id: str,
        resource_owner_session_id: str,
    ) -> None:
        """持久化子会话审计元信息。"""
        self._save_session_meta_fields(
            session_id,
            {
                "is_subsession": True,
                "parent_session_id": str(parent_session_id or "").strip(),
                "resource_owner_session_id": str(resource_owner_session_id or "").strip(),
            },
        )

    def save_session_tool_approvals(
        self,
        session_id: str,
        tool_approval_grants: dict[str, Any],
    ) -> None:
        """持久化会话级工具放行状态。"""
        self._save_session_meta_fields(
            session_id,
            {"tool_approval_grants": self._normalize_tool_approval_grants(tool_approval_grants)},
        )

    def save_session_sandbox_import_approvals(
        self,
        session_id: str,
        sandbox_approved_imports: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        """持久化会话级沙盒扩展包授权。"""
        normalized = self._normalize_sandbox_import_approvals(sandbox_approved_imports)
        persistent = self._load_persistent_sandbox_import_approvals()
        session_only = sorted(normalized - persistent)
        self._save_session_meta_fields(
            session_id,
            {"sandbox_approved_imports": session_only},
        )

    @staticmethod
    def _normalize_tool_approval_grants(raw: Any) -> dict[str, str]:
        """规范化持久化的工具放行字典。"""
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, str] = {}
        for raw_key, raw_value in raw.items():
            key = str(raw_key or "").strip()
            value = str(raw_value or "").strip().lower()
            if not key or value != "session":
                continue
            normalized[key] = value
        return normalized

    @staticmethod
    def _normalize_sandbox_import_approvals(raw: Any) -> set[str]:
        """规范化持久化的沙盒扩展包授权集合。"""
        from nini.sandbox.policy import normalize_reviewable_import_roots

        if isinstance(raw, str):
            return normalize_reviewable_import_roots([raw])
        if isinstance(raw, (list, tuple, set)):
            return normalize_reviewable_import_roots(raw)
        return set()

    @staticmethod
    def _load_persistent_sandbox_import_approvals() -> set[str]:
        """读取永久级沙盒扩展包授权集合。"""
        from nini.sandbox.approval_manager import approval_manager

        return approval_manager.load_approved_imports()

    def _load_session_title(self, session_id: str) -> str:
        """从元数据文件读取会话标题。"""
        meta = self._load_session_meta(session_id)
        return str(meta.get("title", "新会话") or "新会话")

    def _load_session_meta(self, session_id: str) -> dict[str, Any]:
        """加载会话元数据。优先从 SQLite 读取，回退到 meta.json。"""
        if not session_persistence_enabled(session_id):
            return {}
        session_dir = settings.sessions_dir / session_id

        # 优先路径：SQLite
        try:
            from nini.memory.db import get_session_db, load_meta_from_db

            conn = get_session_db(session_dir, create=False)
            if conn is not None:
                try:
                    db_meta = load_meta_from_db(conn)
                    if db_meta:
                        return db_meta
                except Exception:
                    pass
                finally:
                    conn.close()
        except Exception:
            pass

        # Fallback：meta.json
        meta_path = session_dir / "meta.json"
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
        """持久化元数据字段。双写 meta.json + SQLite。"""
        if not session_persistence_enabled(session_id):
            return
        session_dir = settings.sessions_dir / session_id
        meta_path = session_dir / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = self._load_session_meta(session_id)
        meta.update(fields)
        now_iso = datetime.now(timezone.utc).isoformat()
        if "updated_at" not in fields:
            meta["updated_at"] = now_iso
        meta["created_at"] = self._derive_session_created_at_iso(
            session_id,
            meta,
            str(meta.get("updated_at") or now_iso),
        )

        # 主路径：写入 meta.json（保持现有行为，兼容直接读文件的测试）
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        # 次路径：写入 SQLite（失败不影响主路径）
        try:
            from nini.memory.db import get_session_db, upsert_meta_fields

            conn = get_session_db(session_dir, create=True)
            if conn is not None:
                try:
                    upsert_meta_fields(conn, meta)
                except Exception as exc:
                    logger.debug("[Session] SQLite 元数据双写失败: %s", exc)
                finally:
                    conn.close()
        except Exception:
            pass

    def save_session_token_usage(self, session_id: str, token_usage: dict[str, Any]) -> None:
        """保存会话的 Token 使用统计到 meta.json。"""
        self._save_session_meta_fields(session_id, {"token_usage": token_usage})

    def _session_exists_on_disk(self, session_id: str) -> bool:
        session_dir = settings.sessions_dir / session_id
        db_filename = getattr(settings, "session_db_filename", "session.db")
        return (
            (session_dir / "memory.jsonl").exists()
            or (session_dir / "knowledge.md").exists()
            or (session_dir / "workspace").exists()
            or (session_dir / "meta.json").exists()
            or (session_dir / db_filename).exists()
        )

    def _list_persisted_session_ids(self) -> list[str]:
        """列出有实际消息记录的会话ID（避免列出空目录）。"""
        root = settings.sessions_dir
        if not root.exists():
            return []
        db_filename = getattr(settings, "session_db_filename", "session.db")
        session_ids = []
        for p in root.iterdir():
            if p.is_dir():
                memory_path = p / "memory.jsonl"
                db_path = p / db_filename
                workspace_dir = p / "workspace"
                has_workspace_file = workspace_dir.exists() and any(
                    child.is_file() for child in workspace_dir.rglob("*")
                )
                if memory_path.exists() or db_path.exists() or has_workspace_file:
                    session_ids.append(p.name)
        return session_ids


# 全局单例
session_manager = SessionManager()
