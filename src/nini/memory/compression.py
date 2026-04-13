"""会话压缩服务。

将长会话前半段历史归档到磁盘，并写入压缩摘要供后续上下文注入。
支持两种摘要模式：
- 轻量摘要（默认）：纯文本提取，不调用 LLM
- LLM 摘要：调用大模型生成 ≤500 字中文摘要，保留关键上下文
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.agent.session import session_persistence_enabled
from nini.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CompressionSegment:
    """单轮压缩产生的摘要段。

    depth=0 表示对原始对话的直接摘要；depth=1 表示对摘要的二次摘要。
    """

    summary: str
    archived_count: int
    created_at: str
    depth: int = 0  # 0=直接摘要, 1=摘要的摘要

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 json.dumps 的普通 dict。"""
        return {
            "summary": self.summary,
            "archived_count": self.archived_count,
            "created_at": self.created_at,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompressionSegment":
        """从 dict 反序列化。"""
        return cls(
            summary=str(data.get("summary", "")),
            archived_count=int(data.get("archived_count", 0)),
            created_at=str(data.get("created_at", "")),
            depth=int(data.get("depth", 0)),
        )


_LLM_SUMMARY_PROMPT = (
    "请将以下对话历史压缩为简洁的中文摘要（≤800字），必须保留：\n"
    "- 用户研究问题与分析目标\n"
    "- 数据集关键信息（样本量、缺失率、异常值）\n"
    "- 统计方法及选择理由\n"
    "- 具体数值结果（统计量、p值、效应量、置信区间，不得省略）\n"
    "- 关键结论与实际意义\n"
    "- 每个已完成步骤的关键输出（不超过一句）\n"
    "- PDCA 任务列表当前状态（ID、标题、状态）\n"
    "- 未解决的待处理动作及其影响\n"
    "只输出摘要，不要额外说明。\n\n"
    "对话历史：\n{conversation}"
)


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _strip_upload_mentions(text: str) -> str:
    """过滤摘要中含 upload/上传 关键词的整句，防止文件路径污染长期记忆。

    仅影响写入压缩摘要的文本，不修改原始 memory.jsonl。
    """
    lines = text.split("\n")
    result = []
    for line in lines:
        # 按句末标点分割，过滤含关键词的片段
        sentences = re.split(r"(?<=[。！？.!?])\s*", line)
        kept = [s for s in sentences if not re.search(r"upload|上传", s, re.IGNORECASE)]
        if kept:
            result.append("".join(kept).rstrip())
    return "\n".join(result).strip()


def _trim_text(value: Any, *, max_len: int = 180) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _summarize_messages(messages: list[dict[str, Any]], *, max_items: int = 20) -> str:
    """生成结构化轻量摘要（无 LLM 调用）。

    借鉴 claw-code 的结构化提取模式，按类别提取关键信息而非逐条截取。
    组装顺序：timeline 在前（截断时优先丢弃），结构化信息在后（优先保留）。
    """
    # 1. 消息范围统计
    roles = Counter(str(m.get("role", "unknown")) for m in messages)
    scope = (
        f"已压缩 {len(messages)} 条消息"
        f"（用户={roles.get('user', 0)}, "
        f"助手={roles.get('assistant', 0)}, "
        f"工具={roles.get('tool', 0)}）"
    )

    # 2. 提取各类结构化信息
    tools_used = _extract_tools_used(messages)
    datasets = _extract_datasets_referenced(messages)
    recent_requests = _extract_recent_user_requests(messages, limit=3, max_chars=160)
    stat_results = _extract_stat_results(messages)
    tool_failures = _extract_tool_failures(messages)
    pending = _extract_pending_tasks(messages)
    # timeline 降低预算：max_items=15, max_chars=100，减少空间占用
    timeline = _build_timeline(messages[:max_items], max_chars=100)

    # 3. 组装（timeline 在前，重要信息在后；截断从尾部保留时重要信息优先保留）
    parts = []
    if timeline:
        parts.append("时间线:\n" + "\n".join(f"  - {t}" for t in timeline))
    if tools_used:
        parts.append(f"使用工具: {', '.join(tools_used)}")
    if datasets:
        parts.append(f"涉及数据集: {', '.join(datasets)}")
    if recent_requests:
        parts.append("最近用户请求:\n" + "\n".join(f"  - {r}" for r in recent_requests))
    if stat_results:
        parts.append("关键统计结果:\n" + "\n".join(f"  - {r}" for r in stat_results))
    if tool_failures:
        parts.append("工具失败记录:\n" + "\n".join(f"  - {f}" for f in tool_failures))
    if pending:
        parts.append("待办事项:\n" + "\n".join(f"  - {p}" for p in pending))
    parts.append(scope)
    return "\n".join(parts)


def _extract_tools_used(messages: list[dict[str, Any]]) -> list[str]:
    """从 assistant 消息的 tool_calls 中提取工具名（去重排序）。"""
    names: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                func = tc.get("function", {})
                if isinstance(func, dict):
                    name = str(func.get("name", "")).strip()
                    if name:
                        names.add(name)
    return sorted(names)


def _extract_datasets_referenced(messages: list[dict[str, Any]]) -> list[str]:
    """从工具参数中提取 dataset_name（去重）。"""
    datasets: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            func = tc.get("function", {})
            if not isinstance(func, dict):
                continue
            args_str = str(func.get("arguments", ""))
            try:
                args = json.loads(args_str) if args_str.strip().startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            ds_name = str(args.get("dataset_name", "")).strip()
            if ds_name:
                datasets.add(ds_name)
    return sorted(datasets)


_STAT_RESULT_RE = re.compile(
    r"(?:p[\s_-]*(?:value)?[\s=:：]*[\d.eE\-]+)"
    r"|(?:effect[\s_]*size[\s=:：]*[\d.eE\-]+)"
    r"|(?:statistic[\s=:：]*[\d.eE\-]+)"
    r"|(?:r[\s=:：]*[\d.]+)"
    r"|(?:CI[\s=:：]*[\[(][\d.,\s\-]+[\])])",
    re.IGNORECASE,
)


def _extract_stat_results(messages: list[dict[str, Any]]) -> list[str]:
    """从 tool 消息中提取统计结果（p 值、效应量等关键数值）。"""
    results: list[str] = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content", ""))
        try:
            payload = json.loads(content) if content.strip().startswith("{") else None
        except (json.JSONDecodeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            stat_summary = payload.get("stat_summary")
            if isinstance(stat_summary, dict):
                pairwise = stat_summary.get("pairwise")
                if isinstance(pairwise, list) and pairwise:
                    for pair in pairwise[:3]:
                        if not isinstance(pair, dict):
                            continue
                        left = str(pair.get("var_a", "")).strip()
                        right = str(pair.get("var_b", "")).strip()
                        if not left or not right:
                            continue
                        line_parts = [f"{left} vs {right}"]
                        coefficient = pair.get("coefficient")
                        p_value = pair.get("p_value")
                        if isinstance(coefficient, (int, float)):
                            line_parts.append(f"r={float(coefficient):.4f}")
                        if isinstance(p_value, (int, float)):
                            line_parts.append(f"p={float(p_value):.4g}")
                        significant = pair.get("significant")
                        if isinstance(significant, bool):
                            line_parts.append("显著" if significant else "不显著")
                        line = "，".join(line_parts)
                        if line not in results:
                            results.append(line)
                    if results:
                        continue
        matches = _STAT_RESULT_RE.findall(content)
        if matches:
            # 取前 5 个匹配，每个截断
            for m in matches[:5]:
                trimmed = _trim_text(m, max_len=80)
                if trimmed and trimmed not in results:
                    results.append(trimmed)
        if len(results) >= 10:
            break
    return results


def _extract_tool_failures(messages: list[dict[str, Any]]) -> list[str]:
    """从工具结果中提取失败记录，确保压缩后 LLM 仍感知到错误状态。"""
    failures: list[str] = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        if msg.get("status") != "error":
            continue
        content = str(msg.get("content", ""))
        try:
            data = json.loads(content) if content.strip().startswith("{") else None
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            tool_name = str(msg.get("tool_name", "") or msg.get("name", "")).strip()
            error_code = str(data.get("error_code", "")).strip()
            err_msg = _trim_text(data.get("message", ""), max_len=120)
            is_duplicate = bool(data.get("metadata", {}).get("duplicate_profile_blocked", False))
            if is_duplicate:
                line = f"{tool_name or '未知工具'} 重复调用（已成功）: {err_msg}"
            else:
                line = f"{tool_name or '未知工具'} 失败: {err_msg}"
                if error_code:
                    line += f" [{error_code}]"
            if line not in failures:
                failures.append(line)
        if len(failures) >= 5:
            break
    return failures


def _extract_pending_tasks(messages: list[dict[str, Any]]) -> list[str]:
    """从 task_state 工具结果中提取 pending/in_progress 的任务。"""
    pending: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content", ""))
        # 尝试解析 task_state 的 JSON 结果
        try:
            data = json.loads(content) if content.strip().startswith("{") else None
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            tasks = (
                data.get("data", {}).get("tasks") if isinstance(data.get("data"), dict) else None
            )
            if isinstance(tasks, list):
                for t in tasks:
                    if isinstance(t, dict):
                        status = str(t.get("status", "")).lower()
                        if status in ("pending", "in_progress"):
                            title = _trim_text(t.get("title", t.get("name", "")), max_len=100)
                            if title:
                                pending.append(f"[{status}] {title}")
                if pending:
                    return pending[:8]
    return pending[:8]


def _extract_recent_user_requests(
    messages: list[dict[str, Any]], *, limit: int = 3, max_chars: int = 160
) -> list[str]:
    """提取最后 N 条用户消息内容。"""
    requests: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            text = _trim_text(msg.get("content", ""), max_len=max_chars)
            if text:
                requests.append(text)
            if len(requests) >= limit:
                break
    requests.reverse()
    return requests


def _is_task_management_tool(name: str) -> bool:
    """判断工具名是否属于任务管理类（应在 timeline 中折叠）。"""
    return name in ("task_state", "task_write")


def _build_timeline(messages: list[dict[str, Any]], *, max_chars: int = 160) -> list[str]:
    """构建消息时间线摘要，连续的 task_state/task_write 调用折叠为一行。"""
    timeline: list[str] = []
    # 折叠计数器：连续的任务管理工具调用次数
    _task_mgmt_count: int = 0

    def _flush_task_mgmt() -> None:
        """将累积的任务管理工具条目折叠写入 timeline。"""
        nonlocal _task_mgmt_count
        if _task_mgmt_count > 0:
            if _task_mgmt_count == 1:
                timeline.append("[助手] task_state")
            else:
                timeline.append(f"[助手] task_state (×{_task_mgmt_count}，已折叠)")
            _task_mgmt_count = 0

    for msg in messages:
        role = str(msg.get("role", "unknown")).strip()

        # 检测 assistant 消息是否仅包含任务管理工具
        if role == "assistant" and msg.get("tool_calls"):
            names = []
            for tc in (msg.get("tool_calls") or [])[:4]:
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    if isinstance(func, dict):
                        name = str(func.get("name", "")).strip()
                        if name:
                            names.append(name)
            is_only_task_mgmt = names and all(_is_task_management_tool(n) for n in names)

            if is_only_task_mgmt:
                # 连续的任务管理工具：累加计数，不立即写入
                _task_mgmt_count += 1
                continue
            else:
                # 非任务管理工具：先 flush 累积的 task_mgmt 条目
                _flush_task_mgmt()
                text = _trim_text(msg.get("content", ""), max_len=100)
                tool_info = f"调用 {', '.join(names)}" if names else ""
                entry = f"[助手] {tool_info}"
                if text:
                    entry += f" {text}"
                timeline.append(_trim_text(entry, max_len=max_chars))
                continue

        # tool 消息：跳过 task_state/task_write 的结果（已在上方折叠）
        if role == "tool":
            # 检查是否是任务管理工具的结果（通过上下文推断）
            # task_state 结果的特征：content 包含 task_state 相关 JSON
            content_str = str(msg.get("content", ""))
            if _task_mgmt_count > 0:
                # 跳过与折叠的 task_mgmt 调用配对的 tool result
                continue
            content = _trim_text(content_str, max_len=max_chars)
            timeline.append(f"[工具结果] {content}")
            continue

        # 其他消息（user、reasoning 等）：先 flush
        _flush_task_mgmt()
        content = _trim_text(msg.get("content", ""), max_len=max_chars)
        timeline.append(f"[{role}] {content}")

    # 处理末尾残留的折叠条目
    _flush_task_mgmt()
    return timeline


def _format_messages_for_llm(messages: list[dict[str, Any]], *, max_chars: int = 8000) -> str:
    """将消息列表格式化为 LLM 可读的对话文本。"""
    lines: list[str] = []
    total_chars = 0
    for msg in messages:
        role = str(msg.get("role", "")).strip() or "unknown"
        content = str(msg.get("content", "")).strip()

        if role == "tool":
            content = _trim_text(content, max_len=200)
            line = f"[工具结果] {content}"
        elif role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls", [])
            names = []
            for item in (tool_calls or [])[:4]:
                if isinstance(item, dict):
                    func = item.get("function", {})
                    if isinstance(func, dict):
                        name = str(func.get("name", "")).strip()
                        if name:
                            names.append(name)
            tool_info = f"（调用工具: {', '.join(names)}）" if names else ""
            text = _trim_text(content, max_len=300) if content else ""
            line = f"[助手]{tool_info} {text}".strip()
        elif role == "user":
            line = f"[用户] {_trim_text(content, max_len=500)}"
        elif role == "assistant":
            line = f"[助手] {_trim_text(content, max_len=500)}"
        else:
            line = f"[{role}] {_trim_text(content, max_len=200)}"

        if total_chars + len(line) > max_chars:
            lines.append("... (后续消息已省略)")
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


async def _llm_summarize(messages: list[dict[str, Any]]) -> str | None:
    """调用 LLM 生成对话摘要。失败时返回 None。"""
    try:
        from nini.agent.model_resolver import model_resolver

        conversation_text = _format_messages_for_llm(messages)
        prompt = _LLM_SUMMARY_PROMPT.format(conversation=conversation_text)

        response = await model_resolver.chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            purpose="chat",
        )
        summary = response.text.strip()
        if summary:
            # 确保不超过 800 字（放宽以保留科研数值细节和 PDCA 任务状态）
            if len(summary) > 800:
                summary = summary[:800] + "..."
            logger.info("LLM 对话摘要生成成功 (%d 字)", len(summary))
            return summary
    except Exception:
        logger.warning("LLM 对话摘要生成失败，回退到轻量摘要", exc_info=True)
    return None


async def try_merge_oldest_segments(session: Session, max_segments: int) -> None:
    """当 compression_segments 段数超限时，尝试 LLM 合并最旧的两段为 depth=1 摘要。

    LLM 合并成功时：最旧两段被替换为一个 depth=1 新段，总段数净减少 1。
    LLM 合并失败时：维持 set_compressed_context() 已丢弃最旧段的结果，不额外操作。
    无论是否合并，均从最终 compression_segments 重新 join 覆写 compressed_context
    （不应用 compressed_context_max_chars 截断）。
    """
    if len(session.compression_segments) <= max_segments:
        return

    if len(session.compression_segments) < 2:
        # 段数不足以合并，直接 join 覆写
        session.compressed_context = "\n\n---\n\n".join(
            s["summary"] for s in session.compression_segments
        )
        return

    oldest_two = session.compression_segments[:2]
    combined_messages = [
        {"role": "assistant", "content": oldest_two[0]["summary"]},
        {"role": "assistant", "content": oldest_two[1]["summary"]},
    ]

    merged_summary: str | None = None
    try:
        merged_summary = await _llm_summarize(combined_messages)
    except Exception:
        logger.warning("LLM 合并最旧段时发生异常", exc_info=True)

    if merged_summary:
        # 替换最旧的两段为 depth=1 合并段
        merged_count = int(oldest_two[0].get("archived_count", 0)) + int(
            oldest_two[1].get("archived_count", 0)
        )
        merged_seg = CompressionSegment(
            summary=merged_summary,
            archived_count=merged_count,
            created_at=datetime.now(timezone.utc).isoformat(),
            depth=1,
        ).to_dict()
        session.compression_segments = [merged_seg] + session.compression_segments[2:]
        logger.info(
            "LLM 合并最旧两段成功 (depth=1), segments=%d", len(session.compression_segments)
        )

    # 无论是否合并，覆写 compressed_context（不截断）
    session.compressed_context = "\n\n---\n\n".join(
        s["summary"] for s in session.compression_segments
    )


def _archive_messages(session_id: str, messages: list[dict[str, Any]]) -> Path:
    archive_dir = settings.sessions_dir / session_id / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"compressed_{_now_ts()}_{uuid.uuid4().hex[:8]}.json"
    archive_path.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _append_to_search_index(archive_dir, archive_path.name, messages)
    return archive_path


def _append_to_search_index(
    archive_dir: Path, filename: str, messages: list[dict[str, Any]]
) -> None:
    """将归档消息写入 SQLite archived_messages + FTS5 索引。

    优先写入 session.db（SQLite 路径）；SQLite 不可用时 fallback 到 search_index.jsonl。
    失败时静默跳过，不影响归档主流程。
    """
    session_dir = (
        archive_dir.parent
    )  # sessions_dir / session_id / archive -> sessions_dir / session_id

    # 优先路径：写入 SQLite
    try:
        from nini.memory.db import (
            get_indexed_archive_files,
            get_session_db,
            insert_archived_messages_bulk,
        )

        conn = get_session_db(session_dir, create=True)
        if conn is not None:
            try:
                # 检查是否已被迁移（避免 migration + insert 导致重复）
                already_indexed = get_indexed_archive_files(conn)
                if filename in already_indexed:
                    return  # 已在迁移时写入，无需重复插入
                insert_archived_messages_bulk(conn, filename, messages)
                return  # 写入成功，直接返回
            except Exception as exc:
                logger.warning("[DB] 写入归档索引到 SQLite 失败，回退到 JSONL: %s", exc)
            finally:
                conn.close()
    except Exception as exc:
        logger.warning("[DB] 打开 SQLite 失败，回退到 JSONL: %s", exc)

    # Fallback 路径：写入 search_index.jsonl
    try:
        from nini.tools.search_archive import _extract_message_text
    except Exception:
        return

    index_path = archive_dir / "search_index.jsonl"
    try:
        with index_path.open("a", encoding="utf-8") as f:
            for msg in messages:
                text = _extract_message_text(msg)
                if not text:
                    continue
                entry = {
                    "file": filename,
                    "role": str(msg.get("role", "unknown")),
                    "text": text,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("更新归档搜索索引失败: %s", archive_dir, exc_info=True)


def _append_pending_actions_to_summary(summary: str, pending_actions: list[dict]) -> str:
    """将 session.pending_actions 的摘要追加到压缩摘要末尾。

    确保压缩后 LLM 仍能感知到未解决的待处理动作（如工具失败记录），
    避免 recovery 阶段因丢失上下文而无法自救。
    """
    if not pending_actions:
        return summary
    pa_lines = []
    for pa in pending_actions[:5]:
        blocking_tag = "[阻塞]" if pa.get("blocking", True) else "[非阻塞]"
        pa_type = str(pa.get("type", "unknown")).strip()
        pa_key = str(pa.get("key", "")).strip()
        key_hint = f" (key={pa_key})" if pa_key else ""
        pa_lines.append(f"  - {blocking_tag} [{pa_type}]{key_hint} {pa.get('summary', '未知')}")
    return summary + "\n\n当前待处理动作:\n" + "\n".join(pa_lines)


def compress_session_history(
    session: Session,
    *,
    ratio: float = 0.5,
    min_messages: int = 4,
) -> dict[str, Any]:
    """压缩会话历史并返回执行结果（轻量摘要模式）。"""
    total = len(session.messages)
    if total < min_messages:
        return {
            "success": False,
            "message": f"消息数量不足，至少需要 {min_messages} 条消息才可压缩",
            "archived_count": 0,
            "remaining_count": total,
        }

    ratio = min(max(ratio, 0.1), 0.9)
    # min_messages 表示"最少保留数"，归档其余部分，并受 ratio 限制单次归档比例
    archive_count = total - min_messages
    archive_count = min(archive_count, int(total * ratio))
    archive_count = max(1, archive_count)
    if archive_count >= total:
        archive_count = max(total - 1, 1)

    archived = session.messages[:archive_count]
    remaining = session.messages[archive_count:]
    if not archived:
        return {
            "success": False,
            "message": "没有可归档的消息",
            "archived_count": 0,
            "remaining_count": total,
        }

    summary = _strip_upload_mentions(_summarize_messages(archived))
    # 追加 pending_actions 状态到摘要，确保压缩后 LLM 仍感知待处理动作
    summary = _append_pending_actions_to_summary(summary, session.pending_actions)
    archive_path: Path | None = None
    if session_persistence_enabled(session.id):
        archive_path = _archive_messages(session.id, archived)

    session.messages = remaining
    session._rewrite_conversation_memory()
    session.set_compressed_context(summary)

    return {
        "success": True,
        "message": "会话压缩完成",
        "summary": summary,
        "summary_mode": "lightweight",
        "archive_path": str(archive_path) if archive_path is not None else "",
        "archived_count": len(archived),
        "remaining_count": len(remaining),
        "compressed_rounds": session.compressed_rounds,
        "last_compressed_at": session.last_compressed_at,
    }


async def compress_session_history_with_llm(
    session: Session,
    *,
    ratio: float = 0.5,
    min_messages: int = 4,
) -> dict[str, Any]:
    """压缩会话历史（LLM 摘要模式）。

    优先使用 LLM 生成高质量中文摘要，失败时自动回退到轻量摘要。
    """
    total = len(session.messages)
    if total < min_messages:
        return {
            "success": False,
            "message": f"消息数量不足，至少需要 {min_messages} 条消息才可压缩",
            "archived_count": 0,
            "remaining_count": total,
        }

    ratio = min(max(ratio, 0.1), 0.9)
    # min_messages 表示"最少保留数"，归档其余部分，并受 ratio 限制单次归档比例
    archive_count = total - min_messages
    archive_count = min(archive_count, int(total * ratio))
    archive_count = max(1, archive_count)
    if archive_count >= total:
        archive_count = max(total - 1, 1)

    archived = session.messages[:archive_count]
    remaining = session.messages[archive_count:]
    if not archived:
        return {
            "success": False,
            "message": "没有可归档的消息",
            "archived_count": 0,
            "remaining_count": total,
        }

    # 尝试 LLM 摘要
    summary = await _llm_summarize(archived)
    summary_mode = "llm"
    if summary is None:
        summary = _summarize_messages(archived)
        summary_mode = "lightweight"

    # 过滤上传文件路径，防止污染长期记忆
    summary = _strip_upload_mentions(summary)

    # 追加 pending_actions 状态到摘要，确保压缩后 LLM 仍感知待处理动作
    summary = _append_pending_actions_to_summary(summary, session.pending_actions)

    archive_path = _archive_messages(session.id, archived)

    session.messages = remaining
    session._rewrite_conversation_memory()
    session.set_compressed_context(summary)

    # LLM 路径：尝试将最旧两段合并为 depth=1 摘要（段数超限时）
    await try_merge_oldest_segments(session, settings.compressed_context_max_segments)

    return {
        "success": True,
        "message": "会话压缩完成",
        "summary": summary,
        "summary_mode": summary_mode,
        "archive_path": str(archive_path),
        "archived_count": len(archived),
        "remaining_count": len(remaining),
        "compressed_rounds": session.compressed_rounds,
        "last_compressed_at": session.last_compressed_at,
    }


def rollback_compression(session: Session) -> dict[str, Any]:
    """回滚最近一次压缩，将最新归档消息恢复到当前会话。"""
    archive_dir = settings.sessions_dir / session.id / "archive"
    if not archive_dir.exists() or not archive_dir.is_dir():
        return {"success": False, "message": "未找到压缩归档目录"}

    archive_files = sorted(
        archive_dir.glob("compressed_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not archive_files:
        return {"success": False, "message": "未找到可回滚的压缩记录"}

    latest_archive = archive_files[0]
    try:
        payload = json.loads(latest_archive.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "message": f"读取压缩归档失败: {exc}"}

    if not isinstance(payload, list):
        return {"success": False, "message": "压缩归档格式无效"}

    restored_messages = [item for item in payload if isinstance(item, dict)]
    if not restored_messages:
        return {"success": False, "message": "压缩归档中没有可恢复消息"}

    session.messages = [*restored_messages, *session.messages]
    session._rewrite_conversation_memory()
    session.compressed_rounds = max(0, session.compressed_rounds - 1)
    if session.compressed_rounds == 0:
        session.compressed_context = ""
        session.last_compressed_at = None

    return {
        "success": True,
        "message": "会话压缩已回滚",
        "restored_count": len(restored_messages),
        "archive_path": str(latest_archive),
        "compressed_rounds": session.compressed_rounds,
        "last_compressed_at": session.last_compressed_at,
    }


# ---- 向后兼容：结构化记忆类型和函数从 analysis_memory 模块重导出 ----

from nini.memory.analysis_memory import (  # noqa: E402,F401
    AnalysisMemory,
    Artifact,
    Decision,
    Finding,
    StatisticResult,
    clear_session_analysis_memories,
    clear_session_analysis_memory_cache,
    get_analysis_memory,
    list_session_analysis_memories,
    load_analysis_memory,
    remove_analysis_memory,
    save_analysis_memory,
)

