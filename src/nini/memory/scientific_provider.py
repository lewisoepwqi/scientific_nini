"""ScientificMemoryProvider：nini 唯一内置记忆 Provider。"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any

from nini.memory.manager import build_memory_context_block
from nini.memory.memory_store import MemoryStore
from nini.memory.provider import MemoryProvider

logger = logging.getLogger(__name__)

# 统计数值检测正则（用于 sync_turn 和 on_pre_compress）
_STAT_PATTERNS = [
    re.compile(r"p\s*[=<>≤≥]\s*[\d.eE\-]+"),
    re.compile(r"Cohen['s]*\s*[dDgG]\s*[=≈]\s*[\d.]+", re.IGNORECASE),
    re.compile(r"效应量\s*[=≈：:]\s*[\d.]+"),
    re.compile(r"[tF]\s*\(\d+[,\s]*\d*\)\s*[=≈]\s*[\d.]+"),
]
_CONCLUSION_PATTERNS = [
    re.compile(r"结论[：:].{5,150}"),
    re.compile(r"发现[：:].{5,150}"),
]


class ScientificMemoryProvider(MemoryProvider):
    """nini 内置记忆 Provider，管理跨会话科研记忆与研究画像。"""

    def __init__(
        self,
        db_path: Path | None = None,
        profile_id: str = "default",
    ) -> None:
        if db_path is None:
            from nini.config import settings

            db_path = settings.sessions_dir.parent / "nini_memory.db"
        self._db_path = Path(db_path)
        self._profile_id = profile_id
        self._store: MemoryStore | None = None
        self._session_id: str = ""

    @property
    def name(self) -> str:
        return "builtin"

    async def initialize(self, session_id: str, **kwargs: Any) -> None:
        """打开 SQLite，执行旧数据迁移（幂等）。"""
        self._session_id = session_id
        self._store = MemoryStore(self._db_path)
        self._migrate_legacy()
        logger.info("ScientificMemoryProvider 初始化完成: session=%s", session_id[:8])

    def _migrate_legacy(self) -> None:
        """迁移旧格式数据（幂等，静默跳过不存在的文件）。"""
        assert self._store is not None
        ltm_dir = self._db_path.parent / "long_term_memory"
        jsonl_path = ltm_dir / "entries.jsonl"
        if jsonl_path.exists():
            count = self._store.migrate_from_jsonl(jsonl_path)
            if count:
                logger.info("JSONL 迁移完成：写入 %d 条记忆", count)
        profiles_dir = self._db_path.parent / "profiles"
        if profiles_dir.exists():
            for json_path in profiles_dir.glob("*.json"):
                md_path = profiles_dir / f"{json_path.stem}_profile.md"
                self._store.migrate_profile_json(json_path, md_path if md_path.exists() else None)

    def system_prompt_block(self) -> str:
        """返回研究画像的 system prompt 快照（会话开始时调用一次）。

        包含两部分：
        1. 研究画像摘要（若有）
        2. 记忆工具说明（nini_memory_find / nini_memory_save）
        """
        parts: list[str] = []

        # 研究画像部分
        if self._store is not None:
            profile = self._store.get_profile(self._profile_id)
            if profile:
                narrative = (profile.get("narrative_md") or "").strip()
                if narrative:
                    parts.append(f"## 研究画像\n\n{narrative}")
                else:
                    data = profile.get("data_json") or {}
                    profile_parts: list[str] = []
                    domain = data.get("domain", "")
                    if domain and domain != "general":
                        profile_parts.append(f"研究领域：{domain}")
                    if data.get("significance_level"):
                        profile_parts.append(f"显著性水平：α={data['significance_level']}")
                    if data.get("journal_style"):
                        profile_parts.append(f"期刊风格：{data['journal_style']}")
                    if profile_parts:
                        parts.append("## 研究画像\n\n" + "\n".join(f"- {p}" for p in profile_parts))

        # 记忆工具说明
        parts.append(
            "## 记忆系统\n\n"
            "你可以主动使用以下工具访问和保存跨会话的科研记忆：\n"
            "- `nini_memory_find`：检索历史分析结果（支持关键词 + p 值/数据集过滤）\n"
            "- `nini_memory_save`：保存重要发现、统计结论或分析决策"
        )

        return "\n\n".join(parts)

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """三段式检索：FTS5 召回 → 时间衰减+情境加权排序 → fencing 包裹。

        返回值包含 <memory-context> 标签，供调用方直接追加到 prompt。
        """
        if self._store is None or not query.strip():
            return ""
        try:
            candidates = self._store.search_fts(query, top_k=15)
            if not candidates:
                return ""
            now = time.time()
            scored: list[tuple[float, dict[str, Any]]] = []
            for fact in candidates:
                importance = float(fact.get("importance", 0.5))
                access_count = int(fact.get("access_count") or 0)
                created_at = float(fact.get("created_at") or now)
                days = max(0.0, (now - created_at) / 86400)
                # 高频访问记忆衰减更慢（更"经典"）
                decay_lambda = 0.005 if access_count > 5 else 0.01
                score = importance * math.exp(-decay_lambda * days)
                scored.append((score, fact))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = [f for _, f in scored[:5]]
            lines: list[str] = []
            for fact in top:
                memory_type = fact.get("memory_type", "")
                summary = fact.get("summary") or fact.get("content", "")[:80]
                sci = fact.get("sci_metadata") or {}
                dataset = sci.get("dataset_name", "") if isinstance(sci, dict) else ""
                line = f"[{memory_type.upper()}] {summary}"
                if dataset:
                    line += f"（来源：{dataset}）"
                lines.append(line)
            raw = "\n".join(lines)
            return build_memory_context_block(raw)
        except Exception as exc:
            logger.warning("ScientificMemoryProvider.prefetch 失败: %s", exc)
            return ""

    async def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
    ) -> None:
        """轻量提取：扫描 assistant 回复，写入统计数值和结论（importance ≥ 0.4）。"""
        if self._store is None:
            return
        try:
            items = self._extract_from_text(assistant_content, session_id or self._session_id)
            for item in items:
                self._store.upsert_fact(**item)
        except Exception as exc:
            logger.warning("ScientificMemoryProvider.sync_turn 失败: %s", exc)

    def _extract_from_text(self, text: str, session_id: str) -> list[dict[str, Any]]:
        """从文本中提取统计数值和结论，返回 upsert_fact kwargs 列表。

        importance < 0.4 的片段不写入（噪声过滤）。
        """
        results: list[dict[str, Any]] = []
        for pattern in _STAT_PATTERNS:
            for match in pattern.finditer(text):
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 60)
                snippet = text[start:end].strip()
                results.append(
                    {
                        "content": snippet,
                        "memory_type": "statistic",
                        "summary": match.group(0)[:80],
                        "importance": 0.7,
                        "source_session_id": session_id,
                    }
                )
        for pattern in _CONCLUSION_PATTERNS:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "content": match.group(0),
                        "memory_type": "finding",
                        "summary": match.group(0)[:80],
                        "importance": 0.65,
                        "source_session_id": session_id,
                    }
                )
        return results

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """重度沉淀：将本会话的 AnalysisMemory 写入 facts 表。

        通过 self._session_id 调用 list_session_analysis_memories()，
        不依赖 messages 参数读取 AnalysisMemory。
        """
        if self._store is None:
            return
        try:
            from nini.memory.compression import list_session_analysis_memories

            sid = self._session_id
            memories = list_session_analysis_memories(sid)
            count = 0
            for memory in memories:
                dataset = memory.dataset_name
                for finding in memory.findings:
                    if finding.confidence < 0.7:
                        continue
                    self._store.upsert_fact(
                        content=finding.summary,
                        memory_type="finding",
                        summary=finding.detail or "",
                        tags=[finding.category] if finding.category else [],
                        importance=finding.confidence,
                        source_session_id=sid,
                        sci_metadata={"dataset_name": dataset},
                    )
                    count += 1
                for stat in memory.statistics:
                    importance = (
                        0.8
                        if stat.significant is True
                        else 0.6 if stat.significant is False else 0.45
                    )
                    self._store.upsert_fact(
                        content=(
                            f"{stat.test_name}: 统计量={stat.test_statistic}, "
                            f"p={stat.p_value}, 效应量={stat.effect_size}"
                        ),
                        memory_type="statistic",
                        summary=f"{stat.test_name} 结果",
                        importance=importance,
                        source_session_id=sid,
                        sci_metadata={
                            "dataset_name": dataset,
                            "test_name": stat.test_name,
                            "test_statistic": stat.test_statistic,
                            "p_value": stat.p_value,
                            "effect_size": stat.effect_size,
                            "effect_type": stat.effect_type or None,
                            "significant": stat.significant,
                            "analysis_type": stat.test_name,
                        },
                    )
                    count += 1
                for decision in memory.decisions:
                    if decision.confidence < 0.7:
                        continue
                    self._store.upsert_fact(
                        content=(
                            f"{decision.decision_type}: 选择 {decision.chosen}。"
                            f"理由：{decision.rationale}"
                        ),
                        memory_type="decision",
                        summary=f"{decision.decision_type} → {decision.chosen}",
                        importance=decision.confidence * 0.8,
                        source_session_id=sid,
                        sci_metadata={"dataset_name": dataset},
                    )
                    count += 1
            if count:
                logger.info("on_session_end: 会话 %s 沉淀 %d 条记忆", sid[:8], count)
        except Exception as exc:
            logger.warning("ScientificMemoryProvider.on_session_end 失败: %s", exc)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """压缩前：提取 assistant 回复中含统计数值的行，追加保留提示到压缩 prompt。"""
        stat_lines: list[str] = []
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = str(msg.get("content") or "")
            for pattern in _STAT_PATTERNS:
                for match in pattern.finditer(content):
                    start = max(0, match.start() - 10)
                    end = min(len(content), match.end() + 60)
                    stat_lines.append(content[start:end].strip())
        if not stat_lines:
            return ""
        return "以下统计结果必须完整保留在摘要中：\n" + "\n".join(
            f"- {line}" for line in stat_lines[:10]
        )

    async def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        """路由工具调用到对应处理方法，返回 JSON 字符串。"""
        if self._store is None:
            return json.dumps({"success": False, "error": "记忆存储未初始化"}, ensure_ascii=False)
        if tool_name == "nini_memory_find":
            return await self._handle_find(args)
        if tool_name == "nini_memory_save":
            return await self._handle_save(args)
        return json.dumps({"success": False, "error": f"未知工具：{tool_name}"}, ensure_ascii=False)

    async def _handle_find(self, args: dict[str, Any]) -> str:
        """处理 nini_memory_find 工具调用。"""
        assert self._store is not None
        query = str(args.get("query") or "")
        top_k = int(args.get("top_k") or 5)
        dataset_name = args.get("dataset_name") or None
        max_p_value = args.get("max_p_value")

        if max_p_value is not None or dataset_name:
            candidates = self._store.filter_by_sci(
                dataset_name=dataset_name,
                max_p_value=float(max_p_value) if max_p_value is not None else None,
            )
            if query:
                q_lower = query.lower()
                candidates = [
                    r
                    for r in candidates
                    if q_lower in r.get("content", "").lower()
                    or q_lower in r.get("summary", "").lower()
                ]
            candidates = candidates[:top_k]
        else:
            candidates = self._store.search_fts(query, top_k=top_k)

        formatted = [
            {
                "memory_type": r.get("memory_type"),
                "summary": r.get("summary") or r.get("content", "")[:100],
                "content": r.get("content"),
                "dataset": (r.get("sci_metadata") or {}).get("dataset_name"),
            }
            for r in candidates
        ]
        return json.dumps({"success": True, "results": formatted}, ensure_ascii=False)

    async def _handle_save(self, args: dict[str, Any]) -> str:
        """处理 nini_memory_save 工具调用。"""
        assert self._store is not None
        content = str(args.get("content") or "").strip()
        if not content:
            return json.dumps({"success": False, "error": "content 不能为空"}, ensure_ascii=False)
        memory_type = str(args.get("memory_type") or "insight")
        importance = float(args.get("importance") or 0.7)
        fact_id = self._store.upsert_fact(
            content=content,
            memory_type=memory_type,
            importance=importance,
            source_session_id=self._session_id,
        )
        return json.dumps({"success": True, "id": fact_id}, ensure_ascii=False)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """返回暴露给 LLM 的工具 schema。"""
        return [
            {
                "name": "nini_memory_find",
                "description": (
                    "检索历史分析记忆。支持全文搜索和科研字段过滤（p_value、dataset_name 等）。"
                    "当需要引用之前分析的具体数值时使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "检索关键词"},
                        "top_k": {
                            "type": "integer",
                            "description": "最多返回条数（默认 5）",
                        },
                        "dataset_name": {
                            "type": "string",
                            "description": "限定数据集名称（可选）",
                        },
                        "max_p_value": {
                            "type": "number",
                            "description": "p 值上限过滤（可选，如 0.05）",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "nini_memory_save",
                "description": "主动保存一条分析发现、洞察或决策到长期记忆。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要保存的内容"},
                        "memory_type": {
                            "type": "string",
                            "enum": [
                                "finding",
                                "statistic",
                                "decision",
                                "insight",
                                "knowledge",
                            ],
                        },
                        "importance": {
                            "type": "number",
                            "description": "重要性 0~1（默认 0.7）",
                        },
                    },
                    "required": ["content"],
                },
            },
        ]

    async def shutdown(self) -> None:
        """关闭数据库连接。"""
        if self._store is not None:
            self._store.close()
            self._store = None
