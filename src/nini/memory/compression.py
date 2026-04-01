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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nini.agent.session import Session
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
    "你是一位专业的科研助手。请将以下对话历史压缩为一段简洁的中文摘要，"
    "**必须**保留以下信息：\n"
    "① 用户研究问题与分析目标\n"
    "② 数据集关键信息（样本量、缺失率、异常值情况）\n"
    "③ 统计方法及选择理由\n"
    "④ **具体数值结果**（检验统计量、p 值、效应量、置信区间等，不得省略）\n"
    "⑤ 关键结论与实际意义\n"
    "⑥ 每个已完成分析步骤的关键输出（如统计量、发现的规律），不超过一句话\n"
    "⑦ PDCA 任务列表的当前状态（每个任务的 ID、标题、状态：completed/in_progress/pending）\n"
    "⑧ 当前仍未解决的待处理动作（pending_actions）及其影响\n"
    "摘要不超过 800 字。只输出摘要内容，不要添加额外说明。\n\n"
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


def _summarize_messages(messages: list[dict[str, Any]], *, max_items: int = 30) -> str:
    """生成轻量摘要，避免再引入一次模型调用。"""
    lines: list[str] = []
    for msg in messages[:max_items]:
        role = str(msg.get("role", "")).strip() or "unknown"
        if role == "tool":
            tool_id = _trim_text(msg.get("tool_call_id", ""), max_len=32)
            # tool_result 包含统计数值等关键结果，给予更多空间
            content = _trim_text(msg.get("content", ""), max_len=300)
            lines.append(f"- [tool:{tool_id}] {content}")
            continue

        content = _trim_text(msg.get("content", ""), max_len=140)
        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls", [])
            if isinstance(tool_calls, list) and tool_calls:
                names = []
                for item in tool_calls[:4]:
                    if isinstance(item, dict):
                        func = item.get("function", {})
                        if isinstance(func, dict):
                            name = str(func.get("name", "")).strip()
                            if name:
                                names.append(name)
                if names:
                    lines.append(f"- [assistant] 调用了工具: {', '.join(names)}")
                    if content:
                        lines.append(f"- [assistant] {content}")
                    continue
        lines.append(f"- [{role}] {content}")

    if len(messages) > max_items:
        lines.append(f"- ... 其余 {len(messages) - max_items} 条消息已省略")

    return "\n".join(lines).strip()


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
    archive_path = _archive_messages(session.id, archived)

    session.messages = remaining
    session._rewrite_conversation_memory()
    session.set_compressed_context(summary)

    return {
        "success": True,
        "message": "会话压缩完成",
        "summary": summary,
        "summary_mode": "lightweight",
        "archive_path": str(archive_path),
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


# ---- 结构化记忆压缩 ----


def _analysis_memory_dir(session_id: str) -> Path:
    """返回会话的 AnalysisMemory 持久化目录。"""
    path = settings.sessions_dir / session_id / "analysis_memories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _analysis_memory_path(session_id: str, dataset_name: str) -> Path:
    """返回指定数据集的 AnalysisMemory 文件路径。"""
    safe_name = quote(dataset_name, safe="")
    return _analysis_memory_dir(session_id) / f"{safe_name}.json"


@dataclass
class Finding:
    """分析发现记录。

    用于记录分析过程中的关键发现，如统计显著性、效应量、数据问题等。
    """

    category: str  # 发现类别
    summary: str  # 简短总结
    detail: str = ""  # 详细描述
    confidence: float = 1.0  # 置信度 (0-1)
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    ltm_id: str = ""  # 已沉淀到长期记忆的条目 ID，非空表示已写入


@dataclass
class StatisticResult:
    """统计结果记录。

    记录统计检验的结果，便于后续引用和解释。
    """

    test_name: str  # 检验名称
    test_statistic: float | None = None  # 检验统计量
    p_value: float | None = None  # p 值
    degrees_of_freedom: int | None = None  # 自由度
    effect_size: float | None = None  # 效应量
    effect_type: str = ""  # 效应量类型 (cohens_d, eta_squared 等)
    confidence_interval_lower: float | None = None  # 置信区间下限
    confidence_interval_upper: float | None = None  # 置信区间上限
    confidence_level: float = 0.95  # 置信水平
    significant: bool = False  # 是否显著
    ltm_id: str = ""  # 已沉淀到长期记忆的条目 ID，非空表示已写入


@dataclass
class Decision:
    """决策记录。

    记录分析过程中的决策，如方法选择、参数选择等。
    """

    decision_type: str  # 决策类型
    chosen: str  # 选择的方法/参数
    alternatives: list[str] = field(default_factory=list)  # 考虑的替代方案
    rationale: str = ""  # 决策理由
    confidence: float = 1.0  # 决策置信度
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    ltm_id: str = ""  # 已沉淀到长期记忆的条目 ID，非空表示已写入


@dataclass
class Artifact:
    """产出文件记录。

    记录分析过程中生成的文件，如图表、报告等。
    """

    artifact_type: str  # 文件类型 (chart, report, data)
    path: str  # 文件路径
    description: str = ""  # 描述
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据
    timestamp: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class AnalysisMemory:
    """结构化分析记忆。

    将分析结果提取为结构化知识，而非简单文本摘要。
    支持转换为可注入的上下文，用于后续分析。
    """

    session_id: str
    dataset_name: str
    findings: list[Finding] = field(default_factory=list)
    statistics: list[StatisticResult] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: __import__("time").time())
    updated_at: float = field(default_factory=lambda: __import__("time").time())

    def add_finding(self, finding: Finding) -> None:
        """添加发现记录。"""
        self.findings.append(finding)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def add_statistic(self, statistic: StatisticResult) -> None:
        """添加统计结果。"""
        self.statistics.append(statistic)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def add_decision(self, decision: Decision) -> None:
        """添加决策记录。"""
        self.decisions.append(decision)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def add_artifact(
        self,
        artifact_type: str,
        path: str,
        description: str = "",
        **metadata: Any,
    ) -> None:
        """添加产出文件记录。"""
        artifact = Artifact(
            artifact_type=artifact_type,
            path=path,
            description=description,
            metadata=metadata,
        )
        self.artifacts.append(artifact)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def summary(self) -> str:
        """生成摘要文本。"""
        parts: list[str] = []

        if self.findings:
            parts.append(f"关键发现 ({len(self.findings)} 项)")

        if self.statistics:
            parts.append(f"统计结果 ({len(self.statistics)} 项)")

        if self.decisions:
            parts.append(f"决策记录 ({len(self.decisions)} 项)")

        if self.artifacts:
            parts.append(f"产出文件 ({len(self.artifacts)} 个)")

        if not parts:
            return "分析记忆为空"

        return "、".join(parts) + f"（数据集: {self.dataset_name}）"

    def to_context(self) -> dict[str, Any]:
        """转换为可注入的上下文。"""
        return {
            "dataset_name": self.dataset_name,
            "findings": [
                {
                    "category": f.category,
                    "summary": f.summary,
                    "detail": f.detail,
                    "confidence": f.confidence,
                }
                for f in self.findings
            ],
            "statistics": [
                {
                    "test_name": s.test_name,
                    "test_statistic": s.test_statistic,
                    "p_value": s.p_value,
                    "effect_size": s.effect_size,
                    "effect_type": s.effect_type,
                    "significant": s.significant,
                }
                for s in self.statistics
            ],
            "decisions": [
                {
                    "type": d.decision_type,
                    "chosen": d.chosen,
                    "rationale": d.rationale,
                }
                for d in self.decisions
            ],
            "artifacts": [
                {
                    "type": a.artifact_type,
                    "path": a.path,
                    "description": a.description,
                }
                for a in self.artifacts
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）。"""
        return {
            "session_id": self.session_id,
            "dataset_name": self.dataset_name,
            "findings": [
                {
                    "category": f.category,
                    "summary": f.summary,
                    "detail": f.detail,
                    "confidence": f.confidence,
                    "timestamp": f.timestamp,
                    "ltm_id": f.ltm_id,
                }
                for f in self.findings
            ],
            "statistics": [
                {
                    "test_name": s.test_name,
                    "test_statistic": s.test_statistic,
                    "p_value": s.p_value,
                    "degrees_of_freedom": s.degrees_of_freedom,
                    "effect_size": s.effect_size,
                    "effect_type": s.effect_type,
                    "significant": s.significant,
                    "ltm_id": s.ltm_id,
                }
                for s in self.statistics
            ],
            "decisions": [
                {
                    "decision_type": d.decision_type,
                    "chosen": d.chosen,
                    "alternatives": d.alternatives,
                    "rationale": d.rationale,
                    "confidence": d.confidence,
                    "timestamp": d.timestamp,
                    "ltm_id": d.ltm_id,
                }
                for d in self.decisions
            ],
            "artifacts": [
                {
                    "artifact_type": a.artifact_type,
                    "path": a.path,
                    "description": a.description,
                    "metadata": a.metadata,
                    "timestamp": a.timestamp,
                }
                for a in self.artifacts
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisMemory:
        """从字典恢复 AnalysisMemory。"""
        return cls(
            session_id=str(data.get("session_id", "")).strip(),
            dataset_name=str(data.get("dataset_name", "")).strip(),
            findings=[
                Finding(
                    category=str(item.get("category", "")),
                    summary=str(item.get("summary", "")),
                    detail=str(item.get("detail", "")),
                    confidence=float(item.get("confidence", 1.0)),
                    timestamp=float(item.get("timestamp", 0.0)),
                    ltm_id=str(item.get("ltm_id", "")),
                )
                for item in data.get("findings", [])
                if isinstance(item, dict)
            ],
            statistics=[
                StatisticResult(
                    test_name=str(item.get("test_name", "")),
                    test_statistic=(
                        float(item["test_statistic"])
                        if item.get("test_statistic") is not None
                        else None
                    ),
                    p_value=float(item["p_value"]) if item.get("p_value") is not None else None,
                    degrees_of_freedom=(
                        int(item["degrees_of_freedom"])
                        if item.get("degrees_of_freedom") is not None
                        else None
                    ),
                    effect_size=(
                        float(item["effect_size"]) if item.get("effect_size") is not None else None
                    ),
                    effect_type=str(item.get("effect_type", "")),
                    significant=bool(item.get("significant", False)),
                    ltm_id=str(item.get("ltm_id", "")),
                )
                for item in data.get("statistics", [])
                if isinstance(item, dict)
            ],
            decisions=[
                Decision(
                    decision_type=str(item.get("decision_type", "")),
                    chosen=str(item.get("chosen", "")),
                    alternatives=[
                        str(option)
                        for option in item.get("alternatives", [])
                        if isinstance(option, str)
                    ],
                    rationale=str(item.get("rationale", "")),
                    confidence=float(item.get("confidence", 1.0)),
                    timestamp=float(item.get("timestamp", 0.0)),
                    ltm_id=str(item.get("ltm_id", "")),
                )
                for item in data.get("decisions", [])
                if isinstance(item, dict)
            ],
            artifacts=[
                Artifact(
                    artifact_type=str(item.get("artifact_type", "")),
                    path=str(item.get("path", "")),
                    description=str(item.get("description", "")),
                    metadata=(
                        dict(item.get("metadata", {}))
                        if isinstance(item.get("metadata"), dict)
                        else {}
                    ),
                    timestamp=float(item.get("timestamp", 0.0)),
                )
                for item in data.get("artifacts", [])
                if isinstance(item, dict)
            ],
            created_at=float(data.get("created_at", __import__("time").time())),
            updated_at=float(data.get("updated_at", __import__("time").time())),
        )

    def get_context_prompt(self) -> str:
        """获取用于系统提示词的记忆描述。"""
        parts: list[str] = []

        if self.findings:
            parts.append(f"**关键发现**（{len(self.findings)} 项）：")
            for f in self.findings[:5]:  # 最多显示 5 项
                parts.append(f"- {f.category}: {f.summary}")

        if self.statistics:
            parts.append(f"**统计结果**（{len(self.statistics)} 项）：")
            for s in self.statistics[:5]:  # 最多显示 5 项
                sig = "显著" if s.significant else "不显著"
                nums: list[str] = []
                if s.test_statistic is not None:
                    nums.append(f"统计量={s.test_statistic:.4f}")
                if s.p_value is not None:
                    nums.append(f"p={s.p_value:.4f}")
                if s.effect_size is not None:
                    label = s.effect_type or "效应量"
                    nums.append(f"{label}={s.effect_size:.4f}")
                num_str = f"（{'，'.join(nums)}）" if nums else ""
                parts.append(f"- {s.test_name}: {sig}{num_str}")

        if self.decisions:
            parts.append(f"**方法决策**（{len(self.decisions)} 项）：")
            for d in self.decisions[:3]:  # 最多显示 3 项
                parts.append(f"- {d.decision_type}: 选择 {d.chosen}")

        if self.artifacts:
            parts.append(f"**产出文件**（{len(self.artifacts)} 个）")

        if not parts:
            return f"暂无分析记录（数据集: {self.dataset_name}）"

        return "\n".join(parts)


# ---- 会话记忆注册表 ----

_analysis_memories: dict[str, AnalysisMemory] = {}


def save_analysis_memory(memory: AnalysisMemory) -> None:
    """将 AnalysisMemory 持久化到磁盘。"""
    path = _analysis_memory_path(memory.session_id, memory.dataset_name)
    path.write_text(
        json.dumps(memory.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_analysis_memory(session_id: str, dataset_name: str) -> AnalysisMemory | None:
    """从磁盘加载 AnalysisMemory。"""
    path = _analysis_memory_path(session_id, dataset_name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("读取 AnalysisMemory 失败: session=%s dataset=%s", session_id, dataset_name)
        return None
    if not isinstance(payload, dict):
        return None
    memory = AnalysisMemory.from_dict(payload)
    if not memory.session_id:
        memory.session_id = session_id
    if not memory.dataset_name:
        memory.dataset_name = dataset_name
    return memory


def get_analysis_memory(session_id: str, dataset_name: str) -> AnalysisMemory:
    """获取或创建分析记忆。"""
    key = f"{session_id}:{dataset_name}"
    if key not in _analysis_memories:
        loaded = load_analysis_memory(session_id, dataset_name)
        _analysis_memories[key] = loaded or AnalysisMemory(
            session_id=session_id,
            dataset_name=dataset_name,
        )
    return _analysis_memories[key]


def remove_analysis_memory(session_id: str, dataset_name: str) -> None:
    """移除分析记忆。"""
    key = f"{session_id}:{dataset_name}"
    _analysis_memories.pop(key, None)
    path = _analysis_memory_path(session_id, dataset_name)
    if path.exists():
        path.unlink()


def list_session_analysis_memories(session_id: str) -> list[AnalysisMemory]:
    """列出会话的所有分析记忆（非空的）。"""
    memory_dir = _analysis_memory_dir(session_id)
    for path in sorted(memory_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取 AnalysisMemory 文件失败: %s", path)
            continue
        if not isinstance(payload, dict):
            continue
        dataset_name = str(payload.get("dataset_name", "")).strip()
        if not dataset_name:
            continue
        key = f"{session_id}:{dataset_name}"
        if key not in _analysis_memories:
            _analysis_memories[key] = AnalysisMemory.from_dict(payload)

    result: list[AnalysisMemory] = []
    prefix = f"{session_id}:"
    for key, mem in _analysis_memories.items():
        if key.startswith(prefix) and (mem.findings or mem.statistics or mem.decisions):
            result.append(mem)
    return result


def clear_session_analysis_memories(session_id: str) -> None:
    """清除会话的所有分析记忆。"""
    clear_session_analysis_memory_cache(session_id)
    memory_dir = settings.sessions_dir / session_id / "analysis_memories"
    if memory_dir.exists():
        for path in memory_dir.glob("*.json"):
            path.unlink()
        memory_dir.rmdir()


def clear_session_analysis_memory_cache(session_id: str) -> None:
    """仅清除会话的 AnalysisMemory 内存缓存。"""
    keys_to_remove = [k for k in _analysis_memories if k.startswith(f"{session_id}:")]
    for key in keys_to_remove:
        _analysis_memories.pop(key, None)
