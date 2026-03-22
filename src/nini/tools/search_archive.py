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
        """检索归档历史中包含关键词的消息。"""
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

        # 按修改时间降序（最新归档优先），限制扫描数量
        files = sorted(
            archive_dir.glob("compressed_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:_MAX_FILES_TO_SCAN]

        results: list[dict[str, Any]] = []
        keyword_lower = keyword.lower()

        for archive_file in files:
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
        return SkillResult(
            success=True,
            data={"results": top_results, "files_searched": len(files)},
            message=f"在 {len(files)} 个归档文件中找到 {len(top_results)} 条相关记录",
        )
