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
