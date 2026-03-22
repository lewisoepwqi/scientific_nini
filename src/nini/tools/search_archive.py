"""归档历史检索工具：在已压缩的归档消息中进行关键词搜索。

当对话历史被压缩归档后，Agent 可通过本工具主动检索
archive/ 目录下的原始消息内容，找回已被压缩的历史信息。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nini.agent.session import Session
from nini.config import settings
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

# 单次最多扫描的归档文件数（避免大量归档时性能下降）
_MAX_FILES_TO_SCAN = 50
# 消息内容摘要长度
_SNIPPET_LENGTH = 200


def _extract_message_text(msg: dict[str, Any]) -> str:
    """从消息字典中提取可检索的纯文本内容。"""
    role = str(msg.get("role", "")).strip()
    content = msg.get("content", "")

    if isinstance(content, list):
        # 多模态消息：提取所有文本块
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        content = " ".join(parts)
    else:
        content = str(content)

    # 工具调用消息补充工具名
    if role == "assistant" and msg.get("tool_calls"):
        tool_calls = msg.get("tool_calls", [])
        names = []
        for item in (tool_calls or [])[:4]:
            if isinstance(item, dict):
                func = item.get("function", {})
                if isinstance(func, dict) and (name := str(func.get("name", "")).strip()):
                    names.append(name)
        if names:
            content = f"[工具调用: {', '.join(names)}] {content}"

    return content.strip()


class SearchMemoryArchiveTool(Tool):
    """在当前会话的压缩历史归档中，通过关键词检索已被压缩的对话记录。"""

    @property
    def name(self) -> str:
        return "search_memory_archive"

    @property
    def description(self) -> str:
        return (
            "在当前会话被压缩归档的历史对话中，通过关键词搜索相关记录。"
            "当你需要回忆某个具体的分析细节、数值或结论，但当前上下文中已没有该信息时使用。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "检索关键词，支持中英文，区分大小写不敏感，全文模糊匹配",
                },
                "max_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "返回结果数上限，默认 5 条",
                },
            },
            "required": ["keyword"],
        }

    @property
    def category(self) -> str:
        return "utility"

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """检索归档历史中包含关键词的消息。

        检索路径优先级：
        1. SQLite archived_messages/FTS5（若 session.db 存在）
        2. search_index.jsonl 增量索引（旧格式兼容）
        3. 物理 archive/*.json 文件全量扫描

        未被索引的旧归档文件仍通过全量扫描补充，确保结果完整。
        """
        keyword: str = kwargs.get("keyword", "")
        max_results: int = int(kwargs.get("max_results", 5))
        if not keyword or not keyword.strip():
            return ToolResult(success=False, message="关键词不能为空")

        keyword = keyword.strip()
        max_results = max(1, min(max_results, 20))

        session_dir = settings.sessions_dir / session.id
        archive_dir = session_dir / "archive"
        if not archive_dir.exists() and not session_dir.exists():
            return ToolResult(
                success=True,
                data={"results": [], "files_searched": 0},
                message="当前会话尚无压缩归档，无历史可检索",
            )

        keyword_lower = keyword.lower()

        # ---- 优先路径：SQLite 查询 ----
        db_result = await self._search_sqlite(session_dir, keyword_lower, max_results)
        if db_result is not None:
            return db_result

        # ---- 若无 SQLite，回退到旧路径 ----
        if not archive_dir.exists():
            return ToolResult(
                success=True,
                data={"results": [], "files_searched": 0},
                message="当前会话尚无压缩归档，无历史可检索",
            )

        results: list[dict[str, Any]] = []
        indexed_files: set[str] = set()

        # ---- 旧路径 1：读取 search_index.jsonl 增量索引 ----
        index_path = archive_dir / "search_index.jsonl"
        if index_path.exists():
            try:
                with index_path.open("r", encoding="utf-8") as f:
                    for raw_line in f:
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        entry = json.loads(raw_line)
                        fname = str(entry.get("file", ""))
                        if fname:
                            indexed_files.add(fname)
                        text = str(entry.get("text", ""))
                        if keyword_lower in text.lower():
                            snippet = text[:_SNIPPET_LENGTH]
                            if len(text) > _SNIPPET_LENGTH:
                                snippet += "…"
                            results.append(
                                {
                                    "archive_file": fname,
                                    "role": str(entry.get("role", "unknown")),
                                    "snippet": snippet,
                                }
                            )
            except Exception as exc:
                logger.warning("读取搜索索引失败，回退到全量扫描: %s", exc)
                indexed_files = set()
                results = []

        # ---- 旧路径 2：全量扫描未索引的归档文件 ----
        unindexed = sorted(
            (f for f in archive_dir.glob("compressed_*.json") if f.name not in indexed_files),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:_MAX_FILES_TO_SCAN]

        for archive_file in unindexed:
            try:
                data = json.loads(archive_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("读取归档文件失败: %s, 原因: %s", archive_file.name, exc)
                continue

            messages = data if isinstance(data, list) else data.get("messages", [])
            for msg in messages:
                text = _extract_message_text(msg)
                if keyword_lower in text.lower():
                    snippet = text[:_SNIPPET_LENGTH]
                    if len(text) > _SNIPPET_LENGTH:
                        snippet += "…"
                    results.append(
                        {
                            "archive_file": archive_file.name,
                            "role": msg.get("role", "unknown"),
                            "snippet": snippet,
                        }
                    )

        top_results = results[:max_results]
        total_sources = len(indexed_files) + len(unindexed)
        used_index = bool(indexed_files)
        return ToolResult(
            success=True,
            data={
                "results": top_results,
                "files_searched": len(unindexed),
                "indexed_files": len(indexed_files),
                "used_index": used_index,
            },
            message=(
                f"（{'索引+' if used_index else ''}全量扫描）"
                f"在 {total_sources} 个归档来源中找到 {len(top_results)} 条相关记录"
            ),
        )

    async def _search_sqlite(
        self, session_dir: Any, keyword_lower: str, max_results: int
    ) -> "ToolResult | None":
        """通过 SQLite 检索归档消息。

        返回 ToolResult（若 DB 存在且查询成功），否则返回 None（调用方应 fallback）。
        使用 FTS5 MATCH（若可用），否则使用 LIKE 全表扫描。
        """
        import asyncio

        from nini.memory.db import (
            get_indexed_archive_files,
            get_session_db,
            is_fts5_available,
        )

        db_filename = getattr(settings, "session_db_filename", "session.db")
        db_path = session_dir / db_filename
        if not db_path.exists():
            return None

        def _query() -> "ToolResult | None":
            conn = get_session_db(session_dir, create=False)
            if conn is None:
                return None
            try:
                results: list[dict[str, Any]] = []
                indexed_files: set[str] = set()

                try:
                    indexed_files = get_indexed_archive_files(conn)
                except Exception:
                    pass

                if not indexed_files:
                    return None  # DB 存在但无归档数据，让 fallback 处理

                # FTS5 路径
                if is_fts5_available():
                    try:
                        # 对中文支持较好的 FTS5 引号精确短语搜索
                        fts_keyword = f'"{keyword_lower}"'
                        rows = conn.execute(
                            "SELECT archive_file, role, content FROM archived_fts "
                            "WHERE archived_fts MATCH ? LIMIT ?",
                            (fts_keyword, max_results * 2),
                        ).fetchall()
                        for row in rows:
                            content = str(row[2] or "")
                            if keyword_lower not in content.lower():
                                continue  # FTS5 结果中再次过滤，确保精度
                            snippet = content[:_SNIPPET_LENGTH]
                            if len(content) > _SNIPPET_LENGTH:
                                snippet += "…"
                            results.append(
                                {
                                    "archive_file": str(row[0]),
                                    "role": str(row[1]),
                                    "snippet": snippet,
                                }
                            )
                    except Exception as exc:
                        logger.debug("FTS5 查询失败，降级到 LIKE: %s", exc)
                        results = []

                # LIKE 路径（FTS5 无结果或不可用时）
                if not results:
                    rows = conn.execute(
                        "SELECT archive_file, role, content FROM archived_messages "
                        "WHERE lower(content) LIKE ? LIMIT ?",
                        (f"%{keyword_lower}%", max_results * 2),
                    ).fetchall()
                    for row in rows:
                        content = str(row[2] or "")
                        snippet = content[:_SNIPPET_LENGTH]
                        if len(content) > _SNIPPET_LENGTH:
                            snippet += "…"
                        results.append(
                            {
                                "archive_file": str(row[0]),
                                "role": str(row[1]),
                                "snippet": snippet,
                            }
                        )

                # 补充扫描：物理 archive/*.json 中未被 SQLite 收录的旧文件
                archive_dir = session_dir / "archive"
                unindexed_files: list[Any] = []
                if archive_dir.exists():
                    unindexed_files = sorted(
                        (
                            f
                            for f in archive_dir.glob("compressed_*.json")
                            if f.name not in indexed_files
                        ),
                        key=lambda f: f.stat().st_mtime,
                        reverse=True,
                    )[:_MAX_FILES_TO_SCAN]
                    for archive_file in unindexed_files:
                        try:
                            data = json.loads(archive_file.read_text(encoding="utf-8"))
                            messages = data if isinstance(data, list) else data.get("messages", [])
                            for msg in messages:
                                text = _extract_message_text(msg)
                                if keyword_lower in text.lower():
                                    snippet = text[:_SNIPPET_LENGTH]
                                    if len(text) > _SNIPPET_LENGTH:
                                        snippet += "…"
                                    results.append(
                                        {
                                            "archive_file": archive_file.name,
                                            "role": msg.get("role", "unknown"),
                                            "snippet": snippet,
                                        }
                                    )
                        except (json.JSONDecodeError, OSError) as exc:
                            logger.warning("读取归档文件失败: %s, 原因: %s", archive_file.name, exc)

                top_results = results[:max_results]
                return ToolResult(
                    success=True,
                    data={
                        "results": top_results,
                        "files_searched": len(unindexed_files),
                        "indexed_files": len(indexed_files),
                        "used_index": True,
                    },
                    message=(
                        f"（SQLite 索引+{'全量扫描' if unindexed_files else ''}）"
                        f"在 {len(indexed_files) + len(unindexed_files)} 个归档来源中找到 {len(top_results)} 条相关记录"
                    ),
                )
            except Exception as exc:
                logger.warning("SQLite 归档检索失败，回退到旧路径: %s", exc)
                return None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)
