## Why

根据对 `memory/` 目录下四份调研报告（mem0、momOS、Memary 记忆系统分析 + GSD Agent 上下文工程分析）的深度梳理，发现 Nini 记忆系统存在一个核心断层：**基础设施已建好，但未接通**。具体表现为：`LongTermMemoryStore` 具备完整检索能力但从未注入系统提示词；`AnalysisMemory` 在会话结束后无自动沉淀通道；长期记忆排序不考虑当前情境，也无时间衰减机制。同时，压缩摘要提示词对科研数值保留要求不明确，strategy.md 的 PDCA 复盘阶段缺少从用户目标出发的逆向验证。如果不解决上述问题，系统将积累大量"沉默记忆"——数据已写入磁盘，但从未对 Agent 的推理产生任何影响。

## What Changes

- **长期记忆运行时注入**：在 `context_memory.py` 中新增 `build_long_term_memory_context()`，在每次 Agent 处理用户消息前以当前消息为 query 检索 top-3 长期记忆，通过 `format_untrusted_context_block("long_term_memory", ...)` 注入运行时上下文（`context_parts`），与现有 `analysis_memory`、`research_profile` 注入模式一致
- **会话记忆自动沉淀**：Agent 响应完成时，异步调用 `consolidate_session_memories(session_id)`，将 `AnalysisMemory` 中 `confidence ≥ 0.7` 的 Finding/Statistic/Decision 条目写入 `LongTermMemoryStore`
- **情境感知 + 时间衰减评分**：`LongTermMemoryStore.search()` 引入可选 `context` 参数（当前数据集/分析类型），对匹配条目给予权重加成；同时引入指数衰减 `score = importance × e^(-λ × days)`，高访问频次条目衰减速率减半
- **用户画像运行时注入**：`build_research_profile_context()` 通过 `format_untrusted_context_block("research_profile", ...)` 将用户研究画像注入 `context_parts`
- **压缩摘要科研增强**：`_LLM_SUMMARY_PROMPT` 明确要求保留具体统计数值（检验统计量/p值/效应量/置信区间）、已选方法及选择理由、当前未完成任务，上限放宽至 600 字
- **strategy.md 目标逆向验证**：`builder.py` 的 `_DEFAULT_COMPONENTS["strategy.md"]` 中 `【Check 复盘】` 阶段追加 Goal-Backward Check，要求验证分析结论是否回应用户最初的研究问题、产出物是否足以支撑决策

## Capabilities

### New Capabilities

- `dynamic-memory-injection`: 基于当前用户消息动态检索长期记忆，通过 `context_parts` 注入运行时上下文（`format_untrusted_context_block` 包裹）
- `memory-session-extraction`: 会话结束时自动将高置信度 AnalysisMemory findings 提取到长期记忆存储
- `context-aware-memory-ranking`: 长期记忆检索的情境加权（数据集/分析类型匹配提升）与时间衰减复合评分
- `user-profile-injection`: 用户研究画像通过 `context_parts` 动态注入运行时上下文

### Modified Capabilities

- `prompt-system-composition`: memory.md 组件保持静态；长期记忆与用户画像改为通过运行时上下文消息（context_parts）注入，而非修改系统提示词组件文件

## Impact

- **后端代码**：`agent/components/context_memory.py`（主要）、`agent/components/context_builder.py`（调用注入）、`agent/runner.py`（会话沉淀钩子）、`memory/long_term_memory.py`（检索评分 + 沉淀函数）、`memory/compression.py`（压缩提示词）、`agent/prompts/builder.py`（strategy.md 默认内容）
- **调用链变化**：`ContextBuilder.build_messages_and_retrieval()` 新增长期记忆检索和用户画像调用
- **无 API 变化**：全部改动在服务端内部，WebSocket 事件协议无变化
- **存储兼容**：`LongTermMemoryEntry` 格式不变，仅修改检索排序逻辑
- **依赖新增**：无新外部依赖
