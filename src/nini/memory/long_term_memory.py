"""长期记忆持久化模块。

提供跨会话的长期记忆存储和检索：
1. LLM 摘要压缩关键发现
2. 写入向量数据库
3. 跨会话检索历史分析结论
4. 集成到知识检索流程
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LongTermMemoryEntry:
    """长期记忆条目。

    存储从分析会话中提取的关键发现，支持跨会话检索。
    """

    id: str
    memory_type: str  # finding, statistic, decision, insight
    content: str  # 记忆内容
    summary: str  # 简短摘要
    source_session_id: str
    source_dataset: str | None = None
    analysis_type: str | None = None  # 分析类型 (t_test, correlation, etc.)
    confidence: float = 1.0
    importance_score: float = 0.5  # 重要性评分 (0-1)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "summary": self.summary,
            "source_session_id": self.source_session_id,
            "source_dataset": self.source_dataset,
            "analysis_type": self.analysis_type,
            "confidence": self.confidence,
            "importance_score": self.importance_score,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LongTermMemoryEntry:
        """从字典创建。"""
        return cls(
            id=str(data.get("id", uuid.uuid4())),
            memory_type=str(data.get("memory_type", "insight")),
            content=str(data.get("content", "")),
            summary=str(data.get("summary", "")),
            source_session_id=str(data.get("source_session_id", "")),
            source_dataset=data.get("source_dataset"),
            analysis_type=data.get("analysis_type"),
            confidence=float(data.get("confidence", 1.0)),
            importance_score=float(data.get("importance_score", 0.5)),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            last_accessed_at=str(data.get("last_accessed_at", datetime.now(timezone.utc).isoformat())),
            access_count=int(data.get("access_count", 0)),
        )


class LongTermMemoryStore:
    """长期记忆存储。

    管理长期记忆的持久化和向量索引。
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or settings.sessions_dir / "../long_term_memory"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, LongTermMemoryEntry] = {}
        self._vector_store: Any = None
        self._load_entries()

    def _load_entries(self) -> None:
        """加载所有记忆条目。"""
        entries_file = self._storage_dir / "entries.jsonl"
        if not entries_file.exists():
            return

        for line in entries_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entry = LongTermMemoryEntry.from_dict(data)
                self._entries[entry.id] = entry
            except Exception as e:
                logger.warning(f"加载记忆条目失败: {e}")

        logger.info(f"已加载 {len(self._entries)} 条长期记忆")

    def _save_entries(self) -> None:
        """保存所有记忆条目。"""
        entries_file = self._storage_dir / "entries.jsonl"
        lines = []
        for entry in self._entries.values():
            lines.append(json.dumps(entry.to_dict(), ensure_ascii=False))
        entries_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    async def initialize(self) -> None:
        """初始化向量存储。"""
        try:
            from nini.knowledge.vector_store import VectorKnowledgeStore

            vector_dir = self._storage_dir / "vector_index"
            self._vector_store = VectorKnowledgeStore(
                knowledge_dir=self._storage_dir / "documents",
                storage_dir=vector_dir,
            )
            await self._vector_store.initialize()
            logger.info("长期记忆向量存储初始化完成")
        except Exception as e:
            logger.warning(f"长期记忆向量存储初始化失败: {e}")

    def add_memory(
        self,
        memory_type: str,
        content: str,
        summary: str,
        source_session_id: str,
        source_dataset: str | None = None,
        analysis_type: str | None = None,
        confidence: float = 1.0,
        importance_score: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LongTermMemoryEntry:
        """添加记忆。

        Args:
            memory_type: 记忆类型
            content: 记忆内容
            summary: 简短摘要
            source_session_id: 源会话 ID
            source_dataset: 源数据集名称
            analysis_type: 分析类型
            confidence: 置信度
            importance_score: 重要性评分
            tags: 标签
            metadata: 元数据

        Returns:
            创建的记忆条目
        """
        entry = LongTermMemoryEntry(
            id=str(uuid.uuid4()),
            memory_type=memory_type,
            content=content,
            summary=summary,
            source_session_id=source_session_id,
            source_dataset=source_dataset,
            analysis_type=analysis_type,
            confidence=confidence,
            importance_score=importance_score,
            tags=tags or [],
            metadata=metadata or {},
        )

        self._entries[entry.id] = entry
        self._save_entries()

        # 添加到向量索引
        if self._vector_store and self._vector_store._initialized:
            try:
                import asyncio
                asyncio.create_task(
                    self._vector_store.add_document(
                        doc_id=entry.id,
                        content=f"{entry.summary}\n{entry.content}",
                        metadata={
                            "memory_type": entry.memory_type,
                            "analysis_type": entry.analysis_type,
                            "tags": entry.tags,
                        },
                    )
                )
            except Exception as e:
                logger.warning(f"添加记忆到向量索引失败: {e}")

        logger.info(f"添加长期记忆: {entry.memory_type} - {entry.summary[:50]}...")
        return entry

    @staticmethod
    def _compute_effective_score(
        entry: "LongTermMemoryEntry",
        context: dict[str, Any] | None = None,
    ) -> float:
        """计算记忆条目的有效分值。

        综合考虑重要性评分、时间衰减和情境匹配权重：
        - 时间衰减：R(t) = importance × e^(-λ × days)，λ=0.01
        - 高频访问（access_count > 5）的条目衰减速率减半
        - 情境命中当前数据集（×1.5）或分析类型（×1.3）时给予加成
        """
        # 时间衰减
        try:
            created = datetime.fromisoformat(entry.created_at)
            days_elapsed = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400)
        except Exception:
            days_elapsed = 0.0

        # 高频访问条目衰减更慢
        decay_lambda = 0.005 if entry.access_count > 5 else 0.01
        time_decay = math.exp(-decay_lambda * days_elapsed)
        score = entry.importance_score * time_decay

        # 情境权重加成
        if context:
            dataset_name = context.get("dataset_name") or context.get("dataset")
            analysis_type = context.get("analysis_type")
            if dataset_name and entry.source_dataset == dataset_name:
                score *= 1.5
            if analysis_type and entry.analysis_type == analysis_type:
                score *= 1.3

        return score

    async def search(
        self,
        query: str,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        min_importance: float = 0.0,
        context: dict[str, Any] | None = None,
    ) -> list[LongTermMemoryEntry]:
        """搜索记忆。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            memory_types: 记忆类型过滤
            min_importance: 最小重要性评分（经衰减后的有效分值）
            context: 情境信息，支持 dataset_name/analysis_type 键用于情境加权

        Returns:
            匹配的记忆条目列表
        """
        results: list[LongTermMemoryEntry] = []

        # 向量搜索
        if self._vector_store and self._vector_store._initialized:
            try:
                vector_results = await self._vector_store.search(query, top_k=top_k * 2)
                for doc_id, score in vector_results:
                    if doc_id in self._entries:
                        entry = self._entries[doc_id]
                        entry.access_count += 1
                        entry.last_accessed_at = datetime.now(timezone.utc).isoformat()
                        results.append(entry)
            except Exception as e:
                logger.warning(f"向量搜索失败: {e}")

        # 如果没有向量结果，使用关键词匹配
        if not results:
            query_lower = query.lower()
            for entry in self._entries.values():
                if query_lower in entry.content.lower() or query_lower in entry.summary.lower():
                    entry.access_count += 1
                    entry.last_accessed_at = datetime.now(timezone.utc).isoformat()
                    results.append(entry)

        # 类型过滤
        if memory_types:
            results = [r for r in results if r.memory_type in memory_types]

        # 按有效分值（含衰减与情境权重）排序并过滤低分条目
        results.sort(
            key=lambda x: self._compute_effective_score(x, context),
            reverse=True,
        )
        if min_importance > 0:
            results = [r for r in results if self._compute_effective_score(r, context) >= min_importance]

        return results[:top_k]

    def get_memories_by_session(self, session_id: str) -> list[LongTermMemoryEntry]:
        """获取会话的所有记忆。

        Args:
            session_id: 会话 ID

        Returns:
            记忆条目列表
        """
        return [
            entry for entry in self._entries.values()
            if entry.source_session_id == session_id
        ]

    def get_memories_by_dataset(self, dataset_name: str) -> list[LongTermMemoryEntry]:
        """获取数据集的所有记忆。

        Args:
            dataset_name: 数据集名称

        Returns:
            记忆条目列表
        """
        return [
            entry for entry in self._entries.values()
            if entry.source_dataset == dataset_name
        ]

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆。

        Args:
            memory_id: 记忆 ID

        Returns:
            是否成功
        """
        if memory_id not in self._entries:
            return False

        del self._entries[memory_id]
        self._save_entries()

        # 从向量索引中移除
        if self._vector_store and self._vector_store._initialized:
            try:
                import asyncio
                asyncio.create_task(self._vector_store.remove_document(memory_id))
            except Exception as e:
                logger.warning(f"从向量索引移除记忆失败: {e}")

        return True

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        type_counts: dict[str, int] = {}
        for entry in self._entries.values():
            type_counts[entry.memory_type] = type_counts.get(entry.memory_type, 0) + 1

        return {
            "total_memories": len(self._entries),
            "type_distribution": type_counts,
            "vector_store_available": self._vector_store is not None and self._vector_store._initialized,
        }


# 全局长期记忆存储实例
_long_term_memory_store: LongTermMemoryStore | None = None


def get_long_term_memory_store() -> LongTermMemoryStore:
    """获取全局长期记忆存储实例。"""
    global _long_term_memory_store
    if _long_term_memory_store is None:
        _long_term_memory_store = LongTermMemoryStore()
    return _long_term_memory_store


async def initialize_long_term_memory() -> None:
    """初始化长期记忆系统。"""
    store = get_long_term_memory_store()
    await store.initialize()


# ---- LLM 摘要和记忆提取 ----

_MEMORY_EXTRACTION_PROMPT = """请从以下分析对话中提取关键发现，作为长期记忆存储。

对于每个发现，请提供：
1. 发现类型 (finding, statistic, decision, insight)
2. 简短摘要（不超过 100 字）
3. 详细内容（包含具体数值和结论）
4. 重要性评分（1-10）
5. 相关标签

分析内容：
{content}

请以 JSON 格式输出：
{{
  "memories": [
    {{
      "memory_type": "finding",
      "summary": "...",
      "content": "...",
      "importance": 8,
      "tags": ["标签1", "标签2"]
    }}
  ]
}}"""


async def extract_memories_with_llm(
    content: str,
    session_id: str,
    dataset_name: str | None = None,
) -> list[LongTermMemoryEntry]:
    """使用 LLM 从分析内容中提取记忆。

    Args:
        content: 分析内容
        session_id: 会话 ID
        dataset_name: 数据集名称

    Returns:
        提取的记忆条目列表
    """
    try:
        from nini.agent.model_resolver import model_resolver

        prompt = _MEMORY_EXTRACTION_PROMPT.format(content=content[:4000])
        response = await model_resolver.chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            purpose="chat",
        )

        # 解析 JSON 响应
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        memories_data = data.get("memories", [])

        store = get_long_term_memory_store()
        entries: list[LongTermMemoryEntry] = []

        for mem_data in memories_data:
            entry = store.add_memory(
                memory_type=mem_data.get("memory_type", "insight"),
                summary=mem_data.get("summary", ""),
                content=mem_data.get("content", ""),
                source_session_id=session_id,
                source_dataset=dataset_name,
                importance_score=mem_data.get("importance", 5) / 10.0,
                tags=mem_data.get("tags", []),
            )
            entries.append(entry)

        logger.info(f"从 LLM 提取了 {len(entries)} 条记忆")
        return entries

    except Exception as e:
        logger.warning(f"LLM 记忆提取失败: {e}")
        return []


# ---- 知识检索集成 ----

async def search_long_term_memories(
    query: str,
    top_k: int = 3,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """搜索长期记忆，用于知识检索集成。

    Args:
        query: 查询文本
        top_k: 返回结果数量
        context: 情境信息（当前会话、数据集、分析类型等），用于情境感知重排序

    Returns:
        格式化的记忆结果列表
    """
    store = get_long_term_memory_store()
    entries = await store.search(query, top_k=top_k, min_importance=0.3, context=context)

    results = []
    for entry in entries:
        results.append({
            "type": "long_term_memory",
            "memory_type": entry.memory_type,
            "summary": entry.summary,
            "content": entry.content,
            "source_session": entry.source_session_id[:8] + "..." if len(entry.source_session_id) > 8 else entry.source_session_id,
            "source_dataset": entry.source_dataset,
            "confidence": entry.confidence,
            "tags": entry.tags,
            "created_at": entry.created_at,
        })

    return results


async def consolidate_session_memories(session_id: str) -> int:
    """将会话内高置信度分析记忆沉淀为跨会话长期记忆。

    遍历会话的所有 AnalysisMemory，将 confidence >= 0.7 的
    Finding/Statistic/Decision 条目写入 LongTermMemoryStore。

    Args:
        session_id: 会话 ID

    Returns:
        写入的记忆条数
    """
    try:
        from nini.memory.compression import list_session_analysis_memories

        memories = list_session_analysis_memories(session_id)
        if not memories:
            return 0

        store = get_long_term_memory_store()
        count = 0

        for memory in memories:
            # 沉淀高置信度 Finding
            for finding in memory.findings:
                if finding.confidence >= 0.7:
                    store.add_memory(
                        memory_type="finding",
                        content=finding.detail or finding.summary,
                        summary=finding.summary,
                        source_session_id=session_id,
                        source_dataset=memory.dataset_name,
                        importance_score=finding.confidence,
                        tags=[finding.category] if finding.category else [],
                    )
                    count += 1

            # 沉淀统计结果（显著性结果重要性更高）
            for stat in memory.statistics:
                importance = 0.8 if stat.significant else 0.6
                store.add_memory(
                    memory_type="statistic",
                    content=(
                        f"{stat.test_name}: "
                        f"统计量={stat.test_statistic}, p={stat.p_value}, "
                        f"效应量={stat.effect_size}, 显著={stat.significant}"
                    ),
                    summary=f"{stat.test_name} 结果({'显著' if stat.significant else '不显著'})",
                    source_session_id=session_id,
                    source_dataset=memory.dataset_name,
                    analysis_type=stat.test_name,
                    importance_score=importance,
                    tags=["statistic", stat.test_name],
                )
                count += 1

            # 沉淀高置信度方法决策
            for decision in memory.decisions:
                if decision.confidence >= 0.7:
                    store.add_memory(
                        memory_type="decision",
                        content=f"{decision.decision_type}: 选择 {decision.chosen}。理由：{decision.rationale}",
                        summary=f"{decision.decision_type} → {decision.chosen}",
                        source_session_id=session_id,
                        source_dataset=memory.dataset_name,
                        importance_score=decision.confidence * 0.8,
                        tags=["decision", decision.decision_type],
                    )
                    count += 1

        if count > 0:
            logger.info("会话 %s 记忆沉淀完成，写入 %d 条长期记忆", session_id, count)
        return count

    except Exception:
        logger.warning("会话记忆沉淀失败: session=%s", session_id, exc_info=True)
        return 0


def format_memories_for_context(memories: list[LongTermMemoryEntry]) -> str:
    """将记忆格式化为可注入的上下文。

    Args:
        memories: 记忆条目列表

    Returns:
        格式化的上下文文本
    """
    if not memories:
        return ""

    parts = ["## 历史分析记忆", ""]

    for i, mem in enumerate(memories, 1):
        parts.append(f"{i}. [{mem.memory_type.upper()}] {mem.summary}")
        if mem.content and mem.content != mem.summary:
            content_preview = mem.content[:200] + "..." if len(mem.content) > 200 else mem.content
            parts.append(f"   {content_preview}")
        if mem.tags:
            parts.append(f"   标签: {', '.join(mem.tags)}")
        parts.append("")

    return "\n".join(parts)
