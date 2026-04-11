## Context

nini 的记忆系统当前由 5 个独立组件构成，各自持有不同的持久化格式：

| 组件 | 存储 | 问题 |
|---|---|---|
| `LongTermMemoryStore` | `long_term_memory/entries.jsonl` | 无事务、无 SQL 查询、无法精确过滤科研数值 |
| `ResearchProfileManager` | `profiles/*.json` | 与 Markdown 双写冗余 |
| `ProfileNarrativeManager` | `*_profile.md` | 与 JSON 双写冗余 |
| `KnowledgeMemory` | `sessions/*/knowledge.md` | 单会话，无跨会话检索 |
| `session.db` | SQLite（每会话独立） | 仅存对话历史，无科研发现层 |

这 5 个组件无统一接口，生命周期（会话结束沉淀、压缩前保护、每轮检索）由散落的函数调用驱动，扩展新存储后端需要侵入多处代码。对科研分析场景，最关键的问题是无法跨会话查询「哪个数据集的 t 检验 p 值 < 0.05」这类条件——JSONL 做不到。

参考项目：hermes-agent（NousResearch）的 `MemoryProvider` ABC + `MemoryManager` 编排模式已在类似场景中验证，其 holographic 插件的 SQLite + FTS5 设计与 nini 的需求高度匹配。

---

## Goals / Non-Goals

**Goals:**

- 引入 `MemoryProvider` ABC，为所有跨会话记忆提供统一生命周期接口
- 将跨会话记忆迁移到单一 SQLite 文件（`data/nini_memory.db`），事务安全 + FTS5 全文检索 + `json_extract()` 精确过滤
- 接入 Agent 生命周期的三个关键点：每轮检索（`prefetch`）、会话结束沉淀（`on_session_end`）、压缩前保护（`on_pre_compress`）
- 主检索路径（`build_long_term_memory_context`）和数据集专用路径（`_build_dataset_history_memory`）均切换为新架构
- 旧数据幂等迁移，不丢失现有记忆

**Non-Goals:**

- 接入外部 memory provider（Honcho、Mem0 等）——槽位预留，本次不实现
- 修改 `session.db` 的现有 schema
- 向量索引（`VectorKnowledgeStore` 保持不变）
- P5 旧文件清理（独立 PR，本次保留向后兼容 shim）
- 前端改动

---

## Decisions

### 决策 1：单一 `nini_memory.db` vs 保持各组件独立存储

**选择**：单一全局 SQLite 文件 `data/nini_memory.db`，所有跨会话记忆写入同一个 `facts` 表，研究画像写入 `research_profiles` 表。

**理由**：
- 单文件简化部署和备份；WAL 模式支持多会话并发写入，无需引入额外进程间通信
- 同一数据库可用 JOIN 或子查询关联 `facts` 与 `research_profiles`，后续分析能力更强
- 相比保持各组件独立的 SQLite，避免了连接管理碎片化

**备选方案**：每个组件独立 SQLite → 拒绝，原因：依然是 N 个连接，无法跨表查询，迁移难度不减。

---

### 决策 2：`MemoryProvider` ABC vs 直接重构各组件

**选择**：引入 `MemoryProvider` ABC，将 `ScientificMemoryProvider` 作为 nini 的唯一内置 provider。

**理由**：
- 统一生命周期接口后，`AgentRunner` 只需调用 `MemoryManager` 的方法，不再直接依赖具体实现
- 预留外部 provider 槽位（最多 1 个）允许未来接入 Honcho/Mem0 而不修改 agent 核心
- 异常隔离：任何 provider 失败只记录 warning，不影响 agent 主循环

**备选方案**：直接重构 `LongTermMemoryStore` 替换底层存储 → 拒绝，原因：无法解决架构碎片化，也无法预留扩展槽位。

---

### 决策 3：科研字段作为 `sci_metadata` JSON 列 vs 专用结构化表

**选择**：通用 `facts` 表 + `sci_metadata TEXT DEFAULT '{}'` JSON 列，通过 `json_extract()` 过滤。

**理由**：
- 科研字段集合随分析类型变化（t 检验有 `t_statistic`，回归有 `r_squared`），结构化表需要频繁 ALTER TABLE 或稀疏宽表
- SQLite JSON1 扩展（标准库自带）支持 `json_extract(sci_metadata, '$.p_value')` 和表达式索引，查询性能满足需求
- `facts` 表保持与 hermes-agent holographic 插件的 schema 兼容，未来接入外部 provider 时减少映射成本

**备选方案**：独立 `scientific_facts` 表，包含所有科研字段列 → 拒绝，原因：字段稀疏、扩展性差，且与通用层割裂无法统一 FTS5 索引。

---

### 决策 4：FTS5 降级策略

**选择**：启动时探测 FTS5 可用性，不可用时降级为 `LIKE` 匹配，不阻止 agent 启动。

**理由**：部分 Linux 发行版的 SQLite 编译版本不含 FTS5 模块。降级而非失败是 nini「本地优先」精神的体现：功能降级但不中断。

---

### 决策 5：Memory Context Fencing

**选择**：`MemoryManager.prefetch_all()` 返回原始文本，调用方统一经 `build_memory_context_block()` 包裹为 `<memory-context>` 标签。

**理由**：防止 LLM 把历史记忆误当作当前用户输入处理。`<memory-context>` 标签 + 系统注记（「非用户新输入，仅作参考背景」）在 hermes-agent 中已验证有效。现有的 `format_untrusted_context_block("long_term_memory", ...)` 在降级路径中保留，P5 阶段统一删除。

---

### 决策 6：`on_session_end` 双路径并行

**选择**：P4 阶段在 `runner.py` 的会话结束处，同时保留旧的 `consolidate_session_memories`（JSONL 路径）和新的 `MemoryManager.on_session_end()`（SQLite 路径），两者均以 `asyncio.create_task` 后台执行。

**理由**：P5 删除旧路径前，双写保证数据不丢失；回滚时注释新路径即可，零破坏性。

---

## Risks / Trade-offs

| 风险 | 缓解措施 |
|---|---|
| SQLite WAL 锁竞争（多会话并发写 `nini_memory.db`） | `timeout=10.0` 参数；`sync_turn` 写入轻量，争用概率低 |
| FTS5 在目标 SQLite 版本不可用 | 启动时探测，自动降级为 `LIKE` 匹配 |
| `on_session_end` 增加会话关闭延迟 | `asyncio.create_task` 后台执行，不阻塞 WebSocket 关闭响应 |
| 迁移幂等失败导致重复记忆条目 | `dedup_key UNIQUE` 约束，`INSERT OR IGNORE`；迁移失败记录警告，不阻止启动 |
| `sync_turn` 正则误触发（非统计文本命中 p 值规则） | `importance < 0.4` 门槛过滤；FTS5 重排序进一步压制低质量条目 |

**主要 trade-off**：双路径并行（P4）期间磁盘写入翻倍，直到 P5 删除旧路径。对本地单机场景可接受。

---

## Migration Plan

**P1–P3（纯新增，零风险）**：创建新模块和测试，不触碰任何现有文件。

**P4（Agent 接入，双路径）**：
1. `runner.py` 添加 `MemoryManager` 初始化，注入 system_prompt 快照
2. `context_memory.py` 和 `context_builder.py` 各添加 try/except 优先路径，失败自动降级
3. `runner.py` 会话结束处增加 `MemoryManager.on_session_end()` 后台任务（保留旧路径）

**回滚方案**：P1–P3 为纯新增，直接 revert PR 无副作用。P4 的两处优先路径均在 `try/except` 内，失败自动降级到旧行为。极端情况下注释 `context_memory.py` 和 `context_builder.py` 中的新路径 try 块即可完全回退，无需 revert 整个 PR。

**P5（清理，独立 PR）**：验收测试全部通过后，删除 `long_term_memory.py`、`research_profile.py`、`profile_narrative.py`、`knowledge.py` 及旧路径调用。

**数据迁移（自动）**：`MemoryStore.__init__()` 首次初始化时自动读取 `long_term_memory/entries.jsonl` 和 `profiles/*.json`，幂等写入 SQLite，原文件保留不删除。

---

## Open Questions

无待决事项。实施前已确认：
- `session.messages` 是 `Session` 类的直接列表属性（非 `get_messages()` 方法）
- FTS5 降级路径使用 `LIKE` 匹配（参考 `memory/db.py` 现有逻辑）
- `build_memory_context_block` 替代 `format_untrusted_context_block`，两者标签不同（`<memory-context>` vs `<untrusted-context>`），P5 前双方均保留
