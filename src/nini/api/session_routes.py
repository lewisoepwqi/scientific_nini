"""会话管理路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from nini.agent.session import session_manager
from nini.config import settings
from nini.models.schemas import APIResponse, SessionUpdateRequest

router = APIRouter(prefix="/sessions")


@router.get("", response_model=APIResponse)
async def list_sessions(
    q: str | None = Query(default=None, description="按会话标题关键词过滤"),
    limit: int | None = Query(default=None, ge=1, le=500, description="返回条数上限"),
    offset: int = Query(default=0, ge=0, description="分页偏移量"),
) -> APIResponse:
    """获取所有会话列表。"""
    sessions = session_manager.list_sessions()
    keyword = (q or "").strip().lower()
    if keyword:
        sessions = [item for item in sessions if keyword in str(item.get("title", "")).lower()]
    if offset > 0:
        sessions = sessions[offset:]
    if limit is not None:
        sessions = sessions[:limit]
    return APIResponse(
        success=True,
        data=[
            {
                "id": s["id"],
                "title": s["title"],
                "message_count": s["message_count"],
                "source": s.get("source"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "last_message_at": s.get("last_message_at"),
            }
            for s in sessions
        ],
    )


@router.get("/{session_id}", response_model=APIResponse)
async def get_session(session_id: str) -> APIResponse:
    """获取单个会话信息。"""
    session = session_manager.get_or_create(session_id)

    return APIResponse(
        success=True,
        data={
            "id": session.id,
            "title": session.title,
            "message_count": len(session.messages),
        },
    )


@router.post("", response_model=APIResponse)
async def create_session() -> APIResponse:
    """创建新会话。"""
    session = session_manager.create_session(load_persisted_messages=False)
    return APIResponse(
        success=True,
        data={
            "session_id": session.id,
            "title": session.title,
            "message_count": 0,
        },
    )


@router.patch("/{session_id}", response_model=APIResponse)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
) -> APIResponse:
    """更新会话信息（如标题）。"""
    if request.title:
        session_manager.save_session_title(session_id, request.title)
        if session_manager.get_session(session_id):
            session_manager.update_session_title(session_id, request.title)

    return APIResponse(success=True)


@router.post("/{session_id}/compress", response_model=APIResponse)
async def compress_session(session_id: str, mode: str = "auto"):
    """压缩会话历史。

    Args:
        session_id: 会话ID
        mode: 压缩模式 (auto / lightweight / llm)

    Returns:
        压缩结果
    """
    session = session_manager.get_or_create(session_id)

    if mode == "llm":
        from nini.memory.compression import compress_session_history_with_llm

        result = await compress_session_history_with_llm(session)
    else:
        from nini.memory.compression import compress_session_history

        result = compress_session_history(session, ratio=0.5 if mode == "lightweight" else 0.3)

    # 保存压缩元数据
    session_manager.save_session_compression(
        session_id,
        compressed_context=session.compressed_context,
        compressed_rounds=session.compressed_rounds,
        last_compressed_at=session.last_compressed_at,
    )

    return APIResponse(success=True, data=result)


@router.delete("/{session_id}", response_model=APIResponse)
async def delete_session(session_id: str) -> APIResponse:
    """删除会话。"""
    session_manager.remove_session(session_id, delete_persistent=True)
    return APIResponse(success=True)


@router.post("/{session_id}/rollback", response_model=APIResponse)
async def rollback_session(session_id: str) -> APIResponse:
    """回滚会话到压缩前的状态（撤销压缩）。"""
    session = session_manager.get_or_create(session_id)

    if not session.compressed_context:
        return APIResponse(success=False, error="会话没有压缩历史")

    # 恢复压缩前的消息
    from nini.memory.compression import rollback_compression

    rollback_result = rollback_compression(session)
    if not rollback_result.get("success"):
        return APIResponse(success=False, error=str(rollback_result.get("message", "回滚失败")))

    # 保存回滚状态
    session_manager.save_session_compression(
        session_id,
        compressed_context=session.compressed_context,
        compressed_rounds=session.compressed_rounds,
        last_compressed_at=session.last_compressed_at,
    )

    return APIResponse(
        success=True,
        data={
            "message_count": len(session.messages),
            "compressed_rounds": session.compressed_rounds,
        },
    )


@router.get("/{session_id}/token-usage", response_model=APIResponse)
async def get_session_token_usage(session_id: str):
    """获取会话的 token 消耗统计。"""
    from nini.utils.token_counter import get_tracker

    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    tracker = get_tracker(session_id)
    return APIResponse(data=tracker.to_dict())


@router.get("/{session_id}/memory-files", response_model=APIResponse)
async def list_memory_files(session_id: str):
    """列出会话记忆文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    session_dir = settings.sessions_dir / session_id
    files: list[dict[str, Any]] = []

    for filename in ("memory.jsonl", "knowledge.md", "meta.json"):
        fpath = session_dir / filename
        if fpath.exists() and fpath.is_file():
            stat = fpath.stat()
            info: dict[str, Any] = {
                "name": filename,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
            if filename == "memory.jsonl":
                try:
                    info["line_count"] = sum(1 for _ in open(fpath, "r", encoding="utf-8"))
                except Exception:
                    info["line_count"] = 0
            files.append(info)

    archive_dir = session_dir / "archive"
    if archive_dir.exists() and archive_dir.is_dir():
        for apath in sorted(archive_dir.glob("*.json")):
            stat = apath.stat()
            files.append(
                {
                    "name": f"archive/{apath.name}",
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )

    session = session_manager.get_session(session_id)
    compression_info: dict[str, Any] = {}
    if session is not None:
        compression_info = {
            "compressed_rounds": getattr(session, "compressed_rounds", 0),
            "last_compressed_at": getattr(session, "last_compressed_at", None),
        }

    return APIResponse(
        data={
            "session_id": session_id,
            "files": files,
            "compression": compression_info,
        }
    )


@router.get("/{session_id}/memory-files/{filename:path}", response_model=APIResponse)
async def read_memory_file(session_id: str, filename: str):
    """读取记忆文件内容（前 200 行）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    safe_name = Path(filename)
    if ".." in safe_name.parts:
        raise HTTPException(status_code=400, detail="无效的文件路径")

    session_dir = settings.sessions_dir / session_id
    fpath = session_dir / safe_name
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        fpath.resolve().relative_to(session_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的文件路径")

    lines: list[str] = []
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 200:
                    break
                lines.append(line.rstrip("\n"))
    except Exception:
        raise HTTPException(status_code=500, detail="无法读取文件")

    return APIResponse(
        data={
            "session_id": session_id,
            "filename": filename,
            "content": "\n".join(lines),
            "truncated": len(lines) >= 200,
        }
    )


@router.get("/{session_id}/context-size", response_model=APIResponse)
async def get_session_context_size(session_id: str):
    """获取当前会话上下文的 token 预估。"""
    from nini.utils.token_counter import count_messages_tokens, count_tokens

    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    session = session_manager.get_or_create(session_id)

    message_tokens = count_messages_tokens(session.messages)
    compressed_tokens = 0
    if getattr(session, "compressed_context", ""):
        compressed_tokens = count_tokens(str(session.compressed_context))
    total_tokens = message_tokens + compressed_tokens
    threshold_tokens = int(settings.auto_compress_threshold_tokens)
    target_tokens = int(settings.auto_compress_target_tokens)
    remaining_until_compress = max(threshold_tokens - total_tokens, 0)

    return APIResponse(
        data={
            "session_id": session_id,
            "message_count": len(session.messages),
            "message_tokens": message_tokens,
            "compressed_context_tokens": compressed_tokens,
            "total_context_tokens": total_tokens,
            "auto_compress_enabled": bool(settings.auto_compress_enabled),
            "compress_threshold_tokens": threshold_tokens,
            "compress_target_tokens": target_tokens,
            "remaining_until_compress_tokens": remaining_until_compress,
        }
    )


@router.get("/{session_id}/export-all")
async def export_all_session_data(session_id: str):
    """导出会话的所有数据（JSON 格式）。"""
    from fastapi.responses import JSONResponse

    session = session_manager.get_or_create(session_id)

    export_data = {
        "session_id": session_id,
        "title": session.title,
        "messages": session.messages,
        "datasets": list(session.datasets.keys()) if hasattr(session, "datasets") else [],
        "artifacts": session.artifacts if hasattr(session, "artifacts") else [],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f"attachment; filename=nini_session_{session_id}.json"},
    )


# 导入需要在文件末尾以避免循环导入
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.memory.conversation import ConversationMemory
from nini.utils.chart_payload import normalize_chart_payload


def _serialize_history_message(msg: dict[str, Any]) -> dict[str, Any]:
    """序列化会话消息历史，返回统一对外契约。"""
    chart_data = msg.get("chart_data")
    normalized_chart_data = normalize_chart_payload(chart_data)
    item = {
        "role": msg.get("role", ""),
        "content": msg.get("content", ""),
        "_ts": msg.get("_ts"),
        "message_id": msg.get("message_id"),
        "turn_id": msg.get("turn_id"),
        "event_type": msg.get("event_type"),
        "operation": msg.get("operation"),
        "tool_calls": msg.get("tool_calls"),
        "tool_call_id": msg.get("tool_call_id"),
        "tool_name": msg.get("tool_name"),
        "status": msg.get("status"),
        "intent": msg.get("intent"),
        "execution_id": msg.get("execution_id"),
        "reasoning_id": msg.get("reasoning_id"),
        "reasoning_live": msg.get("reasoning_live"),
        "reasoning_type": msg.get("reasoning_type"),
        "key_decisions": msg.get("key_decisions"),
        "confidence_score": msg.get("confidence_score"),
        "chart_data": normalized_chart_data if normalized_chart_data else chart_data,
        "data_preview": msg.get("data_preview"),
        "artifacts": msg.get("artifacts"),
        "images": msg.get("images"),
    }
    return item
