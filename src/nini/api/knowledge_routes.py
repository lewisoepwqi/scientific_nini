"""知识库管理 API 端点。

提供知识库文档管理、搜索和检索接口。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from nini.config import settings
from nini.knowledge.hybrid_retriever import get_hybrid_retriever
from nini.models.knowledge import (
    KnowledgeDocumentMetadata,
    KnowledgeSearchResult,
    KnowledgeUploadResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge")

# 文档元数据存储（持久化到 JSON 文件）
_document_store: dict[str, dict[str, Any]] = {}


def _knowledge_dir() -> Path:
    """返回知识库持久化目录。"""
    return settings.knowledge_dir


def _metadata_file() -> Path:
    """返回知识库元数据文件路径。"""
    return _knowledge_dir() / "metadata.json"


def _document_file(doc_id: str) -> Path:
    """返回知识库文档正文文件路径。"""
    return _knowledge_dir() / f"{doc_id}.txt"


def _load_document_store() -> None:
    """从文件加载文档元数据。如果 metadata.json 不存在，扫描现有文档文件。"""
    global _document_store
    knowledge_dir = _knowledge_dir()
    metadata_file = _metadata_file()
    _document_store = {}

    if metadata_file.exists():
        # 从 metadata.json 加载
        try:
            has_stale_metadata = False
            with open(metadata_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 确保只加载有效的文档（文件仍然存在）
                for doc_id, doc_meta in data.items():
                    doc_file = _document_file(doc_id)
                    if doc_file.exists():
                        # 读取文件内容
                        try:
                            with open(doc_file, "r", encoding="utf-8") as df:
                                doc_meta["content"] = df.read()
                            _document_store[doc_id] = doc_meta
                        except Exception as e:
                            logger.warning(f"加载文档内容失败 {doc_id}: {e}")
                    else:
                        logger.warning(f"文档文件不存在，跳过: {doc_id}")
                        has_stale_metadata = True
            if has_stale_metadata:
                # 启动时自动清理失效元数据，避免后续每次重启都重复告警。
                _save_document_store()
            logger.info(f"已加载 {len(_document_store)} 个知识库文档")
        except Exception as e:
            logger.error(f"加载文档元数据失败: {e}")
            _document_store = {}
    else:
        # 扫描现有文档文件重建元数据
        logger.info("metadata.json 不存在，扫描现有文档文件...")
        _document_store = {}
        from datetime import datetime, timezone

        for doc_file in knowledge_dir.glob("*.txt"):
            doc_id = doc_file.stem
            try:
                with open(doc_file, "r", encoding="utf-8") as f:
                    content = f.read()
                stat = doc_file.stat()
                _document_store[doc_id] = {
                    "id": doc_id,
                    "title": doc_file.name,
                    "content": content,
                    "file_type": "txt",
                    "file_size": len(content.encode("utf-8")),
                    "index_status": "indexed",  # 假设已索引
                    "created_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "updated_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "description": "",
                    "domain": "general",
                    "tags": [],
                    "chunk_count": max(1, len(content) // 1000),
                }
                logger.info(f"重建文档元数据: {doc_id}")
            except Exception as e:
                logger.warning(f"读取文档文件失败 {doc_id}: {e}")

        if _document_store:
            _save_document_store()
            logger.info(f"已重建并保存 {len(_document_store)} 个文档元数据")


def _save_document_store() -> None:
    """保存文档元数据到文件（不包含 content 字段）。"""
    try:
        metadata_file = _metadata_file()
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        # 保存时不包含 content 字段（内容存储在单独的文件中）
        metadata_to_save = {}
        for doc_id, doc_meta in _document_store.items():
            meta_copy = {k: v for k, v in doc_meta.items() if k != "content"}
            metadata_to_save[doc_id] = meta_copy
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存文档元数据失败: {e}")


@router.post("/search")
async def search_knowledge(
    query: str,
    top_k: int = 5,
    domain: str | None = None,
) -> dict[str, Any]:
    """搜索知识库。

    Args:
        query: 搜索查询
        top_k: 返回结果数量
        domain: 领域过滤

    Returns:
        搜索结果
    """
    try:
        retriever = await get_hybrid_retriever()
        result = await retriever.search(query, top_k=top_k, domain=domain)
        return result.to_dict()
    except Exception as e:
        logger.error(f"知识库搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@router.get("/documents")
async def list_documents() -> list[dict[str, Any]]:
    """获取知识库文档列表。

    Returns:
        文档元数据列表
    """
    try:
        documents = []
        for doc_id, doc in _document_store.items():
            documents.append(
                {
                    "id": doc_id,
                    "title": doc.get("title", "未知文档"),
                    "file_type": doc.get("file_type", "txt"),
                    "file_size": doc.get("file_size", 0),
                    "index_status": doc.get("index_status", "indexed"),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                    "chunk_count": doc.get("chunk_count", 0),
                }
            )
        return sorted(documents, key=lambda x: x.get("created_at", ""), reverse=True)
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {e}")


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    description: str = Form(""),
    domain: str = Form("general"),
    tags: str = Form(""),
) -> dict[str, Any]:
    """上传知识库文档。

    Args:
        file: 上传的文件
        title: 文档标题（可选，默认为文件名）
        description: 文档描述
        domain: 领域分类
        tags: 标签（逗号分隔）

    Returns:
        上传结果
    """
    try:
        # 生成文档 ID
        doc_id = str(uuid.uuid4())

        # 读取文件内容
        content = await file.read()
        content_str = content.decode("utf-8", errors="ignore")

        # 使用文件名作为默认标题
        doc_title = title or file.filename or "未命名文档"

        # 解析标签
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        # 存储文档元数据
        from datetime import datetime, timezone

        _document_store[doc_id] = {
            "id": doc_id,
            "title": doc_title,
            "content": content_str,
            "file_type": file.filename.split(".")[-1] if file.filename else "txt",
            "file_size": len(content),
            "index_status": "indexing",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "description": description,
            "domain": domain,
            "tags": tag_list,
            "chunk_count": 0,
        }

        # 仅在索引成功后持久化正文，避免失败请求留下可被误恢复的孤儿文件。
        doc_file = _document_file(doc_id)

        # 添加到混合检索器
        retriever = await get_hybrid_retriever()
        metadata = {
            "title": doc_title,
            "description": description,
            "domain": domain,
            "tags": tag_list,
            "file_type": file.filename.split(".")[-1] if file.filename else "txt",
        }

        success = await retriever.add_document(
            doc_id=doc_id,
            content=content_str,
            title=doc_title,
            metadata=metadata,
        )

        if success:
            _document_store[doc_id]["index_status"] = "indexed"
            # 估算 chunk 数量（简单按 1000 字符一个 chunk）
            _document_store[doc_id]["chunk_count"] = max(1, len(content_str) // 1000)
            doc_file.parent.mkdir(parents=True, exist_ok=True)
            doc_file.write_text(content_str, encoding="utf-8")
        else:
            _document_store[doc_id]["index_status"] = "failed"

        # 保存元数据
        _save_document_store()

        return {
            "success": success,
            "document_id": doc_id,
            "message": "文档上传成功" if success else "文档上传失败",
            "index_status": _document_store[doc_id]["index_status"],
        }

    except Exception as e:
        _document_store.pop(doc_id, None)
        cleanup_doc_file: Path | None = _document_file(doc_id) if "doc_id" in locals() else None
        if cleanup_doc_file is not None:
            try:
                cleanup_doc_file.unlink(missing_ok=True)
            except OSError:
                logger.warning("清理失败知识文档正文失败: %s", cleanup_doc_file)
        logger.error(f"文档上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict[str, Any]:
    """删除知识库文档。

    Args:
        document_id: 文档 ID

    Returns:
        删除结果
    """
    try:
        if document_id not in _document_store:
            raise HTTPException(status_code=404, detail="文档不存在")

        # 从检索器中移除
        retriever = await get_hybrid_retriever()
        await retriever.remove_document(document_id)

        # 从存储中移除
        del _document_store[document_id]

        # 保存元数据
        _save_document_store()

        # 删除文档文件
        try:
            doc_file = _document_file(document_id)
            if doc_file.exists():
                doc_file.unlink()
        except Exception as e:
            logger.warning(f"删除文档文件失败 {document_id}: {e}")

        return {
            "success": True,
            "message": "文档已删除",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict[str, Any]:
    """获取文档详情。

    Args:
        document_id: 文档 ID

    Returns:
        文档详情
    """
    try:
        if document_id not in _document_store:
            raise HTTPException(status_code=404, detail="文档不存在")

        doc = _document_store[document_id]
        return {
            "id": doc["id"],
            "title": doc["title"],
            "description": doc.get("description", ""),
            "file_type": doc["file_type"],
            "file_size": doc["file_size"],
            "index_status": doc["index_status"],
            "domain": doc.get("domain", "general"),
            "tags": doc.get("tags", []),
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
            "chunk_count": doc["chunk_count"],
            # 返回前 1000 字符作为预览
            "content_preview": (
                doc["content"][:1000] if len(doc["content"]) > 1000 else doc["content"]
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取详情失败: {e}")


@router.post("/index/rebuild")
async def rebuild_index() -> dict[str, Any]:
    """重建知识库索引。

    Returns:
        重建结果
    """
    try:
        retriever = await get_hybrid_retriever()
        success = await retriever.rebuild_index()

        # 更新所有文档的索引状态
        for doc_id in _document_store:
            _document_store[doc_id]["index_status"] = "indexed" if success else "failed"

        # 保存元数据
        _save_document_store()

        return {
            "success": success,
            "message": "索引重建成功" if success else "索引重建失败",
            "document_count": len(_document_store),
        }

    except Exception as e:
        logger.error(f"重建索引失败: {e}")
        raise HTTPException(status_code=500, detail=f"重建索引失败: {e}")


@router.get("/index/status")
async def get_index_status() -> dict[str, Any]:
    """获取索引状态。

    Returns:
        索引状态信息
    """
    try:
        retriever = await get_hybrid_retriever()
        status = await retriever.get_status()

        # 统计文档状态
        status_counts = {"indexed": 0, "indexing": 0, "failed": 0, "pending": 0}
        for doc in _document_store.values():
            status_counts[doc.get("index_status", "pending")] += 1

        return {
            "vector_store_available": status.get("vector_store_available", False),
            "document_count": len(_document_store),
            "status_breakdown": status_counts,
        }

    except Exception as e:
        logger.error(f"获取索引状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {e}")


@router.get("/context")
async def get_knowledge_context(query: str | None = None) -> dict[str, Any]:
    """获取知识上下文（当前仅提供参数校验与占位响应）。"""
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    raise HTTPException(status_code=501, detail="知识上下文端点暂未实现")


@router.get("/stats")
async def get_knowledge_stats() -> dict[str, Any]:
    """获取知识库统计信息。"""
    indexed = 0
    indexing = 0
    failed = 0
    pending = 0
    for doc in _document_store.values():
        status = str(doc.get("index_status", "pending"))
        if status == "indexed":
            indexed += 1
        elif status == "indexing":
            indexing += 1
        elif status == "failed":
            failed += 1
        else:
            pending += 1

    return {
        "document_count": len(_document_store),
        "status_breakdown": {
            "indexed": indexed,
            "indexing": indexing,
            "failed": failed,
            "pending": pending,
        },
    }


# 模块加载时初始化文档存储
_load_document_store()
