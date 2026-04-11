# 记忆系统架构重构设计文档

**日期**：2026-04-11  
**状态**：已批准，待实施  
**参考**：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 记忆架构

---

## 背景与动机

nini 现有记忆系统由 5 个相互独立的组件构成，持久化格式混杂（JSONL、JSON、Markdown、SQLite），导致以下问题：

1. **数据完整性弱**：`LongTermMemoryStore` 使用 JSONL 文件，无事务保障，无 SQL 查询能力，科研数值（p 值、效应量）无法按条件过滤
2. **无统一抽象**：各层直接依赖具体实现，无法替换或扩展存储后端
3. **生命周期碎片化**：会话结束、上下文压缩、记忆沉淀由散落的函数调用驱动，缺少统一编排
4. **双写冗余**：`memory.jsonl` 与 `session.db` 同时维护会话历史

hermes-agent 的 `MemoryProvider` 抽象 + `MemoryManager` 编排模式解决了上述问题，且其 holographic 插件的 SQLite + FTS5 设计直接满足「所有会话不丢失、存入数据库」的诉求。

---

## 目标

- 引入 `MemoryProvider` ABC 和 `MemoryManager`，与 hermes-agent 架构对齐
- 将 `LongTermMemoryStore` 的 JSONL 迁移到 SQLite，提供事务安全、FTS5 全文检索、科研字段 JSON 过滤
- 统一研究画像的 JSON + Markdown 双存储为单一 SQLite 表
- 完整接入生命周期钩子（每轮、会话结束、压缩前）
- 向后兼容现有公共接口，过渡期后清除废弃层

---

## 不在范围内

- 接入 hermes 的外部 memory provider 插件（Honcho、Mem0 等）——架构预留槽位，但本次不实现
- 修改 `session.db` 的现有 schema
- 向量索引迁移（现有 `VectorKnowledgeStore` 保持不变，后续可接入 `MemoryProvider.prefetch()`）

---

## 架构概览

```
MemoryManager                          ← 编排层（对齐 hermes）
  └── ScientificMemoryProvider         ← nini 唯一内置 provider（永远开启）
        └── MemoryStore
              └── nini_memory.db (SQLite, WAL 模式)
                    ├── facts              ← 通用记忆层 + sci_metadata JSON 列
                    ├── facts_fts          ← FTS5 全文索引
                    └── research_profiles  ← 研究画像（JSON + Markdown 合一）

data/sessions/{id}/session.db          ← 会话历史（不变）
```

**预留扩展槽**：`MemoryManager` 支持注册最多 1 个外部 provider，内置 provider 不可移除。

---

## 文件变更清单

### 新增（4 个）

| 文件 | 职责 |
|---|---|
| `src/nini/memory/provider.py` | `MemoryProvider` ABC，定义生命周期接口 |
| `src/nini/memory/manager.py` | `MemoryManager`，编排所有 provider |
| `src/nini/memory/scientific_provider.py` | `ScientificMemoryProvider`，nini 唯一内置 provider |
| `src/nini/memory/memory_store.py` | SQLite 操作层，被 `ScientificMemoryProvider` 使用 |

### 改动（3 个）

| 文件 | 改动内容 |
|---|---|
| `src/nini/memory/__init__.py` | 导出 `MemoryManager`、`MemoryProvider`、`ScientificMemoryProvider` |
| `src/nini/agent/components/context_memory.py` | 改为调用 `MemoryManager.prefetch_all()`，移除直接导入旧组件 |
| `src/nini/agent/__init__.py` | 初始化 `MemoryManager`，接入生命周期钩子 |

### 废弃（过渡期保留，P5 阶段清除）

| 文件 | 替代方 |
|---|---|
| `src/nini/memory/long_term_memory.py` | `ScientificMemoryProvider` + `MemoryStore` |
| `src/nini/memory/research_profile.py` | `research_profiles` 表 + `MemoryStore.upsert_profile()` |
| `src/nini/memory/profile_narrative.py` | `research_profiles.narrative_md` 列 |
| `src/nini/memory/knowledge.py` | `on_session_end()` 沉淀到 `facts(memory_type='knowledge')` |

---

## SQLite Schema（`data/nini_memory.db`）

### `facts` 表

```sql
CREATE TABLE facts (
    id                TEXT PRIMARY KEY,       -- UUID
    content           TEXT NOT NULL,
    memory_type       TEXT NOT NULL,          -- finding / statistic / decision /
                                              -- insight / knowledge / preference
    summary           TEXT DEFAULT '',
    tags              TEXT DEFAULT '[]',      -- JSON array
    importance        REAL DEFAULT 0.5,       -- 0~1，含时间衰减
    trust_score       REAL DEFAULT 0.5,       -- 0~1，随访问反馈更新
    source_session_id TEXT DEFAULT '',
    created_at        REAL NOT NULL,          -- Unix timestamp
    updated_at        REAL NOT NULL,
    access_count      INTEGER DEFAULT 0,
    last_accessed_at  REAL,
    dedup_key         TEXT UNIQUE,            -- MD5(type|dataset|content) 防重复写入
    sci_metadata      TEXT DEFAULT '{}'       -- JSON 列：科研专用字段
);
```

**`sci_metadata` 字段约定**（按需填充，缺失字段留空）：

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

### `research_profiles` 表

```sql
CREATE TABLE research_profiles (
    profile_id   TEXT PRIMARY KEY,
    data_json    TEXT NOT NULL,   -- UserProfile 所有字段序列化
    narrative_md TEXT DEFAULT '', -- AUTO/AGENT/USER 三段叙述层合一存储
    updated_at   REAL NOT NULL
);
```

### 查询索引

```sql
CREATE INDEX idx_facts_session ON facts(source_session_id);
CREATE INDEX idx_facts_type    ON facts(memory_type);
CREATE INDEX idx_facts_trust   ON facts(trust_score DESC);
CREATE INDEX idx_facts_dataset ON facts(json_extract(sci_metadata, '$.dataset_name'));
CREATE INDEX idx_facts_dedup   ON facts(dedup_key);
```

---

## MemoryProvider ABC（`memory/provider.py`）

```python
class MemoryProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def initialize(self, session_id: str, **kwargs) -> None: ...

    def system_prompt_block(self) -> str:
        """注入 system prompt 的静态块（会话开始快照，不中途变化）。"""
        return ""

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """每轮 LLM 调用前：检索相关记忆，返回注入上下文文本。"""
        return ""

    async def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """每轮结束后：持久化本轮对话摘要/发现。"""

    async def on_session_end(self, messages: list[dict]) -> None:
        """会话结束：从完整历史提取关键记忆沉淀到 facts 表。"""

    def on_pre_compress(self, messages: list[dict]) -> str:
        """上下文压缩前：提取关键数值，返回追加到压缩 prompt 的文本。"""
        return ""

    @abstractmethod
    def get_tool_schemas(self) -> list[dict]: ...

    async def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        raise NotImplementedError

    async def shutdown(self) -> None: ...
```

---

## MemoryManager（`memory/manager.py`）

### 核心规则（对齐 hermes）

- 内置 provider（`name == "builtin"`）永远是第一个，不可移除；`ScientificMemoryProvider.name` 返回 `"builtin"`
- 最多允许 1 个外部（非内置）provider；注册第二个外部 provider 时拒绝并警告
- 任何 provider 的任何钩子抛出异常，仅记录警告，不影响其他 provider 和 agent

### Memory Context Fencing

```python
def build_memory_context_block(raw: str) -> str:
    """将召回记忆包裹在 fence 标签内，防止 LLM 把历史记忆误当当前输入。"""
    if not raw or not raw.strip():
        return ""
    clean = _FENCE_TAG_RE.sub('', raw)
    return (
        "<memory-context>\n"
        "[系统注记：以下是召回的记忆上下文，非用户新输入，仅作参考背景。]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )
```

### 主要方法

| 方法 | 调用时机 | 说明 |
|---|---|---|
| `build_system_prompt()` | 会话开始，仅一次 | 快照注入，保护 KV cache |
| `prefetch_all(query, session_id)` | 每轮 LLM 调用前 | 汇总所有 provider 的召回结果 |
| `sync_all(user, assistant, session_id)` | 每轮结束后 | 异步写，不阻塞响应路径 |
| `on_session_end(messages)` | 会话关闭时 | 触发重度沉淀 |
| `on_pre_compress(messages)` | 上下文压缩触发时 | 保护统计数值不被压缩丢弃 |
| `get_all_tool_schemas()` | 工具注册时 | 向 LLM 暴露记忆工具 |
| `handle_tool_call(name, args)` | LLM 调用工具时 | 路由到正确 provider |

---

## ScientificMemoryProvider 内部实现

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
3. 截取 top_k 条，包裹 <memory-context> fencing 返回
```

### `sync_turn()` 轻量提取规则

扫描 assistant 回复，满足以下任一条件即写入 facts（importance < 0.4 不写入）：
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

### `on_pre_compress()` 压缩保护

从待压缩消息中抽取含统计数值的行，生成必须保留提示追加到压缩 prompt：

```
以下统计结果必须完整保留在摘要中：
- t(58)=3.14, p=0.002, d=0.45（独立样本 t 检验，survey_2024.csv）
```

### 暴露给 LLM 的工具

| 工具名 | 操作 | 说明 |
|---|---|---|
| `nini_memory_find` | 检索 | FTS5 全文 + sci_metadata JSON 过滤（支持 p_value / dataset_name 等参数） |
| `nini_memory_save` | 存储 | LLM 主动保存一条发现/洞察 |

---

## Agent 生命周期接入点

```
会话启动
  ├── memory_manager = MemoryManager()
  ├── memory_manager.add_provider(ScientificMemoryProvider(db_path))
  ├── await memory_manager.initialize_all(session_id)
  └── system_prompt += memory_manager.build_system_prompt()   ← 快照，不再变化

每轮处理
  ├── context = await memory_manager.prefetch_all(user_msg, session_id=sid)
  ├── injected = build_memory_context_block(context)          ← fencing
  ├── [LLM 调用，injected 作为额外上下文注入]
  └── asyncio.create_task(memory_manager.sync_all(...))       ← 异步写，不阻塞

上下文压缩触发时
  └── hint = memory_manager.on_pre_compress(messages)
        └── 追加到压缩 prompt

会话结束（WebSocket 断开 / /reset）
  └── await memory_manager.on_session_end(full_message_history)
```

---

## 旧数据迁移策略

| 旧存储 | 迁移目标 | 触发时机 | 策略 |
|---|---|---|---|
| `long_term_memory/entries.jsonl` | `facts` 表 | `MemoryStore.__init__()` | 逐行 `INSERT OR IGNORE`（dedup_key 防重） |
| `profiles/*.json` | `research_profiles.data_json` | `MemoryStore.__init__()` | 逐文件读取，原文件保留 |
| `*_profile.md` | `research_profiles.narrative_md` | 同上 | 同上 |
| `sessions/*/knowledge.md` | `facts(memory_type='knowledge')` | `on_session_end()` | 按需触发 |

迁移为**单次幂等操作**，失败时记录警告，不阻止 agent 启动。

---

## MemoryStore 核心 API（`memory/memory_store.py`）

```python
class MemoryStore:
    def __init__(self, db_path: Path)

    # 写
    def upsert_fact(self, *, content: str, memory_type: str,
                    summary: str = "", tags: list[str] | None = None,
                    importance: float = 0.5, trust_score: float = 0.5,
                    source_session_id: str = "",
                    sci_metadata: dict | None = None) -> str   # 返回 fact id

    def upsert_profile(self, profile_id: str,
                       data_json: dict, narrative_md: str) -> None

    # 读
    def search_fts(self, query: str, top_k: int = 10) -> list[dict]
    def filter_by_sci(self, *, dataset_name: str | None = None,
                      analysis_type: str | None = None,
                      max_p_value: float | None = None,
                      min_effect_size: float | None = None) -> list[dict]
    def get_profile(self, profile_id: str) -> dict | None

    # 迁移（__init__ 自动调用；也可手动调用用于测试或补迁）
    def migrate_from_jsonl(self, jsonl_path: Path) -> int
    def migrate_profile_json(self, json_path: Path,
                             narrative_path: Path | None = None) -> None
```

---

## 错误处理

### 隔离原则

所有 provider 的钩子调用均包裹 `try/except`，异常仅警告日志，不上抛。

### 降级策略

| 故障 | 降级行为 |
|---|---|
| SQLite 不可用 | 记录警告，`prefetch()` 返回空字符串，agent 正常运行 |
| FTS5 不可用 | 降级为 `LIKE` 关键词匹配（复用 `memory/db.py` 现有逻辑） |
| `on_session_end()` 失败 | 记录警告，不影响会话关闭 |
| `sync_turn()` 写入失败 | 记录警告，不影响响应返回 |

### 并发安全

| 场景 | 机制 |
|---|---|
| 多会话同时写 `nini_memory.db` | SQLite WAL 模式 |
| `sync_turn()` 后台写 | `asyncio.create_task()` |
| 高重要性沉淀触发 | per-session `asyncio.Lock` |

---

## 测试策略

```
tests/memory/
  test_memory_store.py          ← SQLite 单元测试（:memory: 数据库）
  test_scientific_provider.py   ← provider 生命周期测试（mock session）
  test_memory_manager.py        ← 编排层：provider 隔离、工具路由
  test_migration.py             ← JSONL → SQLite 迁移正确性验证
```

- 所有测试使用 `:memory:` SQLite，无文件 I/O 依赖
- `on_session_end` 测试使用预置的 `AnalysisMemory` fixture
- 迁移测试读取 `tests/fixtures/sample_entries.jsonl`，验证迁移后条数与字段一致

---

## 实施阶段

| 阶段 | 内容 | 输出产物 |
|---|---|---|
| **P1** | `MemoryProvider` ABC + `MemoryManager` + `MemoryStore` + SQLite schema | 纯新增，不改现有代码 |
| **P2** | `ScientificMemoryProvider` 核心（init / prefetch / on_session_end） | 可独立测试，无需接入 agent |
| **P3** | 旧数据迁移（JSONL + profile JSON/MD） | 迁移测试通过 |
| **P4** | Agent 生命周期接入（替换 `context_memory.py` 的直接调用） | 功能等价替换，E2E 测试通过 |
| **P5** | 废弃旧文件，移除双写冗余 | 代码库清理完成 |

---

## 向后兼容声明

- `ResearchProfileManager` / `get_research_profile_manager()` 公共接口保留，内部改为读写 SQLite
- `LongTermMemoryStore` 保留为兼容 shim，方法内部委托给 `MemoryStore`，P5 阶段标记 `@deprecated`
- `AnalysisMemoryTool` 保留，内部改为调用 `MemoryManager.handle_tool_call()`
