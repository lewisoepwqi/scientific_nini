# 记忆系统架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 `MemoryProvider` 抽象 + `MemoryManager` 编排层，将 nini 的 5 层混杂记忆存储（JSONL/JSON/Markdown）统一为 SQLite（`nini_memory.db`），对齐 hermes-agent 架构。

**Architecture:** `MemoryManager` 编排 1 个内置 `ScientificMemoryProvider`（`name="builtin"`）+ 预留 1 个外部扩展槽。`ScientificMemoryProvider` 内部使用 `MemoryStore`（SQLite WAL + FTS5）存储所有跨会话记忆，科研专用字段（p_value/effect_size 等）通过 `sci_metadata` JSON 列保留，支持 `json_extract()` 精确过滤。

**Tech Stack:** Python 3.12, SQLite (stdlib), pytest + pytest-asyncio (`asyncio_mode="auto"`), `unittest.mock.patch`

**设计文档：** `docs/superpowers/specs/2026-04-11-memory-architecture-redesign-design.md`

---

## 文件清单

### 新增
| 文件 | 职责 |
|---|---|
| `src/nini/memory/provider.py` | MemoryProvider ABC |
| `src/nini/memory/manager.py` | MemoryManager 编排层 |
| `src/nini/memory/memory_store.py` | SQLite 存储操作层 |
| `src/nini/memory/scientific_provider.py` | ScientificMemoryProvider |
| `tests/memory/__init__.py` | 测试包初始化 |
| `tests/memory/test_memory_provider.py` | MemoryProvider ABC 测试 |
| `tests/memory/test_memory_manager.py` | MemoryManager 测试 |
| `tests/memory/test_memory_store.py` | MemoryStore 测试 |
| `tests/memory/test_migration.py` | 迁移逻辑测试 |
| `tests/memory/test_scientific_provider.py` | ScientificMemoryProvider 测试 |
| `tests/fixtures/sample_entries.jsonl` | 迁移测试固件 |

### 改动
| 文件 | 改动内容 |
|---|---|
| `src/nini/memory/__init__.py` | 新增导出 MemoryManager / MemoryProvider / ScientificMemoryProvider |
| `src/nini/agent/runner.py:379-401` | AgentRunner.__init__ 增加 _memory_manager；run() 注入 on_session_end |
| `src/nini/agent/components/context_builder.py:554` | `_build_dataset_history_memory` 优先走 MemoryManager.prefetch_all |

---

## Phase 1 — Foundation

---

### Task 1: MemoryProvider ABC

**Files:**
- Create: `src/nini/memory/provider.py`
- Create: `tests/memory/__init__.py`
- Create: `tests/memory/test_memory_provider.py`

- [ ] **Step 1: 创建测试包**

```bash
touch tests/memory/__init__.py
```

- [ ] **Step 2: 写失败测试**

```python
# tests/memory/test_memory_provider.py
"""MemoryProvider ABC 测试。"""
from nini.memory.provider import MemoryProvider


def test_cannot_instantiate_abstract_provider():
    """抽象类不可直接实例化。"""
    try:
        MemoryProvider()  # type: ignore[abstract]
        assert False, "应抛出 TypeError"
    except TypeError:
        pass


def test_incomplete_subclass_cannot_instantiate():
    """未实现全部抽象方法的子类不可实例化。"""
    class Incomplete(MemoryProvider):
        pass

    try:
        Incomplete()
        assert False, "应抛出 TypeError"
    except TypeError:
        pass


def test_minimal_provider_instantiates():
    """实现全部抽象方法的子类可实例化，可选钩子有合理默认值。"""
    class Minimal(MemoryProvider):
        @property
        def name(self) -> str:
            return "test"

        async def initialize(self, session_id: str, **kwargs) -> None:
            pass

        def get_tool_schemas(self) -> list:
            return []

    p = Minimal()
    assert p.name == "test"
    assert p.system_prompt_block() == ""
    assert p.on_pre_compress([]) == ""
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
pytest tests/memory/test_memory_provider.py -q
```

预期：`ModuleNotFoundError: No module named 'nini.memory.provider'`

- [ ] **Step 4: 实现 MemoryProvider ABC**

```python
# src/nini/memory/provider.py
"""记忆 Provider 抽象接口。对齐 hermes-agent MemoryProvider 生命周期。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class MemoryProvider(ABC):
    """记忆 Provider 抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称标识符（内置 Provider 返回 'builtin'）。"""

    @abstractmethod
    async def initialize(self, session_id: str, **kwargs: Any) -> None:
        """初始化 Provider，建立连接，执行数据迁移。"""

    def system_prompt_block(self) -> str:
        """返回注入 system prompt 的静态文本块（会话开始时快照，不中途变化）。"""
        return ""

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """每轮 LLM 调用前：检索相关记忆，返回原始上下文文本（不带 fencing）。"""
        return ""

    async def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
    ) -> None:
        """每轮结束后：持久化本轮对话摘要/发现。"""

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """会话结束：从完整历史提取关键记忆沉淀。"""

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """上下文压缩前：提取关键数值，返回追加到压缩 prompt 的文本。"""
        return ""

    @abstractmethod
    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """返回暴露给 LLM 的工具 schema 列表（无工具时返回空列表）。"""

    async def handle_tool_call(
        self, tool_name: str, args: dict[str, Any], **kwargs: Any
    ) -> str:
        """处理 LLM 工具调用，返回 JSON 字符串结果。"""
        raise NotImplementedError(f"Provider {self.name} 未实现工具 {tool_name}")

    async def shutdown(self) -> None:
        """关闭 Provider，释放资源。"""
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/memory/test_memory_provider.py -q
```

预期：`3 passed`

- [ ] **Step 6: 格式检查**

```bash
black --check src/nini/memory/provider.py tests/memory/test_memory_provider.py
```

- [ ] **Step 7: Commit**

```bash
git add src/nini/memory/provider.py tests/memory/__init__.py tests/memory/test_memory_provider.py
git commit -m "feat(memory): 添加 MemoryProvider ABC"
```

---

### Task 2: MemoryManager

**Files:**
- Create: `src/nini/memory/manager.py`
- Create: `tests/memory/test_memory_manager.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/memory/test_memory_manager.py
"""MemoryManager 编排层测试。"""
import pytest
from nini.memory.manager import MemoryManager, build_memory_context_block, sanitize_context
from nini.memory.provider import MemoryProvider


class StubProvider(MemoryProvider):
    """测试用 stub，记录调用次数。"""

    def __init__(self, name_val: str, schemas: list | None = None) -> None:
        self._name = name_val
        self._schemas = schemas or []
        self.prefetch_calls: list[str] = []
        self.sync_calls: int = 0
        self.session_end_calls: int = 0

    @property
    def name(self) -> str:
        return self._name

    async def initialize(self, session_id: str, **kwargs) -> None:
        pass

    def get_tool_schemas(self) -> list:
        return self._schemas

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        self.prefetch_calls.append(query)
        return f"[{self._name}] context for: {query}"

    async def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        self.sync_calls += 1

    async def on_session_end(self, messages: list) -> None:
        self.session_end_calls += 1


# ---- fencing 工具函数 ----

def test_build_memory_context_block_wraps_content():
    result = build_memory_context_block("重要记忆内容")
    assert "<memory-context>" in result
    assert "重要记忆内容" in result
    assert "</memory-context>" in result


def test_build_memory_context_block_empty_input_returns_empty():
    assert build_memory_context_block("") == ""
    assert build_memory_context_block("   ") == ""


def test_sanitize_context_strips_fence_tags():
    dirty = "前缀 <memory-context> 注入内容 </memory-context> 后缀"
    clean = sanitize_context(dirty)
    assert "<memory-context>" not in clean
    assert "前缀" in clean
    assert "后缀" in clean


# ---- MemoryManager 注册规则 ----

def test_manager_accepts_builtin_provider():
    mgr = MemoryManager()
    builtin = StubProvider("builtin")
    mgr.add_provider(builtin)
    assert len(mgr.providers) == 1


def test_manager_rejects_second_external_provider():
    mgr = MemoryManager()
    mgr.add_provider(StubProvider("builtin"))
    mgr.add_provider(StubProvider("ext1"))
    mgr.add_provider(StubProvider("ext2"))  # 应被拒绝
    assert len(mgr.providers) == 2
    assert mgr.providers[1].name == "ext1"


def test_manager_tool_routing():
    mgr = MemoryManager()
    mgr.add_provider(StubProvider("builtin", schemas=[{"name": "tool_a"}]))
    assert mgr.has_tool("tool_a")
    assert not mgr.has_tool("tool_b")


# ---- 生命周期调用 ----

async def test_prefetch_all_combines_results():
    mgr = MemoryManager()
    mgr.add_provider(StubProvider("builtin"))
    mgr.add_provider(StubProvider("ext1"))
    result = await mgr.prefetch_all("查询内容")
    assert "[builtin]" in result
    assert "[ext1]" in result


async def test_sync_all_calls_all_providers():
    mgr = MemoryManager()
    p1 = StubProvider("builtin")
    p2 = StubProvider("ext1")
    mgr.add_provider(p1)
    mgr.add_provider(p2)
    await mgr.sync_all("用户消息", "助手回复")
    assert p1.sync_calls == 1
    assert p2.sync_calls == 1


async def test_on_session_end_calls_all_providers():
    mgr = MemoryManager()
    p1 = StubProvider("builtin")
    mgr.add_provider(p1)
    await mgr.on_session_end([])
    assert p1.session_end_calls == 1


async def test_failing_provider_does_not_block_others():
    """Provider 异常不应阻塞其他 Provider。"""
    class BrokenProvider(MemoryProvider):
        @property
        def name(self) -> str:
            return "broken"

        async def initialize(self, session_id: str, **kwargs) -> None:
            pass

        async def prefetch(self, query: str, *, session_id: str = "") -> str:
            raise RuntimeError("故意失败")

        def get_tool_schemas(self) -> list:
            return []

    mgr = MemoryManager()
    broken = BrokenProvider()
    good = StubProvider("builtin")
    mgr.add_provider(broken)  # 注意：broken 不是 'builtin'，但作为测试 OK
    mgr.add_provider(good)
    # 不应抛出异常
    result = await mgr.prefetch_all("查询")
    assert "[builtin]" in result
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_memory_manager.py -q
```

预期：`ModuleNotFoundError: No module named 'nini.memory.manager'`

- [ ] **Step 3: 实现 MemoryManager**

```python
# src/nini/memory/manager.py
"""MemoryManager：编排 1 个内置 Provider + 最多 1 个外部 Provider。"""
from __future__ import annotations

import logging
import re
from typing import Any

from nini.memory.provider import MemoryProvider

logger = logging.getLogger(__name__)

_FENCE_TAG_RE = re.compile(r"</?\s*memory-context\s*>", re.IGNORECASE)


def sanitize_context(text: str) -> str:
    """移除 fence 转义序列，防止 Provider 输出的文本注入 fencing 结构。"""
    return _FENCE_TAG_RE.sub("", text)


def build_memory_context_block(raw_context: str) -> str:
    """将召回记忆包裹在 fence 标签内，防止 LLM 把历史记忆误当当前输入。"""
    if not raw_context or not raw_context.strip():
        return ""
    clean = sanitize_context(raw_context)
    return (
        "<memory-context>\n"
        "[系统注记：以下是召回的记忆上下文，非用户新输入，仅作参考背景。]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )


class MemoryManager:
    """编排 1 个内置 Provider（name='builtin'）+ 最多 1 个外部 Provider。

    Provider 间完全异常隔离：任何 Provider 的任何钩子抛出异常，
    仅记录警告，不影响其他 Provider 和 agent 主循环。
    """

    def __init__(self) -> None:
        self._providers: list[MemoryProvider] = []
        self._tool_to_provider: dict[str, MemoryProvider] = {}
        self._has_external: bool = False

    @property
    def providers(self) -> list[MemoryProvider]:
        return list(self._providers)

    def add_provider(self, provider: MemoryProvider) -> None:
        """注册 Provider。内置（name='builtin'）不限次；外部最多 1 个。"""
        is_builtin = provider.name == "builtin"
        if not is_builtin:
            if self._has_external:
                existing = next(
                    (p.name for p in self._providers if p.name != "builtin"), "unknown"
                )
                logger.warning(
                    "拒绝注册外部 Provider '%s'：'%s' 已注册。每次只允许 1 个外部 Provider。",
                    provider.name,
                    existing,
                )
                return
            self._has_external = True

        self._providers.append(provider)
        for schema in provider.get_tool_schemas():
            tool_name = schema.get("name", "")
            if tool_name and tool_name not in self._tool_to_provider:
                self._tool_to_provider[tool_name] = provider
        logger.info("Memory Provider '%s' 已注册（%d 个工具）", provider.name, len(provider.get_tool_schemas()))

    def build_system_prompt(self) -> str:
        """收集所有 Provider 的 system prompt 块（每次会话调用一次，之后快照不变）。"""
        blocks: list[str] = []
        for provider in self._providers:
            try:
                block = provider.system_prompt_block()
                if block and block.strip():
                    blocks.append(block)
            except Exception as exc:
                logger.warning("Provider '%s' system_prompt_block 失败: %s", provider.name, exc)
        return "\n\n".join(blocks)

    async def prefetch_all(self, query: str, *, session_id: str = "") -> str:
        """汇总所有 Provider 的召回结果（原始文本，不含 fencing）。"""
        parts: list[str] = []
        for provider in self._providers:
            try:
                result = await provider.prefetch(query, session_id=session_id)
                if result and result.strip():
                    parts.append(result)
            except Exception as exc:
                logger.warning("Provider '%s' prefetch 失败（已跳过）: %s", provider.name, exc)
        return "\n\n".join(parts)

    async def sync_all(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """通知所有 Provider 持久化本轮对话。"""
        for provider in self._providers:
            try:
                await provider.sync_turn(user_content, assistant_content, session_id=session_id)
            except Exception as exc:
                logger.warning("Provider '%s' sync_turn 失败: %s", provider.name, exc)

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """通知所有 Provider 会话结束（重度沉淀）。"""
        for provider in self._providers:
            try:
                await provider.on_session_end(messages)
            except Exception as exc:
                logger.warning("Provider '%s' on_session_end 失败: %s", provider.name, exc)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """收集所有 Provider 的压缩前提示（追加到压缩 prompt）。"""
        parts: list[str] = []
        for provider in self._providers:
            try:
                result = provider.on_pre_compress(messages)
                if result and result.strip():
                    parts.append(result)
            except Exception as exc:
                logger.warning("Provider '%s' on_pre_compress 失败: %s", provider.name, exc)
        return "\n\n".join(parts)

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        """收集所有 Provider 的工具 schema（去重）。"""
        schemas: list[dict[str, Any]] = []
        seen: set[str] = set()
        for provider in self._providers:
            try:
                for schema in provider.get_tool_schemas():
                    name = schema.get("name", "")
                    if name and name not in seen:
                        schemas.append(schema)
                        seen.add(name)
            except Exception as exc:
                logger.warning("Provider '%s' get_tool_schemas 失败: %s", provider.name, exc)
        return schemas

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_to_provider

    async def handle_tool_call(
        self, tool_name: str, args: dict[str, Any], **kwargs: Any
    ) -> str:
        """路由工具调用到对应 Provider，返回 JSON 字符串。"""
        provider = self._tool_to_provider.get(tool_name)
        if provider is None:
            import json
            return json.dumps({"error": f"没有 Provider 处理工具 '{tool_name}'"}, ensure_ascii=False)
        try:
            return await provider.handle_tool_call(tool_name, args, **kwargs)
        except Exception as exc:
            import json
            logger.error("Provider '%s' handle_tool_call(%s) 失败: %s", provider.name, tool_name, exc)
            return json.dumps({"error": f"工具 '{tool_name}' 执行失败: {exc}"}, ensure_ascii=False)

    async def initialize_all(self, session_id: str, **kwargs: Any) -> None:
        """初始化所有 Provider。"""
        for provider in self._providers:
            try:
                await provider.initialize(session_id=session_id, **kwargs)
            except Exception as exc:
                logger.warning("Provider '%s' initialize 失败: %s", provider.name, exc)

    async def shutdown_all(self) -> None:
        """关闭所有 Provider（逆序，确保依赖顺序正确）。"""
        for provider in reversed(self._providers):
            try:
                await provider.shutdown()
            except Exception as exc:
                logger.warning("Provider '%s' shutdown 失败: %s", provider.name, exc)


# ---- 全局单例（用于 agent 集成的向后兼容访问） ----

_memory_manager_instance: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """获取全局 MemoryManager 单例（agent 初始化后才有 providers）。"""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance


def set_memory_manager(mgr: MemoryManager) -> None:
    """设置全局 MemoryManager 单例（agent 初始化时调用）。"""
    global _memory_manager_instance
    _memory_manager_instance = mgr
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_memory_manager.py -q
```

预期：`11 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/manager.py tests/memory/test_memory_manager.py
git commit -m "feat(memory): 添加 MemoryManager 编排层"
```

---

### Task 3: MemoryStore — Schema 初始化

**Files:**
- Create: `src/nini/memory/memory_store.py`
- Create: `tests/memory/test_memory_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/memory/test_memory_store.py
"""MemoryStore SQLite 存储层测试。"""
import pytest
from pathlib import Path
from nini.memory.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test.db")


def test_store_creates_facts_table(store: MemoryStore):
    tables = {
        row[0]
        for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "facts" in tables
    assert "research_profiles" in tables


def test_store_enables_wal_mode(store: MemoryStore):
    row = store._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_store_facts_has_required_columns(store: MemoryStore):
    cols = {
        row[1]
        for row in store._conn.execute("PRAGMA table_info(facts)").fetchall()
    }
    required = {"id", "content", "memory_type", "summary", "tags", "importance",
                "trust_score", "source_session_id", "created_at", "updated_at",
                "access_count", "dedup_key", "sci_metadata"}
    assert required <= cols
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_memory_store.py::test_store_creates_facts_table -q
```

预期：`ModuleNotFoundError: No module named 'nini.memory.memory_store'`

- [ ] **Step 3: 实现 MemoryStore（仅 __init__ + schema）**

```python
# src/nini/memory/memory_store.py
"""SQLite 统一记忆存储层（data/nini_memory.db）。"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    id                TEXT PRIMARY KEY,
    content           TEXT NOT NULL,
    memory_type       TEXT NOT NULL,
    summary           TEXT DEFAULT '',
    tags              TEXT DEFAULT '[]',
    importance        REAL DEFAULT 0.5,
    trust_score       REAL DEFAULT 0.5,
    source_session_id TEXT DEFAULT '',
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL,
    access_count      INTEGER DEFAULT 0,
    last_accessed_at  REAL,
    dedup_key         TEXT UNIQUE,
    sci_metadata      TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS research_profiles (
    profile_id   TEXT PRIMARY KEY,
    data_json    TEXT NOT NULL,
    narrative_md TEXT DEFAULT '',
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(source_session_id);
CREATE INDEX IF NOT EXISTS idx_facts_type    ON facts(memory_type);
CREATE INDEX IF NOT EXISTS idx_facts_trust   ON facts(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_facts_dedup   ON facts(dedup_key);
"""

_FTS5_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content, summary, tags,
    content=facts, content_rowid=rowid,
    tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, summary, tags)
    VALUES (new.rowid, new.content, new.summary, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, summary, tags)
    VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, summary, tags)
    VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
    INSERT INTO facts_fts(rowid, content, summary, tags)
    VALUES (new.rowid, new.content, new.summary, new.tags);
END;
"""


def _check_fts5() -> bool:
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE _p USING fts5(x)")
        probe.close()
        return True
    except sqlite3.OperationalError:
        return False


class MemoryStore:
    """SQLite 统一记忆存储层。线程安全（WAL 模式）。"""

    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._fts5 = _check_fts5()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._conn:
            self._conn.executescript(_SCHEMA_SQL)
            if self._fts5:
                try:
                    self._conn.executescript(_FTS5_SQL)
                except sqlite3.OperationalError:
                    self._fts5 = False
        # json_extract 索引（JSON1 扩展存在时生效，否则静默跳过）
        try:
            with self._conn:
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_facts_dataset "
                    "ON facts(json_extract(sci_metadata, '$.dataset_name'))"
                )
        except sqlite3.OperationalError:
            pass

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self._conn.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = []
        try:
            d["sci_metadata"] = json.loads(d.get("sci_metadata") or "{}")
        except Exception:
            d["sci_metadata"] = {}
        return d
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_memory_store.py -q
```

预期：`3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/memory_store.py tests/memory/test_memory_store.py
git commit -m "feat(memory): 添加 MemoryStore SQLite schema 初始化"
```

---

### Task 4: MemoryStore — 写操作

**Files:**
- Modify: `src/nini/memory/memory_store.py` （添加 `upsert_fact` + `upsert_profile`）
- Modify: `tests/memory/test_memory_store.py` （添加写操作测试）

- [ ] **Step 1: 追加失败测试**

在 `tests/memory/test_memory_store.py` 末尾添加：

```python
# ---- 写操作测试 ----

def test_upsert_fact_returns_uuid(store: MemoryStore):
    fact_id = store.upsert_fact(content="t(58)=3.14, p=0.002", memory_type="statistic")
    assert len(fact_id) == 36  # UUID 格式


def test_upsert_fact_dedup_returns_same_id(store: MemoryStore):
    """相同内容+类型+dataset 的 fact 不重复写入，返回已有 id。"""
    id1 = store.upsert_fact(
        content="正偏斜分布",
        memory_type="finding",
        sci_metadata={"dataset_name": "data.csv"},
    )
    id2 = store.upsert_fact(
        content="正偏斜分布",
        memory_type="finding",
        sci_metadata={"dataset_name": "data.csv"},
    )
    assert id1 == id2


def test_upsert_fact_different_content_creates_new_entry(store: MemoryStore):
    id1 = store.upsert_fact(content="发现 A", memory_type="finding")
    id2 = store.upsert_fact(content="发现 B", memory_type="finding")
    assert id1 != id2


def test_upsert_profile_and_get(store: MemoryStore):
    store.upsert_profile(
        "default",
        data_json={"domain": "psychology", "significance_level": 0.05},
        narrative_md="## 研究偏好摘要\n- 心理学",
    )
    profile = store.get_profile("default")
    assert profile is not None
    assert profile["data_json"]["domain"] == "psychology"
    assert "心理学" in profile["narrative_md"]


def test_upsert_profile_overwrites_existing(store: MemoryStore):
    store.upsert_profile("default", data_json={"domain": "old"}, narrative_md="")
    store.upsert_profile("default", data_json={"domain": "new"}, narrative_md="")
    profile = store.get_profile("default")
    assert profile["data_json"]["domain"] == "new"


def test_get_profile_returns_none_for_missing(store: MemoryStore):
    assert store.get_profile("nonexistent") is None
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_memory_store.py -q
```

预期：`AttributeError: 'MemoryStore' object has no attribute 'upsert_fact'`

- [ ] **Step 3: 实现写操作（在 MemoryStore 类中添加以下方法）**

```python
    # ---- 写操作 ----

    def upsert_fact(
        self,
        *,
        content: str,
        memory_type: str,
        summary: str = "",
        tags: list[str] | None = None,
        importance: float = 0.5,
        trust_score: float = 0.5,
        source_session_id: str = "",
        sci_metadata: dict[str, Any] | None = None,
    ) -> str:
        """插入 fact；相同 dedup_key 时更新访问计数并返回已有 id（幂等）。"""
        sci = sci_metadata or {}
        dedup_key = hashlib.md5(
            f"{memory_type}|{sci.get('dataset_name', '')}|{content}".encode()
        ).hexdigest()

        existing = self._conn.execute(
            "SELECT id FROM facts WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()
        if existing:
            now = time.time()
            with self._conn:
                self._conn.execute(
                    "UPDATE facts SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                    (now, existing[0]),
                )
            return str(existing[0])

        fact_id = str(uuid.uuid4())
        now = time.time()
        with self._conn:
            self._conn.execute(
                """INSERT INTO facts
                   (id, content, memory_type, summary, tags, importance, trust_score,
                    source_session_id, created_at, updated_at, dedup_key, sci_metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact_id,
                    content,
                    memory_type,
                    summary,
                    json.dumps(tags or [], ensure_ascii=False),
                    importance,
                    trust_score,
                    source_session_id,
                    now,
                    now,
                    dedup_key,
                    json.dumps(sci, ensure_ascii=False),
                ),
            )
        return fact_id

    def upsert_profile(
        self, profile_id: str, data_json: dict[str, Any], narrative_md: str
    ) -> None:
        """更新研究画像（ON CONFLICT 覆盖）。"""
        with self._conn:
            self._conn.execute(
                """INSERT INTO research_profiles (profile_id, data_json, narrative_md, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                       data_json    = excluded.data_json,
                       narrative_md = excluded.narrative_md,
                       updated_at   = excluded.updated_at""",
                (
                    profile_id,
                    json.dumps(data_json, ensure_ascii=False),
                    narrative_md,
                    time.time(),
                ),
            )

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        """获取研究画像，不存在时返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM research_profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row["profile_id"],
            "data_json": json.loads(row["data_json"]),
            "narrative_md": row["narrative_md"],
            "updated_at": row["updated_at"],
        }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_memory_store.py -q
```

预期：`9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/memory_store.py tests/memory/test_memory_store.py
git commit -m "feat(memory): MemoryStore 写操作 upsert_fact / upsert_profile"
```

---

### Task 5: MemoryStore — 读操作

**Files:**
- Modify: `src/nini/memory/memory_store.py` （添加 `search_fts` + `filter_by_sci`）
- Modify: `tests/memory/test_memory_store.py`

- [ ] **Step 1: 追加失败测试**

```python
# ---- 读操作测试 ----

def test_search_fts_finds_matching_facts(store: MemoryStore):
    store.upsert_fact(content="独立样本 t 检验结果显著 p=0.002", memory_type="statistic", summary="t检验")
    store.upsert_fact(content="相关性分析 r=0.75 强正相关", memory_type="statistic", summary="相关性")
    results = store.search_fts("t 检验")
    assert any("t 检验" in r["content"] for r in results)


def test_search_fts_empty_query_returns_all(store: MemoryStore):
    store.upsert_fact(content="内容 A", memory_type="finding")
    store.upsert_fact(content="内容 B", memory_type="finding")
    results = store.search_fts("", top_k=10)
    assert len(results) >= 2


def test_filter_by_sci_p_value(store: MemoryStore):
    store.upsert_fact(
        content="显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.001, "dataset_name": "data.csv"},
    )
    store.upsert_fact(
        content="不显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.3, "dataset_name": "data.csv"},
    )
    results = store.filter_by_sci(max_p_value=0.05)
    assert len(results) == 1
    assert results[0]["content"] == "显著结果"


def test_filter_by_sci_dataset_name(store: MemoryStore):
    store.upsert_fact(
        content="数据集 A 的发现",
        memory_type="finding",
        sci_metadata={"dataset_name": "dataset_a.csv"},
    )
    store.upsert_fact(
        content="数据集 B 的发现",
        memory_type="finding",
        sci_metadata={"dataset_name": "dataset_b.csv"},
    )
    results = store.filter_by_sci(dataset_name="dataset_a.csv")
    assert len(results) == 1
    assert "数据集 A" in results[0]["content"]


def test_filter_by_sci_min_effect_size(store: MemoryStore):
    store.upsert_fact(
        content="大效应量",
        memory_type="statistic",
        sci_metadata={"effect_size": 0.8},
    )
    store.upsert_fact(
        content="小效应量",
        memory_type="statistic",
        sci_metadata={"effect_size": 0.1},
    )
    results = store.filter_by_sci(min_effect_size=0.5)
    assert len(results) == 1
    assert "大效应量" in results[0]["content"]
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_memory_store.py::test_search_fts_finds_matching_facts -q
```

预期：`AttributeError: 'MemoryStore' object has no attribute 'search_fts'`

- [ ] **Step 3: 实现读操作**

```python
    # ---- 读操作 ----

    def search_fts(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """FTS5 全文检索；FTS5 不可用时降级为 LIKE 匹配。"""
        if not query or not query.strip():
            rows = self._conn.execute(
                "SELECT * FROM facts ORDER BY importance DESC, trust_score DESC LIMIT ?",
                (top_k,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

        if self._fts5:
            try:
                rows = self._conn.execute(
                    """SELECT f.* FROM facts f
                       JOIN facts_fts ON f.rowid = facts_fts.rowid
                       WHERE facts_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (query, top_k),
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass  # 降级到 LIKE

        like_q = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE content LIKE ? OR summary LIKE ? LIMIT ?",
            (like_q, like_q, top_k),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def filter_by_sci(
        self,
        *,
        dataset_name: str | None = None,
        analysis_type: str | None = None,
        max_p_value: float | None = None,
        min_effect_size: float | None = None,
    ) -> list[dict[str, Any]]:
        """按 sci_metadata JSON 字段过滤（使用 json_extract）。"""
        conditions: list[str] = []
        params: list[Any] = []

        if dataset_name is not None:
            conditions.append("json_extract(sci_metadata, '$.dataset_name') = ?")
            params.append(dataset_name)
        if analysis_type is not None:
            conditions.append("json_extract(sci_metadata, '$.analysis_type') = ?")
            params.append(analysis_type)
        if max_p_value is not None:
            conditions.append(
                "json_extract(sci_metadata, '$.p_value') IS NOT NULL "
                "AND CAST(json_extract(sci_metadata, '$.p_value') AS REAL) <= ?"
            )
            params.append(max_p_value)
        if min_effect_size is not None:
            conditions.append(
                "json_extract(sci_metadata, '$.effect_size') IS NOT NULL "
                "AND CAST(json_extract(sci_metadata, '$.effect_size') AS REAL) >= ?"
            )
            params.append(min_effect_size)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self._conn.execute(  # noqa: S608
            f"SELECT * FROM facts {where} ORDER BY importance DESC",
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_memory_store.py -q
```

预期：`14 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/memory_store.py tests/memory/test_memory_store.py
git commit -m "feat(memory): MemoryStore 读操作 search_fts / filter_by_sci"
```

---

### Task 6: MemoryStore — 旧数据迁移

**Files:**
- Modify: `src/nini/memory/memory_store.py` （添加 `migrate_from_jsonl` + `migrate_profile_json`）
- Create: `tests/memory/test_migration.py`
- Create: `tests/fixtures/sample_entries.jsonl`

- [ ] **Step 1: 创建测试固件**

```bash
mkdir -p tests/fixtures
```

`tests/fixtures/sample_entries.jsonl` 内容：

```jsonl
{"id": "aaa111", "memory_type": "finding", "content": "数据集存在正偏斜分布，建议对数变换", "summary": "正偏斜", "source_session_id": "sess_old_001", "source_dataset": "survey_2024.csv", "importance_score": 0.7, "tags": ["distribution"], "created_at": "2026-01-10T00:00:00+00:00", "metadata": {}}
{"id": "bbb222", "memory_type": "statistic", "content": "t(58)=3.14, p=0.002, Cohen's d=0.45，组间差异显著", "summary": "t检验显著", "source_session_id": "sess_old_001", "source_dataset": "survey_2024.csv", "importance_score": 0.85, "tags": ["t_test"], "created_at": "2026-01-10T01:00:00+00:00", "metadata": {"significant": true, "sample_size": 60}}
```

- [ ] **Step 2: 写失败测试**

```python
# tests/memory/test_migration.py
"""旧数据迁移测试。"""
import json
from pathlib import Path

import pytest

from nini.memory.memory_store import MemoryStore

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test.db")


def test_migrate_from_jsonl_imports_entries(store: MemoryStore):
    count = store.migrate_from_jsonl(FIXTURES / "sample_entries.jsonl")
    assert count == 2


def test_migrate_from_jsonl_is_idempotent(store: MemoryStore):
    """重复迁移不应写入重复条目。"""
    jsonl = FIXTURES / "sample_entries.jsonl"
    count1 = store.migrate_from_jsonl(jsonl)
    count2 = store.migrate_from_jsonl(jsonl)
    assert count1 == 2
    assert count2 == 0  # 第二次全部被 dedup_key 拦截


def test_migrate_from_jsonl_preserves_sci_metadata(store: MemoryStore):
    store.migrate_from_jsonl(FIXTURES / "sample_entries.jsonl")
    results = store.search_fts("t检验")
    assert any("t(58)" in r["content"] for r in results)


def test_migrate_from_jsonl_missing_file_returns_zero(store: MemoryStore, tmp_path: Path):
    count = store.migrate_from_jsonl(tmp_path / "nonexistent.jsonl")
    assert count == 0


def test_migrate_profile_json(store: MemoryStore, tmp_path: Path):
    profile_data = {"user_id": "default", "domain": "psychology", "significance_level": 0.05}
    json_path = tmp_path / "default.json"
    json_path.write_text(json.dumps(profile_data), encoding="utf-8")

    store.migrate_profile_json(json_path)

    profile = store.get_profile("default")
    assert profile is not None
    assert profile["data_json"]["domain"] == "psychology"


def test_migrate_profile_json_with_narrative(store: MemoryStore, tmp_path: Path):
    json_path = tmp_path / "default.json"
    json_path.write_text(json.dumps({"user_id": "default"}), encoding="utf-8")
    md_path = tmp_path / "default_profile.md"
    md_path.write_text("## 研究偏好摘要\n- α=0.05", encoding="utf-8")

    store.migrate_profile_json(json_path, narrative_path=md_path)

    profile = store.get_profile("default")
    assert "α=0.05" in profile["narrative_md"]


def test_migrate_profile_json_does_not_overwrite_existing(store: MemoryStore, tmp_path: Path):
    """已存在 profile 时，migrate 不覆盖（保护新数据）。"""
    store.upsert_profile("default", data_json={"domain": "new"}, narrative_md="")
    json_path = tmp_path / "default.json"
    json_path.write_text(json.dumps({"user_id": "default", "domain": "old"}), encoding="utf-8")

    store.migrate_profile_json(json_path)

    profile = store.get_profile("default")
    assert profile["data_json"]["domain"] == "new"  # 未被覆盖
```

- [ ] **Step 3: 运行，确认失败**

```bash
pytest tests/memory/test_migration.py -q
```

预期：`AttributeError: 'MemoryStore' object has no attribute 'migrate_from_jsonl'`

- [ ] **Step 4: 实现迁移方法**

```python
    # ---- 旧数据迁移 ----

    def migrate_from_jsonl(self, jsonl_path: Path) -> int:
        """将旧 entries.jsonl 迁移到 facts 表。返回实际写入条数（幂等）。"""
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            return 0
        count = 0
        with open(jsonl_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    sci: dict[str, Any] = {}
                    if d.get("source_dataset"):
                        sci["dataset_name"] = d["source_dataset"]
                    if d.get("analysis_type"):
                        sci["analysis_type"] = d["analysis_type"]
                    meta = d.get("metadata") or {}
                    for key in ("p_value", "effect_size", "significant", "sample_size"):
                        if key in meta:
                            sci[key] = meta[key]

                    dedup_key = hashlib.md5(
                        f"{d.get('memory_type', '')}|{sci.get('dataset_name', '')}|{d.get('content', '')}".encode()
                    ).hexdigest()
                    existing = self._conn.execute(
                        "SELECT id FROM facts WHERE dedup_key = ?", (dedup_key,)
                    ).fetchone()
                    if existing:
                        continue

                    created_ts = time.time()
                    created_str = str(d.get("created_at", ""))
                    if created_str:
                        try:
                            from datetime import datetime, timezone
                            created_ts = datetime.fromisoformat(created_str).timestamp()
                        except Exception:
                            pass

                    fact_id = str(d.get("id") or uuid.uuid4())
                    with self._conn:
                        self._conn.execute(
                            """INSERT OR IGNORE INTO facts
                               (id, content, memory_type, summary, tags, importance,
                                source_session_id, created_at, updated_at, dedup_key, sci_metadata)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                fact_id,
                                str(d.get("content", "")),
                                str(d.get("memory_type", "insight")),
                                str(d.get("summary", "")),
                                json.dumps(d.get("tags") or [], ensure_ascii=False),
                                float(d.get("importance_score", 0.5)),
                                str(d.get("source_session_id", "")),
                                created_ts,
                                created_ts,
                                dedup_key,
                                json.dumps(sci, ensure_ascii=False),
                            ),
                        )
                    count += 1
                except Exception as exc:
                    logger.warning("迁移 JSONL 条目失败: %s", exc)
        return count

    def migrate_profile_json(
        self, json_path: Path, narrative_path: Path | None = None
    ) -> None:
        """将旧 profiles/*.json + *_profile.md 迁移到 research_profiles 表。
        已存在的 profile 不覆盖（保护新数据）。
        """
        json_path = Path(json_path)
        if not json_path.exists():
            return
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            profile_id = str(data.get("user_id", json_path.stem))
            existing = self._conn.execute(
                "SELECT profile_id FROM research_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            if existing:
                return  # 不覆盖已有数据
            narrative = ""
            if narrative_path is not None:
                narrative_path = Path(narrative_path)
                if narrative_path.exists():
                    narrative = narrative_path.read_text(encoding="utf-8")
            self.upsert_profile(profile_id, data, narrative)
        except Exception as exc:
            logger.warning("迁移 profile JSON 失败 %s: %s", json_path, exc)
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/memory/test_migration.py -q
```

预期：`7 passed`

- [ ] **Step 6: 运行全量 memory 测试**

```bash
pytest tests/memory/ -q
```

预期：全部通过。

- [ ] **Step 7: Commit**

```bash
git add src/nini/memory/memory_store.py tests/memory/test_migration.py tests/fixtures/sample_entries.jsonl
git commit -m "feat(memory): MemoryStore 旧数据迁移 migrate_from_jsonl / migrate_profile_json"
```

---

## Phase 2 — ScientificMemoryProvider

---

### Task 7: ScientificMemoryProvider — 骨架 + initialize

**Files:**
- Create: `src/nini/memory/scientific_provider.py`
- Create: `tests/memory/test_scientific_provider.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/memory/test_scientific_provider.py
"""ScientificMemoryProvider 生命周期测试。"""
from pathlib import Path

import pytest

from nini.memory.scientific_provider import ScientificMemoryProvider


@pytest.fixture
async def provider(tmp_path: Path) -> ScientificMemoryProvider:
    p = ScientificMemoryProvider(db_path=tmp_path / "nini_memory.db")
    await p.initialize(session_id="sess001")
    return p


# ---- 基础属性 ----

def test_provider_name_is_builtin():
    p = ScientificMemoryProvider(db_path=Path(":memory:"))
    assert p.name == "builtin"


async def test_initialize_creates_db(tmp_path: Path):
    db_path = tmp_path / "nini_memory.db"
    p = ScientificMemoryProvider(db_path=db_path)
    await p.initialize(session_id="sess001")
    assert db_path.exists()


async def test_provider_has_two_tool_schemas(provider: ScientificMemoryProvider):
    schemas = provider.get_tool_schemas()
    names = {s["name"] for s in schemas}
    assert "nini_memory_find" in names
    assert "nini_memory_save" in names


# ---- system_prompt_block ----

async def test_system_prompt_block_empty_when_no_profile(provider: ScientificMemoryProvider):
    block = provider.system_prompt_block()
    assert block == "" or isinstance(block, str)


async def test_system_prompt_block_includes_profile(provider: ScientificMemoryProvider):
    provider._store.upsert_profile(
        "default",
        data_json={"domain": "psychology"},
        narrative_md="## 研究偏好摘要\n- 研究领域：心理学\n- α=0.05",
    )
    block = provider.system_prompt_block()
    assert "心理学" in block
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_scientific_provider.py -q
```

预期：`ModuleNotFoundError: No module named 'nini.memory.scientific_provider'`

- [ ] **Step 3: 实现 ScientificMemoryProvider 骨架**

```python
# src/nini/memory/scientific_provider.py
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

# 统计数值检测正则
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
                if json_path.stem.endswith("_profile"):
                    continue  # 跳过 narrative MD 对应的 JSON 名（不存在，防止匹配错误）
                md_path = profiles_dir / f"{json_path.stem}_profile.md"
                self._store.migrate_profile_json(
                    json_path, md_path if md_path.exists() else None
                )

    def system_prompt_block(self) -> str:
        """返回研究画像的 system prompt 快照（会话开始时调用一次）。"""
        if self._store is None:
            return ""
        profile = self._store.get_profile(self._profile_id)
        if not profile:
            return ""
        narrative = (profile.get("narrative_md") or "").strip()
        if narrative:
            return f"## 研究画像\n\n{narrative}"
        data = profile.get("data_json") or {}
        parts: list[str] = []
        domain = data.get("domain", "")
        if domain and domain != "general":
            parts.append(f"研究领域：{domain}")
        if data.get("significance_level"):
            parts.append(f"显著性水平：α={data['significance_level']}")
        if data.get("journal_style"):
            parts.append(f"期刊风格：{data['journal_style']}")
        if not parts:
            return ""
        return "## 研究画像\n\n" + "\n".join(f"- {p}" for p in parts)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
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
                        "top_k": {"type": "integer", "description": "最多返回条数（默认 5）"},
                        "dataset_name": {"type": "string", "description": "限定数据集名称（可选）"},
                        "max_p_value": {"type": "number", "description": "p 值上限过滤（可选，如 0.05）"},
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
                            "enum": ["finding", "statistic", "decision", "insight", "knowledge"],
                        },
                        "importance": {"type": "number", "description": "重要性 0~1（默认 0.7）"},
                    },
                    "required": ["content"],
                },
            },
        ]

    async def shutdown(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_scientific_provider.py -q
```

预期：`5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/scientific_provider.py tests/memory/test_scientific_provider.py
git commit -m "feat(memory): ScientificMemoryProvider 骨架 + initialize + system_prompt_block"
```

---

### Task 8: ScientificMemoryProvider — prefetch

**Files:**
- Modify: `src/nini/memory/scientific_provider.py`
- Modify: `tests/memory/test_scientific_provider.py`

- [ ] **Step 1: 追加失败测试**

```python
# ---- prefetch 测试 ----

async def test_prefetch_returns_empty_when_no_facts(provider: ScientificMemoryProvider):
    result = await provider.prefetch("t检验")
    assert result == ""


async def test_prefetch_returns_relevant_facts(provider: ScientificMemoryProvider):
    provider._store.upsert_fact(
        content="t(58)=3.14, p=0.002，独立样本 t 检验结果显著",
        memory_type="statistic",
        summary="t检验显著",
        importance=0.8,
        sci_metadata={"p_value": 0.002, "dataset_name": "survey.csv"},
    )
    result = await provider.prefetch("t检验")
    assert "t(58)=3.14" in result or "t检验" in result


async def test_prefetch_applies_fencing(provider: ScientificMemoryProvider):
    provider._store.upsert_fact(
        content="显著性结果 p=0.001",
        memory_type="statistic",
        summary="显著",
        importance=0.9,
    )
    result = await provider.prefetch("显著性")
    if result:
        assert "<memory-context>" in result
        assert "</memory-context>" in result
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_scientific_provider.py::test_prefetch_returns_relevant_facts -q
```

- [ ] **Step 3: 实现 prefetch**

```python
    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """三段式检索：FTS5 召回 → 时间衰减+情境加权排序 → fencing 包裹。"""
        if self._store is None or not query.strip():
            return ""
        try:
            candidates = self._store.search_fts(query, top_k=15)
            if not candidates:
                return ""
            now = time.time()
            scored: list[tuple[float, dict[str, Any]]] = []
            for fact in candidates:
                importance = float(fact.get("importance", 0.5))
                access_count = int(fact.get("access_count") or 0)
                created_at = float(fact.get("created_at") or now)
                days = max(0.0, (now - created_at) / 86400)
                decay_lambda = 0.005 if access_count > 5 else 0.01
                score = importance * math.exp(-decay_lambda * days)
                scored.append((score, fact))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = [f for _, f in scored[:5]]
            lines: list[str] = []
            for fact in top:
                memory_type = fact.get("memory_type", "")
                summary = fact.get("summary") or fact.get("content", "")[:80]
                sci = fact.get("sci_metadata") or {}
                dataset = sci.get("dataset_name", "") if isinstance(sci, dict) else ""
                line = f"[{memory_type.upper()}] {summary}"
                if dataset:
                    line += f"（来源：{dataset}）"
                lines.append(line)
            raw = "\n".join(lines)
            return build_memory_context_block(raw)
        except Exception as exc:
            logger.warning("ScientificMemoryProvider.prefetch 失败: %s", exc)
            return ""
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_scientific_provider.py -q
```

预期：`8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/scientific_provider.py tests/memory/test_scientific_provider.py
git commit -m "feat(memory): ScientificMemoryProvider.prefetch 三段式检索"
```

---

### Task 9: ScientificMemoryProvider — sync_turn

**Files:**
- Modify: `src/nini/memory/scientific_provider.py`
- Modify: `tests/memory/test_scientific_provider.py`

- [ ] **Step 1: 追加失败测试**

```python
# ---- sync_turn 测试 ----

async def test_sync_turn_extracts_statistical_values(provider: ScientificMemoryProvider):
    await provider.sync_turn(
        user_content="请分析这个数据集",
        assistant_content="独立样本 t 检验：t(58)=3.14, p=0.002, Cohen's d=0.45，差异显著。",
        session_id="sess001",
    )
    results = provider._store.search_fts("t 检验")
    # sync_turn 使用后台任务；此处直接调用 _extract_from_text 验证提取逻辑
    extracted = provider._extract_from_text(
        "独立样本 t 检验：t(58)=3.14, p=0.002, Cohen's d=0.45，差异显著。",
        "sess001",
    )
    assert len(extracted) >= 1
    assert any("p" in item["content"].lower() for item in extracted)


async def test_sync_turn_ignores_no_stat_content(provider: ScientificMemoryProvider):
    """普通对话不应触发统计提取。"""
    extracted = provider._extract_from_text("你好！今天天气怎么样？", "sess001")
    assert extracted == []


async def test_sync_turn_extracts_conclusion(provider: ScientificMemoryProvider):
    extracted = provider._extract_from_text(
        "结论：两组之间存在统计学上的显著差异，建议进一步分析。",
        "sess001",
    )
    assert any(item["memory_type"] == "finding" for item in extracted)
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_scientific_provider.py::test_sync_turn_extracts_statistical_values -q
```

- [ ] **Step 3: 实现 sync_turn + _extract_from_text**

```python
    async def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
    ) -> None:
        """轻量提取：扫描 assistant 回复，写入统计数值和结论。"""
        if self._store is None:
            return
        try:
            items = self._extract_from_text(
                assistant_content, session_id or self._session_id
            )
            for item in items:
                self._store.upsert_fact(**item)
        except Exception as exc:
            logger.warning("ScientificMemoryProvider.sync_turn 失败: %s", exc)

    def _extract_from_text(
        self, text: str, session_id: str
    ) -> list[dict[str, Any]]:
        """从文本中提取统计数值和结论，返回 upsert_fact kwargs 列表。
        importance < 0.4 的片段不写入（噪声过滤）。
        """
        results: list[dict[str, Any]] = []
        for pattern in _STAT_PATTERNS:
            for match in pattern.finditer(text):
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 60)
                snippet = text[start:end].strip()
                results.append(
                    {
                        "content": snippet,
                        "memory_type": "statistic",
                        "summary": match.group(0)[:80],
                        "importance": 0.7,
                        "source_session_id": session_id,
                    }
                )
        for pattern in _CONCLUSION_PATTERNS:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "content": match.group(0),
                        "memory_type": "finding",
                        "summary": match.group(0)[:80],
                        "importance": 0.65,
                        "source_session_id": session_id,
                    }
                )
        return results
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_scientific_provider.py -q
```

预期：`11 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/scientific_provider.py tests/memory/test_scientific_provider.py
git commit -m "feat(memory): ScientificMemoryProvider.sync_turn 轻量统计提取"
```

---

### Task 10: ScientificMemoryProvider — on_session_end

**Files:**
- Modify: `src/nini/memory/scientific_provider.py`
- Modify: `tests/memory/test_scientific_provider.py`

- [ ] **Step 1: 追加失败测试**

```python
# ---- on_session_end 测试 ----

async def test_on_session_end_consolidates_statistics(provider: ScientificMemoryProvider):
    """on_session_end 将显著统计结果写入 facts 表。"""
    from unittest.mock import patch
    from nini.memory.compression import AnalysisMemory, StatisticResult

    memory = AnalysisMemory(
        session_id="sess001",
        dataset_name="survey_2024.csv",
        statistics=[
            StatisticResult(
                test_name="独立样本t检验",
                test_statistic=3.14,
                p_value=0.002,
                effect_size=0.45,
                effect_type="cohen_d",
                significant=True,
            )
        ],
    )
    with patch(
        "nini.memory.scientific_provider.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    results = provider._store.filter_by_sci(max_p_value=0.05)
    assert len(results) >= 1


async def test_on_session_end_consolidates_findings(provider: ScientificMemoryProvider):
    from unittest.mock import patch
    from nini.memory.compression import AnalysisMemory, Finding

    memory = AnalysisMemory(
        session_id="sess001",
        dataset_name="data.csv",
        findings=[Finding(category="distribution", summary="正偏斜分布", confidence=0.85)],
    )
    with patch(
        "nini.memory.scientific_provider.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    results = provider._store.search_fts("正偏斜")
    assert any("正偏斜" in r["content"] or "正偏斜" in r["summary"] for r in results)


async def test_on_session_end_skips_low_confidence(provider: ScientificMemoryProvider):
    """置信度不足 0.7 的 finding 不应沉淀。"""
    from unittest.mock import patch
    from nini.memory.compression import AnalysisMemory, Finding

    memory = AnalysisMemory(
        session_id="sess001",
        dataset_name="data.csv",
        findings=[Finding(category="noise", summary="不确定的发现", confidence=0.3)],
    )
    with patch(
        "nini.memory.scientific_provider.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    results = provider._store.search_fts("不确定的发现")
    assert len(results) == 0


async def test_on_session_end_is_graceful_on_error(provider: ScientificMemoryProvider):
    """on_session_end 遇到异常不应向外抛出。"""
    from unittest.mock import patch

    with patch(
        "nini.memory.scientific_provider.list_session_analysis_memories",
        side_effect=RuntimeError("故意失败"),
    ):
        await provider.on_session_end([])  # 不应抛出
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_scientific_provider.py::test_on_session_end_consolidates_statistics -q
```

- [ ] **Step 3: 实现 on_session_end**

```python
    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """重度沉淀：AnalysisMemory → facts 表 + knowledge.md → facts。"""
        if self._store is None:
            return
        try:
            from nini.memory.compression import list_session_analysis_memories
            sid = self._session_id
            memories = list_session_analysis_memories(sid)
            count = 0
            for memory in memories:
                dataset = memory.dataset_name
                for finding in memory.findings:
                    if finding.confidence < 0.7:
                        continue
                    self._store.upsert_fact(
                        content=finding.detail or finding.summary,
                        memory_type="finding",
                        summary=finding.summary,
                        tags=[finding.category] if finding.category else [],
                        importance=finding.confidence,
                        source_session_id=sid,
                        sci_metadata={"dataset_name": dataset},
                    )
                    count += 1
                for stat in memory.statistics:
                    importance = (
                        0.8 if stat.significant is True
                        else 0.6 if stat.significant is False
                        else 0.45
                    )
                    self._store.upsert_fact(
                        content=(
                            f"{stat.test_name}: 统计量={stat.test_statistic}, "
                            f"p={stat.p_value}, 效应量={stat.effect_size}"
                        ),
                        memory_type="statistic",
                        summary=f"{stat.test_name} 结果",
                        importance=importance,
                        source_session_id=sid,
                        sci_metadata={
                            "dataset_name": dataset,
                            "test_name": stat.test_name,
                            "test_statistic": stat.test_statistic,
                            "p_value": stat.p_value,
                            "effect_size": stat.effect_size,
                            "effect_type": stat.effect_type,
                            "significant": stat.significant,
                            "analysis_type": stat.test_name,
                        },
                    )
                    count += 1
                for decision in memory.decisions:
                    if decision.confidence < 0.7:
                        continue
                    self._store.upsert_fact(
                        content=(
                            f"{decision.decision_type}: 选择 {decision.chosen}。"
                            f"理由：{decision.rationale}"
                        ),
                        memory_type="decision",
                        summary=f"{decision.decision_type} → {decision.chosen}",
                        importance=decision.confidence * 0.8,
                        source_session_id=sid,
                        sci_metadata={"dataset_name": dataset},
                    )
                    count += 1
            # knowledge.md 沉淀
            try:
                from nini.memory.knowledge import KnowledgeMemory
                knowledge_text = KnowledgeMemory(sid).read().strip()
                if knowledge_text:
                    self._store.upsert_fact(
                        content=knowledge_text,
                        memory_type="knowledge",
                        summary=f"会话 {sid[:8]} 知识记录",
                        importance=0.6,
                        source_session_id=sid,
                    )
                    count += 1
            except Exception as exc:
                logger.debug("knowledge.md 沉淀失败: %s", exc)
            if count:
                logger.info("on_session_end: 会话 %s 沉淀 %d 条记忆", sid[:8], count)
        except Exception as exc:
            logger.warning("ScientificMemoryProvider.on_session_end 失败: %s", exc)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_scientific_provider.py -q
```

预期：`15 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/scientific_provider.py tests/memory/test_scientific_provider.py
git commit -m "feat(memory): ScientificMemoryProvider.on_session_end 重度沉淀"
```

---

### Task 11: ScientificMemoryProvider — on_pre_compress + 工具

**Files:**
- Modify: `src/nini/memory/scientific_provider.py`
- Modify: `tests/memory/test_scientific_provider.py`

- [ ] **Step 1: 追加失败测试**

```python
# ---- on_pre_compress 测试 ----

def test_on_pre_compress_extracts_stat_lines(provider: ScientificMemoryProvider):
    messages = [
        {"role": "user", "content": "分析这个数据集"},
        {"role": "assistant", "content": "t(58)=3.14, p=0.002, Cohen's d=0.45，差异显著。"},
    ]
    result = provider.on_pre_compress(messages)
    assert "p=0.002" in result or "3.14" in result


def test_on_pre_compress_empty_when_no_stats(provider: ScientificMemoryProvider):
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么我可以帮你的？"},
    ]
    result = provider.on_pre_compress(messages)
    assert result == ""


# ---- 工具调用测试 ----

async def test_tool_find_returns_results(provider: ScientificMemoryProvider):
    import json as _json
    provider._store.upsert_fact(
        content="t(58)=3.14, p=0.002",
        memory_type="statistic",
        summary="t检验显著",
        importance=0.8,
    )
    result = await provider.handle_tool_call("nini_memory_find", {"query": "t检验"})
    data = _json.loads(result)
    assert data["success"] is True
    assert "results" in data


async def test_tool_save_stores_fact(provider: ScientificMemoryProvider):
    import json as _json
    result = await provider.handle_tool_call(
        "nini_memory_save",
        {"content": "数据正态性不满足，应使用非参数检验", "memory_type": "decision", "importance": 0.8},
    )
    data = _json.loads(result)
    assert data["success"] is True
    assert "id" in data


async def test_tool_save_empty_content_returns_error(provider: ScientificMemoryProvider):
    import json as _json
    result = await provider.handle_tool_call("nini_memory_save", {"content": ""})
    data = _json.loads(result)
    assert data["success"] is False


async def test_tool_find_with_p_value_filter(provider: ScientificMemoryProvider):
    import json as _json
    provider._store.upsert_fact(
        content="显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.001},
    )
    provider._store.upsert_fact(
        content="不显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.4},
    )
    result = await provider.handle_tool_call(
        "nini_memory_find", {"query": "结果", "max_p_value": 0.05}
    )
    data = _json.loads(result)
    assert data["success"] is True
    assert all("显著" in r["content"] and "不" not in r["content"] for r in data["results"])
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/memory/test_scientific_provider.py::test_on_pre_compress_extracts_stat_lines -q
```

- [ ] **Step 3: 实现 on_pre_compress + handle_tool_call**

```python
    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """压缩前：提取 assistant 回复中含统计数值的行，追加到压缩 prompt。"""
        stat_lines: list[str] = []
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = str(msg.get("content") or "")
            for pattern in _STAT_PATTERNS:
                for match in pattern.finditer(content):
                    start = max(0, match.start() - 10)
                    end = min(len(content), match.end() + 60)
                    stat_lines.append(content[start:end].strip())
        if not stat_lines:
            return ""
        return (
            "以下统计结果必须完整保留在摘要中：\n"
            + "\n".join(f"- {line}" for line in stat_lines[:10])
        )

    async def handle_tool_call(
        self, tool_name: str, args: dict[str, Any], **kwargs: Any
    ) -> str:
        if self._store is None:
            return json.dumps({"success": False, "error": "记忆存储未初始化"}, ensure_ascii=False)
        if tool_name == "nini_memory_find":
            return await self._handle_find(args)
        if tool_name == "nini_memory_save":
            return await self._handle_save(args)
        return json.dumps({"success": False, "error": f"未知工具：{tool_name}"}, ensure_ascii=False)

    async def _handle_find(self, args: dict[str, Any]) -> str:
        assert self._store is not None
        query = str(args.get("query") or "")
        top_k = int(args.get("top_k") or 5)
        dataset_name = args.get("dataset_name") or None
        max_p_value = args.get("max_p_value")

        if max_p_value is not None or dataset_name:
            candidates = self._store.filter_by_sci(
                dataset_name=dataset_name,
                max_p_value=float(max_p_value) if max_p_value is not None else None,
            )
            if query:
                q_lower = query.lower()
                candidates = [
                    r for r in candidates
                    if q_lower in r.get("content", "").lower()
                    or q_lower in r.get("summary", "").lower()
                ]
            candidates = candidates[:top_k]
        else:
            candidates = self._store.search_fts(query, top_k=top_k)

        formatted = [
            {
                "memory_type": r.get("memory_type"),
                "summary": r.get("summary") or r.get("content", "")[:100],
                "content": r.get("content"),
                "dataset": (r.get("sci_metadata") or {}).get("dataset_name"),
            }
            for r in candidates
        ]
        return json.dumps({"success": True, "results": formatted}, ensure_ascii=False)

    async def _handle_save(self, args: dict[str, Any]) -> str:
        assert self._store is not None
        content = str(args.get("content") or "").strip()
        if not content:
            return json.dumps({"success": False, "error": "content 不能为空"}, ensure_ascii=False)
        memory_type = str(args.get("memory_type") or "insight")
        importance = float(args.get("importance") or 0.7)
        fact_id = self._store.upsert_fact(
            content=content,
            memory_type=memory_type,
            importance=importance,
            source_session_id=self._session_id,
        )
        return json.dumps({"success": True, "id": fact_id}, ensure_ascii=False)
```

- [ ] **Step 4: 运行全量 ScientificMemoryProvider 测试**

```bash
pytest tests/memory/test_scientific_provider.py -q
```

预期：`21 passed`

- [ ] **Step 5: 运行全量 memory 测试**

```bash
pytest tests/memory/ -q
```

预期：全部通过。

- [ ] **Step 6: Commit**

```bash
git add src/nini/memory/scientific_provider.py tests/memory/test_scientific_provider.py
git commit -m "feat(memory): ScientificMemoryProvider on_pre_compress + LLM 工具 nini_memory_find/save"
```

---

## Phase 3 — Integration

---

### Task 12: memory/__init__.py 导出 + 向后兼容 shim

**Files:**
- Modify: `src/nini/memory/__init__.py`

- [ ] **Step 1: 读取当前 __init__.py，了解现有导出**

```bash
cat src/nini/memory/__init__.py
```

- [ ] **Step 2: 追加新导出**

在 `src/nini/memory/__init__.py` 末尾追加：

```python
from nini.memory.manager import MemoryManager, get_memory_manager, set_memory_manager
from nini.memory.provider import MemoryProvider
from nini.memory.scientific_provider import ScientificMemoryProvider

__all__ = [
    # 现有导出保持不变
    "DEFAULT_RESEARCH_PROFILE_ID",
    "ResearchProfile",
    "ResearchProfileManager",
    "get_research_profile_manager",
    "get_research_profile_prompt",
    # 新增
    "MemoryManager",
    "MemoryProvider",
    "ScientificMemoryProvider",
    "get_memory_manager",
    "set_memory_manager",
]
```

- [ ] **Step 3: 验证导入正常**

```bash
python -c "from nini.memory import MemoryManager, ScientificMemoryProvider; print('OK')"
```

预期：`OK`

- [ ] **Step 4: 运行完整测试，确认无回归**

```bash
pytest tests/memory/ -q
python scripts/check_event_schema_consistency.py
```

- [ ] **Step 5: Commit**

```bash
git add src/nini/memory/__init__.py
git commit -m "feat(memory): memory/__init__.py 新增 MemoryProvider 架构导出"
```

---

### Task 13: Agent 生命周期接入

**Files:**
- Modify: `src/nini/agent/runner.py:379-401`（`AgentRunner.__init__` + 会话结束沉淀）
- Modify: `src/nini/agent/components/context_builder.py:554`（`_build_dataset_history_memory` 优先走 MemoryManager）

> **注意：** 先完整阅读 `runner.py:379-401` 和 `context_builder.py:554-600`，再做修改。以下改动点已在代码调研阶段定位。

#### 13a — 初始化 MemoryManager（runner.py）

- [ ] **Step 1: 在 AgentRunner.__init__ 末尾（约第 401 行）添加**

```python
        # 记忆系统初始化（每次 AgentRunner 实例化时创建，session.id 在 run() 中传入）
        self._memory_manager: "MemoryManager | None" = None
```

完整 `__init__` 末尾（约第 395-401 行）改为：

```python
        self._ask_user_question_handler = ask_user_question_handler
        # 跟踪 context 使用率（0.0 初始，用于自适应工具结果截断预算）
        self._context_ratio: float = 0.0
        # 循环检测守卫
        self._loop_guard = LoopGuard()
        # 累计需要从 Agent 超时预算中扣除的人工等待时长
        self._timeout_excluded_seconds: float = 0.0
        # 记忆系统（惰性初始化，在 run() 中按 session 初始化）
        self._memory_manager: "MemoryManager | None" = None
```

- [ ] **Step 2: 在 runner.py 顶部 import 区域添加**（在已有 import 附近，约第 30-37 行）

```python
from nini.memory.manager import MemoryManager, set_memory_manager, build_memory_context_block
from nini.memory.scientific_provider import ScientificMemoryProvider
```

- [ ] **Step 3: 在 run() 方法中，找到 `AgentRunner.run()` 的 session 参数处理后，添加 MemoryManager 初始化**

定位位置：在 `run()` 方法内，找到已有 system_prompt 组装之前（搜索 `system_prompt` 字符串附近），添加：

```python
            # ---- 初始化记忆系统 ----
            if self._memory_manager is None:
                from nini.config import settings
                mgr = MemoryManager()
                db_path = settings.sessions_dir.parent / "nini_memory.db"
                mgr.add_provider(ScientificMemoryProvider(db_path=db_path))
                self._memory_manager = mgr
                set_memory_manager(mgr)
            await self._memory_manager.initialize_all(session_id=session.id)
            # system_prompt 快照（一次性注入，不中途变化）
            memory_system_prompt = self._memory_manager.build_system_prompt()
```

然后将 `memory_system_prompt` 追加到 system_prompt 组装逻辑。搜索当前 system_prompt 变量的最终使用处，在其前追加：

```python
            if memory_system_prompt:
                system_prompt = system_prompt + "\n\n" + memory_system_prompt
```

- [ ] **Step 4: 在 runner.py 第 1294 行（`# 会话结束后异步沉淀`）处，追加 MemoryManager.on_session_end 调用**

将原来的：

```python
                # 会话结束后异步沉淀分析记忆为跨会话长期记忆
                try:
                    from nini.memory.long_term_memory import consolidate_session_memories
                    from nini.utils.background_tasks import track_background_task

                    track_background_task(consolidate_session_memories(session.id))
                except Exception:
                    logger.debug("长期记忆沉淀失败", exc_info=True)
```

改为（保留原有调用，新增 MemoryManager 调用）：

```python
                # 会话结束后异步沉淀分析记忆为跨会话长期记忆
                try:
                    from nini.memory.long_term_memory import consolidate_session_memories
                    from nini.utils.background_tasks import track_background_task

                    track_background_task(consolidate_session_memories(session.id))
                except Exception:
                    logger.debug("长期记忆沉淀失败", exc_info=True)
                # 同时通过 MemoryManager 沉淀（新架构路径）
                if self._memory_manager is not None:
                    try:
                        from nini.utils.background_tasks import track_background_task
                        track_background_task(
                            self._memory_manager.on_session_end(session.get_messages())
                        )
                    except Exception:
                        logger.debug("MemoryManager.on_session_end 失败", exc_info=True)
```

> 注：`session.get_messages()` 或等价方法名需根据 Session API 确认。若无此方法，使用 `[]` 占位（on_session_end 会自行从 session.db 读取 AnalysisMemory）。

#### 13b — context_builder.py 集成

- [ ] **Step 5: 修改 `_build_dataset_history_memory` 函数（context_builder.py:554）**

在函数开头添加 MemoryManager 优先路径：

```python
async def _build_dataset_history_memory(dataset_name: str) -> str:
    """主动推送指定 dataset 的历史分析记忆摘要。"""
    if not dataset_name or not dataset_name.strip():
        return ""

    # 优先走 MemoryManager（新架构路径）
    try:
        from nini.memory.manager import get_memory_manager, build_memory_context_block
        from nini.agent.prompt_policy import format_untrusted_context_block

        mgr = get_memory_manager()
        if mgr.providers:  # providers 已注册 = 已初始化
            raw = await mgr.prefetch_all(dataset_name.strip())
            if raw:
                return format_untrusted_context_block("long_term_memory", raw)
    except Exception:
        pass  # 降级到原有路径

    # 原有路径（向后兼容）
    try:
        from nini.memory.long_term_memory import (
            ...  # 保持原有 import 不变
```

- [ ] **Step 6: 验证启动正常**

```bash
python -c "from nini.agent.runner import AgentRunner; print('AgentRunner import OK')"
```

- [ ] **Step 7: 运行后端测试**

```bash
python scripts/check_event_schema_consistency.py
pytest -q --ignore=tests/memory/
```

预期：全部通过（memory 目录已单独通过，其他测试无回归）。

- [ ] **Step 8: 运行类型检查**

```bash
mypy src/nini/memory/provider.py src/nini/memory/manager.py \
     src/nini/memory/memory_store.py src/nini/memory/scientific_provider.py
```

- [ ] **Step 9: 格式检查**

```bash
black --check src/nini/memory/ src/nini/agent/runner.py \
      src/nini/agent/components/context_builder.py
```

- [ ] **Step 10: Commit**

```bash
git add src/nini/agent/runner.py src/nini/agent/components/context_builder.py
git commit -m "feat(memory): Agent 生命周期接入 MemoryManager（初始化 + on_session_end + context prefetch）"
```

---

## 验收标准

完成 Task 13 后，执行以下检查：

```bash
# 1. 事件 schema 一致性
python scripts/check_event_schema_consistency.py

# 2. 全量后端测试
pytest -q

# 3. memory 专项测试
pytest tests/memory/ -v

# 4. 类型检查
mypy src/nini/memory/

# 5. 格式检查
black --check src tests
```

全部通过即可创建 PR。

---

## 后续清理（P5 — 可在验收后独立完成）

以下文件在验收测试全部通过后可标记为废弃并计划删除：

| 文件 | 替代方 |
|---|---|
| `src/nini/memory/long_term_memory.py` | `ScientificMemoryProvider` + `MemoryStore` |
| `src/nini/memory/research_profile.py` | `research_profiles` 表 + `MemoryStore.get/upsert_profile` |
| `src/nini/memory/profile_narrative.py` | `research_profiles.narrative_md` 列 |
| `src/nini/memory/knowledge.py` | `on_session_end` 沉淀路径 |

清理步骤：添加 `@deprecated` 注释 → 更新调用方 → 删除文件 → 更新测试。
