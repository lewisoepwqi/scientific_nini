## Why

nini 的记忆系统由 5 个独立组件构成，核心的跨会话长期记忆（`LongTermMemoryStore`）存储在 JSONL 文件中，无事务保障、无 SQL 查询能力，导致科研分析发现（统计结果、方法决策）在会话结束后无法精确检索（如按 `p_value < 0.05` 过滤）。这对科研数据分析这类要求严谨的任务是根本性缺陷。

## What Changes

- **新增** `MemoryProvider` ABC，定义统一的生命周期接口（`initialize` / `prefetch` / `sync_turn` / `on_session_end` / `on_pre_compress`），对齐 hermes-agent 架构
- **新增** `MemoryManager` 编排层，隔离 provider 异常，管理内置 + 外部 provider 注册（最多 1 个外部），提供 Memory Context Fencing（`<memory-context>` 标签防止历史记忆被 LLM 误当当前输入）
- **新增** `ScientificMemoryProvider`（`name="builtin"`），实现三段式检索（FTS5 → 上下文加权重排 → 截取），轻量 `sync_turn` 提取，重度 `on_session_end` 沉淀，压缩前统计数值保护
- **新增** `MemoryStore`，将 `LongTermMemoryStore` 的 JSONL 和研究画像的 JSON/Markdown 双存储迁移到单一 SQLite 文件（`data/nini_memory.db`），WAL 模式 + FTS5 全文索引 + `sci_metadata` JSON 列支持 `json_extract()` 精确过滤
- **改动** `AgentRunner`（`runner.py`）：初始化 `MemoryManager`，注入 system_prompt 快照，会话结束时触发 `on_session_end`
- **改动** `build_long_term_memory_context`（`context_memory.py`）：主检索路径优先路由到 `MemoryManager.prefetch_all()`，降级保留原有 `LongTermMemoryStore` 路径
- **改动** `_build_dataset_history_memory`（`context_builder.py`）：数据集专用检索路径同步切换
- **废弃**（过渡期保留，P5 独立 PR 删除）：`long_term_memory.py`、`research_profile.py`、`profile_narrative.py`、`knowledge.py`

## Capabilities

### New Capabilities

- `memory-provider-abstraction`：`MemoryProvider` ABC + `MemoryManager` 编排层，包括 provider 注册规则、异常隔离、Memory Context Fencing、全局单例管理
- `scientific-memory-store`：`MemoryStore`（SQLite WAL + FTS5 + `sci_metadata` JSON 列）+ 旧数据幂等迁移（JSONL → facts 表，profiles JSON/MD → research_profiles 表）
- `scientific-memory-provider`：`ScientificMemoryProvider` 的完整生命周期实现（prefetch 三段式检索、sync_turn 轻量提取、on_session_end 重度沉淀、on_pre_compress 压缩保护、nini_memory_find / nini_memory_save 工具）

### Modified Capabilities

- `context-aware-memory-ranking`：记忆检索主路径（`build_long_term_memory_context`）和数据集专用路径（`_build_dataset_history_memory`）均切换为经 `MemoryManager.prefetch_all()` 调用，fencing 机制从 `format_untrusted_context_block` 改为 `build_memory_context_block`（`<memory-context>` 标签）
- `memory-session-extraction`：`on_session_end` 沉淀逻辑从 `consolidate_session_memories`（JSONL 写入）切换到 `ScientificMemoryProvider.on_session_end()`（SQLite 写入）；双路径并行运行，P5 阶段移除旧路径

## Impact

**受影响代码：**
- `src/nini/memory/`：新增 4 个模块（`provider.py`、`manager.py`、`scientific_provider.py`、`memory_store.py`），`__init__.py` 新增导出
- `src/nini/agent/runner.py`：`AgentRunner.__init__` + `run()` 接入 `MemoryManager`
- `src/nini/agent/components/context_memory.py`：`build_long_term_memory_context` 新增优先路径
- `src/nini/agent/components/context_builder.py`：`_build_dataset_history_memory` 新增优先路径

**新增持久化文件：** `data/nini_memory.db`（SQLite，独立于 `session.db`，删除不影响会话历史）

**无新增依赖：** 全部使用 Python 标准库（`sqlite3`、`hashlib`、`uuid`）

**非目标：** 接入 hermes 外部 memory provider（Honcho、Mem0 等）；修改 `session.db` schema；向量索引迁移；前端改动
