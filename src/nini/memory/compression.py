"""会话压缩服务。

将长会话前半段历史归档到磁盘，并写入压缩摘要供后续上下文注入。
支持两种摘要模式：
- 轻量摘要（默认）：纯文本提取，不调用 LLM
- LLM 摘要：调用大模型生成 ≤500 字中文摘要，保留关键上下文
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.config import settings

logger = logging.getLogger(__name__)

_LLM_SUMMARY_PROMPT = (
    "你是一位专业的科研助手。请将以下对话历史压缩为一段简洁的中文摘要，"
    "保留关键信息（用户需求、分析方法、数据集、关键结论、待解决问题），"
    "摘要不超过 500 字。只输出摘要内容，不要添加额外说明。\n\n"
    "对话历史：\n{conversation}"
)


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _trim_text(value: Any, *, max_len: int = 180) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _summarize_messages(messages: list[dict[str, Any]], *, max_items: int = 20) -> str:
    """生成轻量摘要，避免再引入一次模型调用。"""
    lines: list[str] = []
    for msg in messages[:max_items]:
        role = str(msg.get("role", "")).strip() or "unknown"
        if role == "tool":
            tool_id = _trim_text(msg.get("tool_call_id", ""), max_len=32)
            content = _trim_text(msg.get("content", ""), max_len=140)
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
        )
        summary = response.text.strip()
        if summary:
            # 确保不超过 500 字
            if len(summary) > 500:
                summary = summary[:500] + "..."
            logger.info("LLM 对话摘要生成成功 (%d 字)", len(summary))
            return summary
    except Exception:
        logger.warning("LLM 对话摘要生成失败，回退到轻量摘要", exc_info=True)
    return None


def _archive_messages(session_id: str, messages: list[dict[str, Any]]) -> Path:
    archive_dir = settings.sessions_dir / session_id / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"compressed_{_now_ts()}.json"
    archive_path.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return archive_path


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
    archive_count = max(min_messages, int(total * ratio))
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

    summary = _summarize_messages(archived)
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
    archive_count = max(min_messages, int(total * ratio))
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

    archive_path = _archive_messages(session.id, archived)

    session.messages = remaining
    session._rewrite_conversation_memory()
    session.set_compressed_context(summary)

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


# ---- 结构化记忆压缩 ----

from dataclasses import dataclass, field
from typing import Any


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

    def add_statistic(self, statistic: StatisticResult) -> None:
        """添加统计结果。"""
        self.statistics.append(statistic)
        self.updated_at = __import__("time").time()

    def add_decision(self, decision: Decision) -> None:
        """添加决策记录。"""
        self.decisions.append(decision)
        self.updated_at = __import__("time").time()

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

    def get_context_prompt(self) -> str:
        """获取用于系统提示词的记忆描述。"""
        parts: list[str] = []

        if self.findings:
            parts.append(f"**关键发现**（{len(self.findings)} 项）：")
            for f in self.findings[:5]:  # 最多显示 5 项
                parts.append(f"- {f.category}: {f.summary}")

        if self.statistics:
            parts.append(f"**统计结果**（{len(self.statistics)} 项）：")
            for s in self.statistics[:3]:  # 最多显示 3 项
                sig = "显著" if s.significant else "不显著"
                parts.append(f"- {s.test_name}: {sig}")

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


def get_analysis_memory(session_id: str, dataset_name: str) -> AnalysisMemory:
    """获取或创建分析记忆。"""
    key = f"{session_id}:{dataset_name}"
    if key not in _analysis_memories:
        _analysis_memories[key] = AnalysisMemory(
            session_id=session_id,
            dataset_name=dataset_name,
        )
    return _analysis_memories[key]


def remove_analysis_memory(session_id: str, dataset_name: str) -> None:
    """移除分析记忆。"""
    key = f"{session_id}:{dataset_name}"
    _analysis_memories.pop(key, None)


def clear_session_analysis_memories(session_id: str) -> None:
    """清除会话的所有分析记忆。"""
    keys_to_remove = [k for k in _analysis_memories if k.startswith(f"{session_id}:")]
    for key in keys_to_remove:
        _analysis_memories.pop(key, None)
