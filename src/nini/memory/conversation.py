"""JSONL 会话记忆。

每个会话一个 .jsonl 文件，append-only 追加写入。
支持大型数据引用化，将超过阈值的数据保存到单独文件。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.config import settings

logger = logging.getLogger(__name__)


def _infer_event_type(entry: dict[str, Any]) -> str:
    """推断缺失的事件类型，兼容旧格式历史消息。"""
    role = str(entry.get("role", "")).strip()
    if role == "user":
        return "message"
    if role == "tool":
        return "tool_result"
    if role != "assistant":
        return ""

    tool_calls = entry.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        return "tool_call"
    if any(
        entry.get(key) is not None
        for key in ("reasoning_id", "reasoning_type", "key_decisions", "confidence_score")
    ):
        return "reasoning"
    return "text"


def canonicalize_message_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为历史消息补齐 canonical 元数据，兼容旧记录。"""
    canonical: list[dict[str, Any]] = []
    current_turn_id: str | None = None
    legacy_turn_seq = 0
    legacy_text_seq: dict[str, int] = {}
    legacy_reasoning_seq: dict[str, int] = {}
    legacy_tool_seq: dict[str, int] = {}

    for raw in entries:
        if not isinstance(raw, dict):
            continue

        entry = dict(raw)
        role = str(entry.get("role", "")).strip()
        if not role:
            canonical.append(entry)
            continue

        raw_turn_id = entry.get("turn_id")
        turn_id = str(raw_turn_id).strip() if isinstance(raw_turn_id, str) else ""
        if role == "user":
            if not turn_id:
                legacy_turn_seq += 1
                turn_id = f"legacy-turn-{legacy_turn_seq}"
                entry["turn_id"] = turn_id
            current_turn_id = turn_id
        else:
            if not turn_id:
                if not current_turn_id:
                    legacy_turn_seq += 1
                    current_turn_id = f"legacy-turn-{legacy_turn_seq}"
                turn_id = current_turn_id
                entry["turn_id"] = turn_id

        event_type = entry.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            event_type = _infer_event_type(entry)
            if event_type:
                entry["event_type"] = event_type
        else:
            event_type = event_type.strip()

        if role == "assistant":
            entry.setdefault("operation", "complete")
            if event_type == "text":
                message_id = entry.get("message_id")
                if not isinstance(message_id, str) or not message_id.strip():
                    seq = legacy_text_seq.get(turn_id, 0)
                    entry["message_id"] = f"legacy-message-{turn_id}-{seq}"
                    legacy_text_seq[turn_id] = seq + 1
            elif event_type == "reasoning":
                reasoning_id = entry.get("reasoning_id")
                if not isinstance(reasoning_id, str) or not reasoning_id.strip():
                    seq = legacy_reasoning_seq.get(turn_id, 0)
                    entry["reasoning_id"] = f"legacy-reasoning-{turn_id}-{seq}"
                    legacy_reasoning_seq[turn_id] = seq + 1
            elif event_type == "tool_call":
                tool_calls = entry.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    first_call = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
                    tool_call_id = (
                        str(first_call.get("id", "")).strip()
                        if isinstance(first_call, dict)
                        else ""
                    )
                    if tool_call_id:
                        entry.setdefault("message_id", f"tool-call-{tool_call_id}")
        elif role == "tool":
            entry.setdefault("event_type", "tool_result")
            entry.setdefault("operation", "complete")
            message_id = entry.get("message_id")
            if not isinstance(message_id, str) or not message_id.strip():
                tool_call_id_value = entry.get("tool_call_id")
                if isinstance(tool_call_id_value, str) and tool_call_id_value.strip():
                    entry["message_id"] = f"tool-result-{tool_call_id_value.strip()}"
                else:
                    seq = legacy_tool_seq.get(turn_id, 0)
                    entry["message_id"] = f"legacy-tool-{turn_id}-{seq}"
                    legacy_tool_seq[turn_id] = seq + 1
        elif role == "user":
            entry.setdefault("event_type", "message")

        canonical.append(entry)

    return canonical


class ConversationMemory:
    """基于 JSONL 的持久化会话记忆。"""

    # 大型数据字段列表（需要检测和引用化的字段）
    _LARGE_DATA_FIELDS = {
        "chart_data",
        "data_preview",
        "dataframe_preview",
        "images",
        "plotly_json",
    }

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._dir = settings.sessions_dir / session_id
        self._path = self._dir / "memory.jsonl"
        self._payloads_dir = self._dir / "workspace" / "artifacts" / "memory-payloads"

    def _ensure_dir(self) -> None:
        """确保目录存在（延迟创建）。"""
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)

    def _ensure_payloads_dir(self) -> None:
        """确保 payloads 目录存在。"""
        if not self._payloads_dir.exists():
            self._payloads_dir.mkdir(parents=True, exist_ok=True)

    def _calculate_size(self, data: Any) -> int:
        """计算数据序列化后的字节数。"""
        try:
            return len(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            return 0

    def _extract_large_payloads(self, entry: dict[str, Any]) -> dict[str, Any]:
        """提取大型数据到单独文件，返回引用化后的 entry。

        如果 entry 中包含超过阈值的大型数据字段，则：
        1. 将数据保存到 memory-payloads/{field}_{hash}.json
        2. 在 entry 中替换为引用：{"_ref": "memory-payloads/xxx.json"}
        """
        if not isinstance(entry, dict):
            return entry

        modified = False
        result = dict(entry)

        for field in self._LARGE_DATA_FIELDS:
            if field not in result:
                continue

            data = result[field]
            if data is None:
                continue

            # 计算数据大小
            size = self._calculate_size(data)
            threshold = settings.memory_large_payload_threshold_bytes

            if size < threshold:
                continue

            # 生成唯一文件名（基于内容哈希）
            content_hash = hashlib.md5(
                json.dumps(data, ensure_ascii=False, default=str, sort_keys=True).encode("utf-8")
            ).hexdigest()[:12]

            filename = f"{field}_{content_hash}.json"
            payload_path = self._payloads_dir / filename

            # 保存到文件
            try:
                self._ensure_payloads_dir()
                payload_path.write_text(
                    json.dumps(data, ensure_ascii=False, default=str, indent=2),
                    encoding="utf-8",
                )

                # 替换为引用
                result[field] = {
                    "_ref": f"memory-payloads/{filename}",
                    "_size_bytes": size,
                    "_type": type(data).__name__,
                }
                modified = True

                logger.info(f"[Memory] 大型数据引用化: {field} ({size} bytes) -> {filename}")
            except Exception as exc:
                logger.warning(f"[Memory] 保存大型数据失败: {field}, {exc}")

        return result if modified else entry

    def _resolve_references(self, entry: dict[str, Any]) -> dict[str, Any]:
        """解析引用，按需加载大型数据。

        如果 entry 中包含引用字段 {"_ref": "memory-payloads/xxx.json"}，
        则从文件加载数据并替换引用。
        """
        if not isinstance(entry, dict):
            return entry

        result = dict(entry)

        for field in self._LARGE_DATA_FIELDS:
            if field not in result:
                continue

            value = result[field]
            if not isinstance(value, dict) or "_ref" not in value:
                continue

            ref_path = value["_ref"]
            payload_path = self._dir / "workspace" / "artifacts" / ref_path

            # 加载引用数据
            try:
                if payload_path.exists():
                    data = json.loads(payload_path.read_text(encoding="utf-8"))
                    result[field] = data
                else:
                    logger.warning(f"[Memory] 引用文件不存在: {ref_path}")
            except Exception as exc:
                logger.warning(f"[Memory] 加载引用数据失败: {ref_path}, {exc}")

        return result

    def append(self, entry: dict[str, Any]) -> None:
        """追加一条记录，自动引用化大型数据。"""
        self._ensure_dir()

        # 提取大型数据到单独文件
        entry_with_refs = self._extract_large_payloads(entry)

        # 添加时间戳
        entry_with_refs.setdefault("_ts", datetime.now(timezone.utc).isoformat())

        # 写入 JSONL
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry_with_refs, ensure_ascii=False, default=str) + "\n")

    def load_all(self, *, resolve_refs: bool = False) -> list[dict[str, Any]]:
        """加载所有记录。

        Args:
            resolve_refs: 是否解析引用加载完整数据（默认不解析，保持引用状态）
        """
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if resolve_refs:
                            entry = self._resolve_references(entry)
                        entries.append(entry)
                    except json.JSONDecodeError:
                        logger.warning("跳过损坏的 JSONL 行: %s", line[:100])
        return entries

    def load_messages(self, *, resolve_refs: bool = False) -> list[dict[str, Any]]:
        """加载所有消息（过滤出 role 字段的记录）。

        Args:
            resolve_refs: 是否解析引用加载完整数据（默认不解析）
        """
        messages = [e for e in self.load_all(resolve_refs=resolve_refs) if "role" in e]
        return canonicalize_message_entries(messages)

    def clear(self) -> None:
        """清空会话记忆。"""
        if self._path.exists():
            self._path.unlink()


class InMemoryConversationMemory:
    """基于内存的会话记忆，不写磁盘，用于子 Agent 隔离上下文。"""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def append(self, entry: dict[str, Any]) -> None:
        """追加一条记录到内存。"""
        entry_copy = dict(entry)
        entry_copy.setdefault("_ts", datetime.now(timezone.utc).isoformat())
        self._entries.append(entry_copy)

    def load_all(self, *, resolve_refs: bool = False) -> list[dict[str, Any]]:
        """返回所有记录（参数 resolve_refs 忽略，内存中无引用）。"""
        return list(self._entries)

    def load_messages(self, *, resolve_refs: bool = False) -> list[dict[str, Any]]:
        """返回所有含 role 字段的消息。"""
        messages = [e for e in self._entries if "role" in e]
        return canonicalize_message_entries(messages)

    def clear(self) -> None:
        """清空内存记录。"""
        self._entries.clear()


def _build_entry_preview(entry: dict, max_chars: int = 200) -> str:
    """生成可读的条目摘要。"""
    role = entry.get("role", "")

    if role == "user":
        content = str(entry.get("content", ""))
        preview = content[:max_chars] + ("..." if len(content) > max_chars else "")
        return preview

    elif role == "assistant":
        content = str(entry.get("content", ""))
        tool_calls_raw = entry.get("tool_calls", [])
        tool_calls = tool_calls_raw if isinstance(tool_calls_raw, list) else []

        if tool_calls:
            tool_names = [
                tc.get("function", {}).get("name", "unknown")
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
            preview = f"[调用工具: {', '.join(tool_names)}]"
            if content:
                preview += f" {content[:100]}"
            return preview[:max_chars] + ("..." if len(preview) > max_chars else "")

        return content[:max_chars] + ("..." if len(content) > max_chars else "")

    elif role == "tool":
        content_str = str(entry.get("content", ""))
        return f"[工具结果] {content_str[:150]}..."

    return str(entry)[:max_chars] + ("..." if len(str(entry)) > max_chars else "")


def format_memory_entries(entries: list[dict]) -> list[dict]:
    """
    将 JSONL 条目格式化为可读的结构。

    返回格式：
    [
        {
            "index": 1,
            "timestamp": "2026-02-13T10:30:00+00:00",
            "role": "user",
            "type": "用户消息",
            "preview": "分析血压数据的相关性",
            "has_attachments": false,
            "raw": {...}  # 原始数据（可选）
        },
        ...
    ]
    """
    result = []
    for i, entry in enumerate(entries, 1):
        role = entry.get("role", "unknown")

        # 生成类型标签
        type_label = {
            "user": "用户消息",
            "assistant": "助手回复",
            "tool": "工具结果",
        }.get(role, "未知类型")

        # 生成预览文本
        preview = _build_entry_preview(entry, max_chars=200)

        # 检测大型数据引用
        has_attachments = any(
            isinstance(entry.get(field), dict) and "_ref" in entry.get(field, {})
            for field in ConversationMemory._LARGE_DATA_FIELDS
        )

        formatted = {
            "index": i,
            "timestamp": entry.get("_ts", ""),
            "role": role,
            "type": type_label,
            "preview": preview,
            "has_attachments": has_attachments,
        }
        result.append(formatted)

    return result
