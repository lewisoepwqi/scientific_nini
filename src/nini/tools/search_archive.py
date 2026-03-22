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
from nini.tools.base import Skill, SkillResult

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


class SearchMemoryArchiveTool(Skill):
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

    async def execute(
        self, session: Session, *, keyword: str, max_results: int = 5
    ) -> SkillResult:
        """检索归档历史中包含关键词的消息。

        优先使用 search_index.jsonl 增量索引（O(entries) 遍历）；
        对未被索引覆盖的归档文件仍进行全量扫描，确保结果完整。
        索引损坏时自动降级为纯全量扫描。
        """
        if not keyword or not keyword.strip():
            return SkillResult(success=False, message="关键词不能为空")

        keyword = keyword.strip()
        max_results = max(1, min(max_results, 20))

        archive_dir = settings.sessions_dir / session.id / "archive"
        if not archive_dir.exists():
            return SkillResult(
                success=True,
                data={"results": [], "files_searched": 0},
                message="当前会话尚无压缩归档，无历史可检索",
            )

        keyword_lower = keyword.lower()
        results: list[dict[str, Any]] = []
        indexed_files: set[str] = set()

        # ---- 优先路径：读取增量索引 ----
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

        # ---- 补充扫描：覆盖索引未收录的旧归档文件 ----
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
        return SkillResult(
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
