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
        entry_with_refs["_ts"] = datetime.now(timezone.utc).isoformat()

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
        return [e for e in self.load_all(resolve_refs=resolve_refs) if "role" in e]

    def clear(self) -> None:
        """清空会话记忆。"""
        if self._path.exists():
            self._path.unlink()


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
