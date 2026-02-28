"""知识库管理 API 端点。

提供知识库文档管理、搜索和检索接口。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from nini.knowledge.hybrid_retriever import get_hybrid_retriever
from nini.models.knowledge import (
    KnowledgeDocumentMetadata,
    KnowledgeSearchResult,
    KnowledgeUploadResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge")

# 模拟文档存储（实际项目中应使用数据库）
_document_store: dict[str, dict[str, Any]] = {}


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
        else:
            _document_store[doc_id]["index_status"] = "failed"

        return {
            "success": success,
            "document_id": doc_id,
            "message": "文档上传成功" if success else "文档上传失败",
            "index_status": _document_store[doc_id]["index_status"],
        }

    except Exception as e:
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
            "content_preview": doc["content"][:1000] if len(doc["content"]) > 1000 else doc["content"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取详情失败: {e}")
