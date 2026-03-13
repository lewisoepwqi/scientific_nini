"""长期记忆管理 API 端点。

提供长期记忆的查询、管理和统计接口。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from nini.memory.long_term_memory import (
    extract_memories_with_llm,
    get_long_term_memory_store,
    initialize_long_term_memory,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/memory")


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
        session_id: 按会话过滤
        dataset_name: 按数据集过滤
        memory_type: 按记忆类型过滤
        limit: 返回数量限制

    Returns:
        记忆列表
    """
    try:
        store = get_long_term_memory_store()

        if query:
            entries = await store.search(
                query,
                top_k=limit,
                memory_types=[memory_type] if memory_type else None,
            )
        elif session_id:
            entries = store.get_memories_by_session(session_id)
            if memory_type:
                entries = [e for e in entries if e.memory_type == memory_type]
            entries = entries[:limit]
        elif dataset_name:
            entries = store.get_memories_by_dataset(dataset_name)
            if memory_type:
                entries = [e for e in entries if e.memory_type == memory_type]
            entries = entries[:limit]
        else:
            # 返回最近的记忆
            all_entries = list(store._entries.values())
            if memory_type:
                all_entries = [e for e in all_entries if e.memory_type == memory_type]
            entries = sorted(all_entries, key=lambda x: x.created_at, reverse=True)[:limit]

        return {
            "memories": [e.to_dict() for e in entries],
            "total": len(entries),
        }

    except Exception as e:
        logger.error(f"获取长期记忆列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记忆列表失败: {e}")


@router.post("/long-term/extract")
async def extract_memories(
    content: str,
    session_id: str,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    """从分析内容中提取长期记忆。

    Args:
        content: 分析内容
        session_id: 会话 ID
        dataset_name: 数据集名称

    Returns:
        提取的记忆列表
    """
    try:
        entries = await extract_memories_with_llm(
            content=content,
            session_id=session_id,
            dataset_name=dataset_name,
        )

        return {
            "success": True,
            "extracted_count": len(entries),
            "memories": [e.to_dict() for e in entries],
        }

    except Exception as e:
        logger.error(f"提取记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"提取记忆失败: {e}")


@router.delete("/long-term/{memory_id}")
async def delete_memory(memory_id: str) -> dict[str, Any]:
    """删除长期记忆。

    Args:
        memory_id: 记忆 ID

    Returns:
        删除结果
    """
    try:
        store = get_long_term_memory_store()
        success = store.delete_memory(memory_id)

        if not success:
            raise HTTPException(status_code=404, detail="记忆不存在")

        return {
            "success": True,
            "message": "记忆已删除",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除记忆失败: {e}")


@router.get("/long-term/stats")
async def get_memory_stats() -> dict[str, Any]:
    """获取长期记忆统计信息。

    Returns:
        统计信息
    """
    try:
        store = get_long_term_memory_store()
        stats = store.get_stats()

        return stats

    except Exception as e:
        logger.error(f"获取记忆统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {e}")


@router.post("/long-term/initialize")
async def init_long_term_memory() -> dict[str, Any]:
    """初始化长期记忆系统。

    Returns:
        初始化结果
    """
    try:
        await initialize_long_term_memory()

        return {
            "success": True,
            "message": "长期记忆系统初始化完成",
        }

    except Exception as e:
        logger.error(f"初始化长期记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"初始化失败: {e}")
