## 1. 长期记忆运行时注入

- [x] 1.1 在 `src/nini/agent/components/context_memory.py` 中新增 `build_long_term_memory_context()` 异步函数，调用 `search_long_term_memories(query, top_k=3)`，用 `format_untrusted_context_block("long_term_memory", ...)` 包裹结果
- [x] 1.2 在 `src/nini/agent/components/context_builder.py` 的 `build_messages_and_retrieval()` 中调用上述函数，将结果追加到 `context_parts`（位于 `analysis_memory_context` 之后）

## 2. 情境感知检索与时间衰减

- [x] 2.1 在 `src/nini/memory/long_term_memory.py` 中新增 `_compute_effective_score(entry, context)` 函数，实现指数衰减打分（λ=0.01，高频访问条目 λ 减半）
- [x] 2.2 为 `LongTermMemoryStore.search()` 新增可选 `context: dict[str, Any] | None = None` 参数，当 `context` 包含 `dataset_name` 或 `analysis_type` 时对命中条目给予权重加成（×1.5 / ×1.3）
- [x] 2.3 将排序 key 从旧公式替换为 `_compute_effective_score()` 返回值

## 3. 会话记忆自动沉淀

- [x] 3.1 在 `src/nini/memory/long_term_memory.py` 中新增 `consolidate_session_memories(session_id: str) -> int` 函数，遍历 `list_session_analysis_memories(session_id)`，将 `confidence >= 0.7` 的 Finding/Statistic/Decision 条目写入 `LongTermMemoryStore`，返回写入条数
- [x] 3.2 在 `src/nini/agent/runner.py` 的 Agent 响应完成钩子处（无 tool_calls 最终回复后），以 `asyncio.create_task()` 异步触发 `consolidate_session_memories(session.id)`，异常仅记录 warning

## 4. 用户画像运行时注入

- [x] 4.1 在 `src/nini/agent/components/context_memory.py` 中实现 `build_research_profile_context()`，通过 `format_untrusted_context_block("research_profile", ...)` 包裹用户研究画像内容
- [x] 4.2 在 `src/nini/agent/components/context_builder.py` 的 `build_messages_and_retrieval()` 中调用上述函数，将结果追加到 `context_parts`

## 5. 压缩摘要提示词强化

- [x] 5.1 更新 `src/nini/memory/compression.py` 中的 `_LLM_SUMMARY_PROMPT`，明确要求保留：具体统计数值（检验统计量/p 值/效应量/置信区间）、已选方法及选择理由、当前未完成任务，摘要上限调整为 600 字

## 6. strategy.md 目标逆向验证

- [x] 6.1 在 `src/nini/agent/prompts/builder.py` 的 `_DEFAULT_COMPONENTS["strategy.md"]` 中，`【Check 复盘】` 段落追加目标逆向验证要求（Goal-Backward Check：分析结论是否回应用户研究问题、产出物是否足以支撑决策）

## 7. 测试

- [x] 7.1 新增 `tests/test_long_term_memory.py`，覆盖：时间衰减打分、情境权重加成、`search()` 新参数的向后兼容性
- [x] 7.2 新增 `tests/test_memory_consolidation.py`，覆盖：`consolidate_session_memories()` 的置信度过滤、写入计数、异常时不抛出
- [x] 7.3 新增 `tests/test_context_memory_injection.py`，覆盖：`build_long_term_memory_context()` 返回非空时被包裹在 `untrusted` 标签内、无记忆时返回空字符串
