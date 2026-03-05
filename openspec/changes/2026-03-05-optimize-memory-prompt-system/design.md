## Context

Nini 记忆系统的基础设施已建齐：`LongTermMemoryStore` 支持向量+关键词双路检索，`AnalysisMemory` 在会话内记录结构化分析发现，`PromptBuilder` 提供组件化系统提示词装配。但代码对比显示三处断层：

1. `context_builder.py` 的 `build_messages_and_retrieval()` 从未调用长期记忆检索。`memory.md` 组件在 `builder.py` 中是硬编码的静态占位符 "长期记忆：当前会话未提供额外长期记忆"，与 `LongTermMemoryStore` 完全解耦。

2. 会话内 `AnalysisMemory`（Finding/Statistic/Decision/Artifact）在会话结束后无自动提取路径，所有结构化分析发现随会话关闭沉默，不进入跨会话长期记忆。

3. `LongTermMemoryStore.search()` 的排序公式为 `importance_score × (1 + access_count × 0.1)`，不考虑当前数据集/分析类型情境，也无时间衰减，旧记忆的重要性分值不随时间递减。

同时，压缩摘要的 `_LLM_SUMMARY_PROMPT` 对科研数值（p 值、效应量、置信区间）无强制保留要求，`strategy.md` 的 PDCA 复盘阶段缺少从用户目标出发的逆向验证。

## Goals / Non-Goals

**Goals:**

- 将长期记忆检索结果接入 Agent 每次调用的运行时上下文，使积累的历史分析发现真正影响推理。
- 会话正常结束时自动将高置信度 AnalysisMemory 条目沉淀为跨会话长期记忆。
- 检索时加入情境感知权重（当前数据集/分析类型）和时间衰减，提升检索精度并防止旧记忆污染。
- 压缩摘要提示词明确保留科研数值细节，防止关键统计量在会话压缩中丢失。
- strategy.md 的 PDCA 复盘段追加目标逆向验证，确保 Agent 从用户研究目标出发检验完成度。

**Non-Goals:**

- 不引入新的向量数据库或图数据库依赖，复用现有 `VectorKnowledgeStore`。
- 不修改 `memory.md` 文件组件的优先级（保持 20）和截断行为。
- 不实现跨用户共享记忆或联邦学习类功能。
- 不重构现有 `AnalysisMemory` 数据结构，仅在其上层添加提取逻辑。

## Decisions

### 决策 1：长期记忆注入为运行时 context_parts，而非 memory.md 组件文件

**决定**：在 `context_memory.py` 中新增 `build_long_term_memory_context()`，在 `context_builder.py` 的 `build_messages_and_retrieval()` 中调用，结果追加到 `context_parts`，以 `format_untrusted_context_block("long_term_memory", ...)` 包裹注入运行时上下文消息。

**原因**：`memory.md` 是系统提示词组件（静态、启动时读取），而长期记忆检索是每次请求动态执行的。将其放入 `context_parts` 符合现有运行时上下文构建模式（与 `analysis_memory`、`research_profile`、`agents_md` 一致），且自动受 `compose_runtime_context_message()` 管理。

**备选方案**：直接写入 `memory.md` 文件后再由 `PromptBuilder` 读取。放弃原因：在高并发场景下文件写入有竞争风险，且绕过了已有的运行时上下文安全标签机制。

### 决策 2：会话沉淀触发点在 AgentRunner 的 `_finalize_session()` 阶段

**决定**：在 `runner.py` 中识别 Agent 响应完成（无 tool_calls 的最终回复）时，异步调用 `consolidate_session_memories(session_id)`，提取 `AnalysisMemory` 中 `confidence ≥ 0.7` 的条目写入长期记忆。

**原因**：AgentRunner 已有完整的会话完成判断逻辑，在此钩子后触发沉淀不影响正常响应路径（异步执行，不阻塞 WebSocket 推送）。

**备选方案**：在 `organize_workspace` 工具中触发。放弃原因：用户不一定每次都调用 organize_workspace，而每次分析结束时 AgentRunner 一定会到达无 tool_call 的终止状态。

### 决策 3：时间衰减在检索时动态计算，不修改存储格式

**决定**：`search()` 中引入 `_compute_effective_score(entry)` 函数，计算 `importance_score × e^(-λ × days_elapsed)`，λ=0.01（约 100 天后重要性衰减到原来的 37%）。`access_count > 5` 的条目 λ 减半。

**原因**：无需迁移现有存储数据，衰减参数可在代码层调整，符合"渐进增强"原则。

### 决策 4：情境权重作为可选参数，不破坏现有调用

**决定**：`search()` 新增可选 `context: dict[str, Any] | None = None` 参数，当调用方传入 `dataset_name` 或 `analysis_type` 时激活权重加成；不传时行为与旧版一致。

**原因**：保证向后兼容，现有调用（如测试）无需修改。

## Risks / Trade-offs

- [风险：长期记忆检索增加每次请求延迟] → 异步检索 + 最多 top-3 条目 + 向量不可用时回退关键词匹配，延迟可控（预期 < 50ms）。
- [风险：低质量记忆被注入污染上下文] → 只注入 `importance_score >= 0.3` 且经时间衰减后分值仍高于阈值的条目；注入内容包裹在 `untrusted` 标签内，受现有安全策略保护。
- [风险：会话沉淀异步失败未被感知] → `consolidate_session_memories()` 内部 try/except 记录 warning，不抛出，不阻断正常流程。
- [风险：压缩摘要 token 增加导致上限不足] → 上限从 500 字放宽到 600 字；按 GPT-4 均值 1.5 字/token 估算，增量约 67 tokens，在摘要压缩本身节省的 token 量中可忽略。

## Open Questions

- `consolidate_session_memories()` 是否需要去重检测（避免同一发现在多次分析后被重复写入长期记忆）？当前方案不做去重，依赖时间衰减自然降权，后续可视积累量决定是否加 embedding 相似度去重。
- 长期记忆的 `min_importance` 检索过滤阈值是否需要暴露为配置项？当前硬编码 0.3，可在后续迭代中移至 `settings`。
