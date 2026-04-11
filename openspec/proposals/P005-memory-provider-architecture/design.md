# P005：记忆系统架构重构 — MemoryProvider 抽象层

> 提案编号：P005  
> 版本：v1.0  
> 日期：2026-04-12  
> 状态：已批准，待实施  
> 分支：`feature/memory-provider-architecture`

---

## 1. 背景与动机

nini 现有记忆系统由 5 个相互独立的组件构成，持久化格式混杂：

| 组件 | 存储格式 | 问题 |
|---|---|---|
| `LongTermMemoryStore` | JSONL（`long_term_memory/entries.jsonl`） | 无事务，无 SQL 查询，科研数值无法按条件过滤 |
| `ResearchProfileManager` | JSON（`profiles/*.json`） | 与 Markdown 双写冗余 |
| `ProfileNarrativeManager` | Markdown（`*_profile.md`） | 与 JSON 双写冗余 |
| `KnowledgeMemory` | Markdown（`sessions/*/knowledge.md`） | 单会话，无跨会话检索 |
| `session.db` | SQLite（`sessions/{id}/session.db`） | 仅存会话历史，无科研发现层 |

核心问题：所有会话分析发现（统计结果、方法决策、数据集洞察）在会话结束后存入 JSONL，无法事务安全地查询，也无法通过 SQL 精确过滤（如 `p_value < 0.05`），这对科研数据分析这类要求严谨的任务是无法接受的。

hermes-agent 项目（NousResearch/hermes-agent）的 `MemoryProvider` 抽象 + `MemoryManager` 编排模式解决了上述问题，且其 holographic 插件的 SQLite + FTS5 设计满足「所有会话记忆持久化到数据库」的核心诉求。

---

## 2. 目标

- 引入 `MemoryProvider` ABC 和 `MemoryManager`，对齐 hermes-agent 架构
- 将 `LongTermMemoryStore` 的 JSONL 迁移到 SQLite，提供事务安全、FTS5 全文检索、`json_extract()` 精确过滤
- 将研究画像的 JSON + Markdown 双存储统一为 `research_profiles` 表
- 接入完整生命周期钩子：每轮（`sync_turn`）、会话结束（`on_session_end`）、压缩前（`on_pre_compress`）
- 主路径记忆检索（`build_long_term_memory_context`）和数据集专用路径（`_build_dataset_history_memory`）均切换为 `MemoryManager.prefetch_all()`
- 向后兼容：过渡期保留 `LongTermMemoryStore`、`ResearchProfileManager` 公共接口

---

## 3. 非目标

- 接入 hermes 的外部 memory provider 插件（Honcho、Mem0 等）——架构预留槽位，本次不实现
- 修改 `session.db` 现有 schema（`messages` / `session_meta` / `archived_messages` 表不变）
- 向量索引迁移（`VectorKnowledgeStore` 保持不变）
- 前端改动（无用户可见界面变化）
- P5 废弃清理（旧文件标记后单独 PR 删除）

---

## 4. 架构概览

```
MemoryManager                             ← 编排层（对齐 hermes）
  └── ScientificMemoryProvider            ← nini 唯一内置 provider（name="builtin"）
        └── MemoryStore
              └── data/nini_memory.db (SQLite, WAL)
                    ├── facts             ← 通用记忆层 + sci_metadata JSON 列
                    ├── facts_fts         ← FTS5 全文索引（自动触发器维护）
                    └── research_profiles ← 研究画像（JSON + Markdown 合一）

data/sessions/{id}/session.db             ← 会话历史（不变）
```

**预留扩展槽**：`MemoryManager` 支持注册最多 1 个外部 provider，内置 provider 不可移除。

---

## 5. 文件变更清单

### 5.1 新增（4 个源文件 + 测试）

| 文件 | 职责 |
|---|---|
| `src/nini/memory/provider.py` | `MemoryProvider` ABC，定义生命周期接口 |
| `src/nini/memory/manager.py` | `MemoryManager`，编排所有 provider；`build_memory_context_block` fencing 工具 |
| `src/nini/memory/scientific_provider.py` | `ScientificMemoryProvider`（`name="builtin"`） |
| `src/nini/memory/memory_store.py` | SQLite 存储操作层，被 provider 使用 |
| `tests/memory/__init__.py` | 测试包 |
| `tests/memory/test_memory_provider.py` | ABC 测试 |
| `tests/memory/test_memory_manager.py` | 编排层测试（隔离、工具路由、fencing） |
| `tests/memory/test_memory_store.py` | SQLite 存储测试 |
| `tests/memory/test_migration.py` | JSONL → SQLite 迁移正确性测试 |
| `tests/memory/test_scientific_provider.py` | ScientificMemoryProvider 生命周期测试 |
| `tests/fixtures/sample_entries.jsonl` | 迁移测试固件（2 条 JSONL 样本） |

### 5.2 改动（4 个）

| 文件 | 改动内容 |
|---|---|
| `src/nini/memory/__init__.py` | 新增导出 `MemoryManager` / `MemoryProvider` / `ScientificMemoryProvider` / `get_memory_manager` / `set_memory_manager` |
| `src/nini/agent/runner.py` | `AgentRunner.__init__` 添加 `_memory_manager` 字段；`run()` 内初始化 + 注入 system_prompt + `on_session_end` |
| `src/nini/agent/components/context_memory.py` | `build_long_term_memory_context` 优先路由到 `MemoryManager.prefetch_all()`（**主检索路径**） |
| `src/nini/agent/components/context_builder.py` | `_build_dataset_history_memory` 优先路由到 `MemoryManager.prefetch_all()`（**数据集专用路径**） |

> **注**：设计文档早期版本误将 `agent/__init__.py` 列为改动目标，正确改动点是 `runner.py`（AgentRunner 的构造和 run 方法）。

### 5.3 废弃（过渡期保留，P5 阶段独立 PR 删除）

| 文件 | 替代方 |
|---|---|
| `src/nini/memory/long_term_memory.py` | `ScientificMemoryProvider` + `MemoryStore` |
| `src/nini/memory/research_profile.py` | `research_profiles` 表 + `MemoryStore.upsert_profile()` |
| `src/nini/memory/profile_narrative.py` | `research_profiles.narrative_md` 列 |
| `src/nini/memory/knowledge.py` | `on_session_end()` 沉淀路径 |

---

## 6. SQLite Schema（`data/nini_memory.db`）

### `facts` 表

```sql
CREATE TABLE facts (
    id                TEXT PRIMARY KEY,        -- UUID
    content           TEXT NOT NULL,
    memory_type       TEXT NOT NULL,           -- finding / statistic / decision /
                                               -- insight / knowledge / preference
    summary           TEXT DEFAULT '',
    tags              TEXT DEFAULT '[]',       -- JSON 数组
    importance        REAL DEFAULT 0.5,        -- 0~1，含时间衰减
    trust_score       REAL DEFAULT 0.5,        -- 0~1，随访问反馈更新
    source_session_id TEXT DEFAULT '',
    created_at        REAL NOT NULL,           -- Unix timestamp
    updated_at        REAL NOT NULL,
    access_count      INTEGER DEFAULT 0,
    last_accessed_at  REAL,
    dedup_key         TEXT UNIQUE,             -- MD5(type|dataset|content) 防重复写入
    sci_metadata      TEXT DEFAULT '{}'        -- JSON 列：科研专用字段
);
```

`sci_metadata` 字段约定（按需填充，缺失字段留空）：

```json
{
  "dataset_name":   "survey_2024.csv",
  "analysis_type":  "t_test",
  "test_name":      "独立样本 t 检验",
  "test_statistic": 3.14,
  "p_value":        0.002,
  "effect_size":    0.45,
  "effect_type":    "cohen_d",
  "significant":    true,
  "confidence":     0.9,
  "sample_size":    120,
  "decision_type":  "method_selection",
  "chosen":         "Mann-Whitney U",
  "rationale":      "正态性检验不通过"
}
```

### `facts_fts` 虚拟表（FTS5）

```sql
CREATE VIRTUAL TABLE facts_fts USING fts5(
    content, summary, tags,
    content=facts, content_rowid=rowid,
    tokenize='unicode61'
);
```

自动维护触发器：`facts_ai` / `facts_ad` / `facts_au`（INSERT/DELETE/UPDATE 后同步 FTS5 索引）。

FTS5 不可用时（部分 SQLite 编译版本），降级为 `LIKE` 关键词匹配。

### `research_profiles` 表

```sql
CREATE TABLE research_profiles (
    profile_id   TEXT PRIMARY KEY,
    data_json    TEXT NOT NULL,   -- UserProfile 所有字段序列化
    narrative_md TEXT DEFAULT '', -- AUTO/AGENT/USER 三段叙述层合一存储
    updated_at   REAL NOT NULL
);
```

### 索引

```sql
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(source_session_id);
CREATE INDEX IF NOT EXISTS idx_facts_type    ON facts(memory_type);
CREATE INDEX IF NOT EXISTS idx_facts_trust   ON facts(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_facts_dedup   ON facts(dedup_key);
-- JSON1 扩展存在时生效，否则静默跳过
CREATE INDEX IF NOT EXISTS idx_facts_dataset
    ON facts(json_extract(sci_metadata, '$.dataset_name'));
```

---

## 7. MemoryProvider ABC（`memory/provider.py`）

```python
class MemoryProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    # name == "builtin" 表示内置 provider，由 MemoryManager 特殊处理

    @abstractmethod
    async def initialize(self, session_id: str, **kwargs: Any) -> None: ...

    def system_prompt_block(self) -> str:
        """返回注入 system prompt 的静态文本块（会话开始快照，不中途变化）。"""
        return ""

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """每轮 LLM 调用前：检索相关记忆，返回原始上下文文本（不带 fencing）。"""
        return ""

    async def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """每轮结束后：持久化本轮对话摘要/发现。"""

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """会话结束：从完整历史提取关键记忆沉淀到 facts 表。"""

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """上下文压缩前：提取关键数值，返回追加到压缩 prompt 的文本。"""
        return ""

    @abstractmethod
    def get_tool_schemas(self) -> list[dict[str, Any]]: ...

    async def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        raise NotImplementedError

    async def shutdown(self) -> None: ...
```

---

## 8. MemoryManager（`memory/manager.py`）

### 核心规则

- 内置 provider（`name == "builtin"`）永远是第一个，不可移除
- 最多允许 1 个外部（非内置）provider；注册第二个时拒绝并警告
- 任何 provider 的任何钩子抛出异常，仅记录警告，不影响其他 provider 和 agent

### Memory Context Fencing

所有 provider 的 `prefetch()` 返回原始文本，由 `MemoryManager.prefetch_all()` 拼接后统一经 `build_memory_context_block()` 包裹：

```python
def build_memory_context_block(raw: str) -> str:
    if not raw or not raw.strip():
        return ""
    clean = _FENCE_TAG_RE.sub("", raw)   # 移除嵌套 fence 标签（防注入）
    return (
        "<memory-context>\n"
        "[系统注记：以下是召回的记忆上下文，非用户新输入，仅作参考背景。]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )
```

> **Fencing 统一规则**：凡是经 `MemoryManager.prefetch_all()` 路径的记忆上下文，使用 `build_memory_context_block`；现有 `format_untrusted_context_block("long_term_memory", ...)` 调用在向后兼容降级路径中保留，P5 阶段随旧文件一并删除。

### 主要方法

| 方法 | 调用时机 | 说明 |
|---|---|---|
| `build_system_prompt()` | 会话开始，仅一次 | 快照注入，保护 KV cache |
| `prefetch_all(query, session_id)` | 每轮 LLM 调用前 | 汇总所有 provider 的召回结果（原始文本） |
| `sync_all(user, assistant, session_id)` | 每轮结束后 | `asyncio.create_task` 异步写，不阻塞响应路径 |
| `on_session_end(messages)` | 会话关闭时 | 触发重度沉淀 |
| `on_pre_compress(messages)` | 上下文压缩触发时 | 保护统计数值不被压缩丢弃 |
| `get_all_tool_schemas()` | 工具注册时 | 向 LLM 暴露记忆工具（去重） |
| `handle_tool_call(name, args)` | LLM 调用工具时 | 路由到正确 provider |
| `initialize_all(session_id)` | 会话开始 | 初始化所有 provider |
| `shutdown_all()` | 进程退出 | 逆序关闭 provider |

全局单例：`get_memory_manager()` / `set_memory_manager()` 供跨模块访问。

---

## 9. ScientificMemoryProvider（`memory/scientific_provider.py`）

`name = "builtin"`，nini 唯一内置 provider，永远开启。

### `prefetch()` 三段式检索

```
1. FTS5 全文搜索（query → facts_fts）
       ↓ 召回候选集（top_k × 3）
2. sci_metadata 上下文加权重排序
       dataset_name 命中 × 1.5
       analysis_type 命中 × 1.3
       trust_score 加权
       时间衰减 e^(-λ × days)，access_count > 5 时 λ 减半
       ↓
3. 截取 top_k 条，返回格式化文本（不含 fencing，由 MemoryManager 统一包裹）
```

### `sync_turn()` 轻量提取

扫描 assistant 回复，满足任一条件即写入 facts（importance < 0.4 不写入）：
- 包含 `p =` / `p<` / `p值` 且有具体数字
- 包含 `效应量` / `effect size` / `Cohen` 且有具体数字
- 包含 `结论：` / `发现：` 等显式标记段落

### `on_session_end()` 重度沉淀流程

1. 读取 `session.db` 中本会话的 `AnalysisMemory`
2. `finding.confidence >= 0.7` → `facts(memory_type='finding')`
3. `statistic.significant=True` → `facts(memory_type='statistic', importance=0.8)`
4. `decision.confidence >= 0.7` → `facts(memory_type='decision')`
5. `session knowledge.md` 内容 → `facts(memory_type='knowledge')`
6. 更新 `research_profiles` 表

`on_session_end` 接收 `messages: list[dict]`，对应 `session.messages`（`Session` 类的直接属性，非方法调用）。

### `on_pre_compress()` 压缩保护

从待压缩消息中抽取含统计数值的行（正则匹配 `_STAT_PATTERNS`），生成追加到压缩 prompt 的提示：

```
以下统计结果必须完整保留在摘要中：
- t(58)=3.14, p=0.002, d=0.45（独立样本 t 检验，survey_2024.csv）
```

### 暴露给 LLM 的工具

| 工具名 | 操作 | 说明 |
|---|---|---|
| `nini_memory_find` | 检索 | FTS5 全文 + sci_metadata JSON 过滤（支持 `p_value` / `dataset_name` 等参数） |
| `nini_memory_save` | 存储 | LLM 主动保存一条发现/洞察 |

---

## 10. Agent 生命周期接入点

### 10.1 runner.py 接入

```python
# AgentRunner.__init__ 末尾追加
self._memory_manager: MemoryManager | None = None

# AgentRunner.run() 内，session 参数处理后，system_prompt 组装前：
if self._memory_manager is None:
    db_path = settings.sessions_dir.parent / "nini_memory.db"
    mgr = MemoryManager()
    mgr.add_provider(ScientificMemoryProvider(db_path=db_path))
    self._memory_manager = mgr
    set_memory_manager(mgr)
await self._memory_manager.initialize_all(session_id=session.id)
memory_system_prompt = self._memory_manager.build_system_prompt()
if memory_system_prompt:
    system_prompt = system_prompt + "\n\n" + memory_system_prompt

# runner.py:1294（会话结束处）并行调用（保留原有调用）：
if self._memory_manager is not None:
    track_background_task(
        self._memory_manager.on_session_end(session.messages)  # session.messages，非 get_messages()
    )
```

> **API 修正**：`session.messages` 是 `Session` 类的直接列表属性（`session.py:86`），不存在 `get_messages()` 方法。

### 10.2 context_memory.py 接入（主检索路径）

`build_long_term_memory_context`（`context_builder.py:227` 调用的主路径）改为优先走 MemoryManager：

```python
async def build_long_term_memory_context(query: str, *, context=None, top_k=3) -> str:
    if not query or not query.strip():
        return ""
    # 优先路径：MemoryManager（新架构）
    try:
        from nini.memory.manager import get_memory_manager, build_memory_context_block
        mgr = get_memory_manager()
        if mgr.providers:
            raw = await mgr.prefetch_all(query.strip(), session_id="")
            if raw:
                return build_memory_context_block(raw)
    except Exception:
        pass  # 降级到旧路径
    # 降级路径：LongTermMemoryStore（向后兼容，P5 删除）
    ...原有实现保持不变...
```

### 10.3 context_builder.py 接入（数据集专用路径）

`_build_dataset_history_memory`（`context_builder.py:554`，数据集加载时调用）同样优先走 MemoryManager：

```python
async def _build_dataset_history_memory(dataset_name: str) -> str:
    if not dataset_name or not dataset_name.strip():
        return ""
    # 优先路径：MemoryManager
    try:
        from nini.memory.manager import get_memory_manager, build_memory_context_block
        mgr = get_memory_manager()
        if mgr.providers:
            raw = await mgr.prefetch_all(dataset_name.strip())
            if raw:
                return build_memory_context_block(raw)
    except Exception:
        pass
    # 降级路径：原有实现
    ...原有实现保持不变...
```

---

## 11. 旧数据迁移策略

| 旧存储 | 迁移目标 | 触发时机 | 策略 |
|---|---|---|---|
| `long_term_memory/entries.jsonl` | `facts` 表 | `MemoryStore.__init__()` | 逐行 `INSERT OR IGNORE`（dedup_key 防重） |
| `profiles/*.json` | `research_profiles.data_json` | `MemoryStore.__init__()` | 逐文件读取，原文件保留 |
| `*_profile.md` | `research_profiles.narrative_md` | 同上 | 同上 |
| `sessions/*/knowledge.md` | `facts(memory_type='knowledge')` | `on_session_end()` | 按需触发 |

迁移为单次幂等操作，失败时记录警告，不阻止 agent 启动。

---

## 12. 错误处理与并发安全

### 隔离原则

所有 provider 钩子调用均包裹 `try/except`，异常仅 `logger.warning`，不上抛。

### 降级策略

| 故障 | 降级行为 |
|---|---|
| SQLite 不可用 | `prefetch()` 返回空字符串，agent 正常运行 |
| FTS5 不可用 | 降级为 `LIKE` 关键词匹配 |
| `on_session_end()` 失败 | 记录警告，不影响会话关闭 |
| `sync_turn()` 写入失败 | 记录警告，不影响响应返回 |

### 并发安全

| 场景 | 机制 |
|---|---|
| 多会话同时写 `nini_memory.db` | SQLite WAL 模式 |
| `sync_turn()` 后台写 | `asyncio.create_task()` |
| 高重要性沉淀触发 | per-session `asyncio.Lock` |

---

## 13. 向后兼容声明

- `ResearchProfileManager` / `get_research_profile_manager()` 公共接口保留，内部读写 SQLite
- `LongTermMemoryStore` 保留为兼容 shim，内部委托给 `MemoryStore`；P5 阶段标记 `@deprecated` 后删除
- `AnalysisMemoryTool` 保留，内部改为调用 `MemoryManager.handle_tool_call()`
- 所有调用 `build_long_term_memory_context` 的外部代码不需要修改（接口签名不变，内部切换实现）

---

## 14. 测试策略

```
tests/memory/
  test_memory_provider.py        ← ABC 约束测试（不可实例化、可选钩子默认值）
  test_memory_manager.py         ← 注册规则、provider 异常隔离、工具路由、fencing 函数
  test_memory_store.py           ← SQLite 单元测试（:memory: 数据库，schema/读写/FTS5）
  test_migration.py              ← JSONL → SQLite 迁移正确性（条数、字段、幂等）
  test_scientific_provider.py    ← provider 生命周期（prefetch/sync_turn/on_session_end/on_pre_compress/工具调用）
```

- 所有测试使用 `:memory:` SQLite，无文件 I/O 依赖
- `on_session_end` 测试使用预置的 `AnalysisMemory` fixture
- 迁移测试读取 `tests/fixtures/sample_entries.jsonl`，验证迁移后条数与字段一致
- Phase 3 集成后：`pytest -q`（不含 memory 目录）零回归，`pytest tests/memory/ -v` 全通过

---

## 15. 实施阶段

| 阶段 | 内容 | 输出产物 |
|---|---|---|
| **P1** | `MemoryProvider` ABC + `MemoryManager` + `MemoryStore` + SQLite schema | 纯新增，不改现有代码，所有 tests/memory/ 测试通过 |
| **P2** | `ScientificMemoryProvider`（init / prefetch / sync_turn / on_session_end / on_pre_compress + 工具） | 可独立测试，无需接入 agent |
| **P3** | 旧数据迁移（JSONL + profile JSON/MD）测试通过 | |
| **P4** | Agent 生命周期接入（runner.py + context_memory.py + context_builder.py） | 功能等价替换，全量 pytest 零回归 |
| **P5** | 废弃旧文件，移除双写冗余（独立 PR） | 代码库清理完成 |

---

## 16. 验证方式

```bash
# 事件 schema 一致性（CI 在 pytest 前运行）
python scripts/check_event_schema_consistency.py

# memory 专项测试
pytest tests/memory/ -v --race

# 全量后端测试（P4 完成后）
pytest -q

# 类型检查
mypy src/nini/memory/

# 格式检查
black --check src/nini/memory/ src/nini/agent/runner.py \
      src/nini/agent/components/context_memory.py \
      src/nini/agent/components/context_builder.py
```

---

## 17. 风险与回滚

### 风险

| 风险 | 可能性 | 缓解措施 |
|---|---|---|
| SQLite WAL 锁竞争导致写入超时 | 低（单机，会话数有限） | `timeout=10.0`，降级路径保底 |
| FTS5 在目标 SQLite 版本不可用 | 低（stdlib SQLite ≥ 3.7.4 支持） | 启动时探测，自动降级为 LIKE |
| `on_session_end` 耗时增加会话关闭延迟 | 中 | `asyncio.create_task` 后台执行 |
| 迁移幂等失败导致重复记忆 | 低 | `dedup_key UNIQUE` 约束保护 |

### 回滚方案

P1-P3 阶段为纯新增代码，可直接 revert PR 无副作用。

P4（agent 接入）采用双路径策略：`MemoryManager.prefetch_all()` 失败时降级到原有 `LongTermMemoryStore` 路径，agent 不中断。若出现严重问题，在 `build_long_term_memory_context` 和 `_build_dataset_history_memory` 中注释掉新路径的 try 块即可回退，无需 revert 整个 PR。

`nini_memory.db` 独立于 `session.db`，删除 db 文件可完全清除新架构状态，不影响会话历史。
