"""长期记忆管理 API 端点（基于 SQLite MemoryStore）。

提供长期记忆的查询、管理和统计接口。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query

from nini.memory.memory_store import MemoryStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/memory")


def _get_store() -> MemoryStore:
    """获取全局 MemoryStore 实例（懒加载，线程安全）。"""
    from nini.memory.manager import get_memory_manager

    mm = get_memory_manager()
    if mm is not None:
        # 优先从 MemoryManager 获取已初始化的 store
        for provider in getattr(mm, "_providers", []):
            store = getattr(provider, "_store", None)
            if store is not None:
                return cast(MemoryStore, store)

    # fallback：直接构造（API 端点独立调用时）
    from nini.config import settings

    db_path = settings.sessions_dir.parent / "nini_memory.db"
    return MemoryStore(db_path)


@router.get("/long-term")
async def list_memories(
    query: str | None = None,
    session_id: str | None = None,
    dataset_name: str | None = None,
    memory_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """获取长期记忆列表。

    Args:
        query: 搜索查询（可选）
        session_id: 按会话 ID 过滤（可选）
        dataset_name: 按数据集名称过滤（可选）
        memory_type: 按记忆类型过滤（可选）
        limit: 返回数量限制

    Returns:
        记忆列表
    """
    try:
        store = _get_store()

        if dataset_name:
            # 使用 sci_metadata 精确过滤
            rows = store.filter_by_sci(dataset_name=dataset_name)
        elif query:
            rows = store.search_fts(query, top_k=limit)
        else:
            # 无过滤条件时返回最近记忆（按 importance 降序）
            rows = store.search_fts("", top_k=limit)

        # 内存级二次过滤
        if session_id:
            rows = [r for r in rows if r.get("source_session_id") == session_id]
        if memory_type:
            rows = [r for r in rows if r.get("memory_type") == memory_type]
        rows = rows[:limit]

        # 统一输出格式（与旧 LongTermMemoryEntry.to_dict() 保持字段语义兼容）
        memories = []
        for r in rows:
            meta = r.get("sci_metadata") or {}
            memories.append({
                "id": r.get("id"),
                "memory_type": r.get("memory_type"),
                "content": r.get("content"),
                "summary": r.get("summary"),
                "source_session_id": r.get("source_session_id"),
                "source_dataset": meta.get("dataset_name"),
                "analysis_type": meta.get("analysis_type"),
                "confidence": r.get("trust_score"),
                "importance_score": r.get("importance"),
                "tags": r.get("tags") or [],
                "metadata": meta,
                "created_at": r.get("created_at"),
                "last_accessed_at": r.get("last_accessed_at"),
                "access_count": r.get("access_count", 0),
            })
        return {"memories": memories, "total": len(memories)}

    except Exception as e:
        logger.error("获取长期记忆列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取记忆列表失败: {e}")


@router.post("/long-term/extract")
async def extract_memories(
    content: str,
    session_id: str,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    """从分析内容中提取并保存长期记忆（LLM 辅助提取）。

    Args:
        content: 分析内容
        session_id: 会话 ID
        dataset_name: 数据集名称

    Returns:
        提取并写入的记忆条数
    """
    try:
        from nini.agent.model_resolver import model_resolver

        _PROMPT = (
            "请从以下分析对话中提取关键发现，以 JSON 格式输出：\n"
            '{{"memories": [{{"memory_type": "finding", "summary": "...", '
            '"content": "...", "importance": 0.7, "tags": []}}]}}\n\n'
            "分析内容：\n{content}"
        )
        prompt = _PROMPT.format(content=content[:4000])
        response = await model_resolver.chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            purpose="chat",
        )
        assert response is not None
        text = response.text.strip()

        import json

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(text)
        memories_raw = parsed.get("memories", [])

        store = _get_store()
        sci: dict[str, Any] = {}
        if dataset_name:
            sci["dataset_name"] = dataset_name

        count = 0
        for m in memories_raw:
            importance = float(m.get("importance", 0.7))
            if isinstance(importance, (int, float)) and importance > 1:
                importance = importance / 10.0
            store.upsert_fact(
                content=str(m.get("content") or m.get("summary") or ""),
                memory_type=str(m.get("memory_type", "insight")),
                summary=str(m.get("summary", ""))[:200],
                tags=list(m.get("tags") or []),
                importance=min(1.0, max(0.0, importance)),
                source_session_id=session_id,
                sci_metadata=sci,
            )
            count += 1

        return {"success": True, "extracted_count": count}

    except Exception as e:
        logger.error("提取记忆失败: %s", e)
        raise HTTPException(status_code=500, detail=f"提取记忆失败: {e}")


@router.delete("/long-term/{memory_id}")
async def delete_memory(memory_id: str) -> dict[str, Any]:
    """删除长期记忆（按 ID 直接删除 SQLite 行）。

    Args:
        memory_id: 记忆 ID

    Returns:
        删除结果
    """
    try:
        store = _get_store()
        # MemoryStore 暂无独立 delete 方法，通过 sqlite3 直接删除
        conn = store._conn  # type: ignore[attr-defined]
        cursor = conn.execute("SELECT id FROM facts WHERE id = ?", (memory_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="记忆不存在")
        with conn:
            conn.execute("DELETE FROM facts WHERE id = ?", (memory_id,))
        return {"success": True, "message": "记忆已删除"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除记忆失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除记忆失败: {e}")


@router.get("/long-term/stats")
async def get_memory_stats() -> dict[str, Any]:
    """获取长期记忆统计信息。

    Returns:
        统计信息（总条数、类型分布、最近更新时间）
    """
    try:
        store = _get_store()
        conn = store._conn  # type: ignore[attr-defined]

        total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        type_rows = conn.execute(
            "SELECT memory_type, COUNT(*) as cnt FROM facts GROUP BY memory_type"
        ).fetchall()
        by_type = {row[0]: row[1] for row in type_rows}
        last_updated = conn.execute("SELECT MAX(updated_at) FROM facts").fetchone()[0]

        return {
            "total_memories": total,
            "type_distribution": by_type,
            "vector_store_available": False,
            "last_updated_ts": last_updated,
            "storage": "sqlite",
        }

    except Exception as e:
        logger.error("获取记忆统计失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取统计失败: {e}")


@router.post("/long-term/initialize")
async def init_long_term_memory() -> dict[str, Any]:
    """初始化长期记忆系统（MemoryStore 为惰性初始化，此接口作为探针使用）。

    Returns:
        初始化结果
    """
    try:
        store = _get_store()
        total = store._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]  # type: ignore[attr-defined]
        return {
            "success": True,
            "message": "长期记忆系统就绪",
            "total_memories": total,
        }

    except Exception as e:
        logger.error("初始化长期记忆失败: %s", e)
        raise HTTPException(status_code=500, detail=f"初始化失败: {e}")
