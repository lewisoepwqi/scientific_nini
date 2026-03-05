## Why

根据对 `memory/` 目录下四份调研报告（mem0、momOS、Memary 记忆系统分析 + GSD Agent 上下文工程分析）的深度梳理，发现 Nini 记忆系统存在一个核心断层：**基础设施已建好，但未接通**。

具体表现为三点：

1. `LongTermMemoryStore` 具备完整的向量+关键词检索能力，但从未被调用注入到系统提示词——`builder.py` 的 `memory.md` 组件仍是静态占位符 "当前会话未提供额外长期记忆"。
2. `AnalysisMemory`（会话内结构化记忆：Finding/Statistic/Decision/Artifact）与 `LongTermMemoryStore`（跨会话持久化）之间没有自动转化通道，每次会话结束后本次分析发现无法自动沉淀为可被后续会话检索的知识。
3. 长期记忆的重排序逻辑未考虑当前情境（数据集、分析类型），导致检索精度有限；且没有时间衰减机制，旧记忆的重要性不随时间递减，存在噪声污染风险。

同时，调研报告揭示了两处提示词设计可低成本优化的点：`strategy.md` 的 PDCA 复盘环节缺少"目标逆向验证"，压缩摘要的 LLM 提示词对科研场景的数值结果（p 值、效应量、置信区间）保留要求不够明确。

如果不解决上述问题，随着用户使用频次增加，系统将积累大量"沉默记忆"——数据已写入磁盘，但从未对 Agent 的推理产生任何影响。

## What Changes

### 记忆动态注入（Memory Dynamic Injection）
- `memory.md` 提示词组件从静态占位改为运行时动态填充：每次 Agent 开始处理用户消息前，以当前消息为 query 检索 top-3 长期记忆，注入 `memory.md` 组件
- 在 `context_memory.py` 中实现检索+格式化逻辑，调用现有 `search_long_term_memories()` 与 `format_memories_for_context()`

### 会话记忆自动沉淀（Session Memory Consolidation）
- 会话正常结束时（`organize_workspace` 工具或 `AgentRunner` 会话终止钩子），自动将本次 `AnalysisMemory` 中置信度 ≥ 0.7 的 Finding/Statistic/Decision 条目写入 `LongTermMemoryStore`
- 利用现有 `extract_memories_with_llm()` 处理无结构化记忆的兜底场景

### 情境感知重排序（Context-Aware Reranking）
- `LongTermMemoryStore.search()` 接受可选 `context` 参数（当前 `dataset_name`、`analysis_type`）
- 排序时对命中当前数据集或分析类型的条目给予权重加成（参考 mem0 的情境感知检索设计）

### 记忆时间衰减（Time-Based Decay）
- 在检索排序时引入指数衰减打分：`score = importance × e^(-λ × days_elapsed)`，λ 默认 0.01
- 对高访问频次（`access_count > 5`）条目降低衰减速率，模拟"反复强化巩固"效应
- 无需变更存储格式，仅修改排序计算逻辑

### 压缩摘要提示词强化（Compression Prompt Enhancement）
- 在 `_LLM_SUMMARY_PROMPT` 中明确要求保留：具体统计数值（t/F/χ² 统计量、p 值、效应量、置信区间）、已选方法及选择理由、当前未完成任务
- 将摘要上限从 500 字适当放宽到 600 字以容纳数值细节

### strategy.md 目标逆向验证补充（Goal-Backward Check）
- 在 PDCA `【Check 复盘】` 阶段追加：验证分析结论是否回应了用户最初的研究问题、产出物是否足以支撑决策
- 借鉴 GSD 调研报告中的 Goal-Backward Methodology，从目标出发而非仅从任务列表出发检验完成度

## Capabilities

### New Capabilities
- `memory-active-injection`: 定义长期记忆在 Agent 运行时的检索、格式化与注入提示词的完整契约，包括触发时机、检索参数、注入位置与截断行为。
- `memory-session-consolidation`: 定义会话结束时 AnalysisMemory → LongTermMemory 自动沉淀的触发条件、过滤规则（置信度阈值）与失败兜底策略。

### Modified Capabilities
- `conversation`: 运行时上下文构建需在 `memory.md` 组件位置注入动态检索结果，而非静态文本。
- `prompt-system-composition`（若存在）：`memory.md` 从"低优先级静态组件"升级为"低优先级动态组件"，截断优先级保持不变（20），但内容来源变为运行时检索。

## Impact

### 后端代码
- `src/nini/agent/components/context_memory.py`：新增长期记忆检索+格式化注入逻辑（主要改动）
- `src/nini/agent/runner.py`：会话结束钩子触发 AnalysisMemory 沉淀（次要改动）
- `src/nini/memory/long_term_memory.py`：`search()` 方法新增 `context` 参数、情境权重与时间衰减打分
- `src/nini/memory/compression.py`：`_LLM_SUMMARY_PROMPT` 强化科研数值保留要求
- `src/nini/agent/prompts/builder.py`：`memory.md` 组件加载逻辑调整为接受外部注入内容

### 提示词组件
- `strategy.md` 默认内容：`【Check 复盘】` 段落追加目标逆向验证要求

### 测试
- `tests/test_memory_*.py`：新增记忆注入、沉淀、衰减、情境排序的单元测试
- 现有 `tests/test_prompt_guardrails.py`：确认 memory 注入不引入不可信内容（注入内容需经安全标签包裹）

### 依赖
- 无新增外部依赖；所有改动基于现有 `VectorKnowledgeStore`、`LongTermMemoryStore`、`AnalysisMemory` 已有实现
