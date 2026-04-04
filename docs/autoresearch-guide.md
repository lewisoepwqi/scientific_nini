# Nini Autoresearch 指南（兼容入口）

新文档已迁移到双线结构：

- 总索引：[docs/autoresearch/README.md](/home/lewis/coding/scientific_nini/docs/autoresearch/README.md)
- 第一条 static：[docs/autoresearch/static/PROGRAM.md](/home/lewis/coding/scientific_nini/docs/autoresearch/static/PROGRAM.md)
- 第二条 harness：[docs/autoresearch/harness/PROTOCOL.md](/home/lewis/coding/scientific_nini/docs/autoresearch/harness/PROTOCOL.md)

如果你的目标是：

- 压缩 prompt、工具面、固定 token 开销：走 `static`
- 优化完成率、阻塞率、成本、耗时：走 `harness`

兼容说明：

- 根目录旧文档保留为跳转入口，后续维护只在 `docs/autoresearch/` 下进行

假设你同时精简了 `strategy_core.md`（-200 tokens）和 `strategy_task.md`（-100 tokens），测试失败了 3 个。你无法知道：
- 是 strategy_core 的精简导致的？
- 还是 strategy_task 的精简导致的？
- 还是两者交互导致的？

你不得不回退全部改动。如果分两次实验做，可能 strategy_task 的精简是安全的，你白白浪费了 100 tokens 的收益。

### 测试作为安全护栏

Nini 的 2010 个测试覆盖了 Agent 的核心行为：
- prompt builder 的组装逻辑
- 工具注册与调用
- 意图分类
- 上下文压缩
- 会话管理

当你精简 prompt 时，如果删除了某个关键行为指令（比如"禁止空参数调用"），相关测试会失败。这是你的安全网。

**但测试不是万能的**：测试只能捕获已知的行为回归。如果你删除了一段"建议性"文本（比如"优先使用非参数方法"），测试可能仍然通过，但真实使用时 Agent 的分析质量可能下降。这就是为什么我们强调「只删除明显冗余，保留行为指令」。

### Token 计数的精确性

`measure_baseline.py` 使用 tiktoken 的 GPT-4 编码器。这与 Nini 实际使用的 LLM（可能是不同的模型）编码方式可能不完全一致。但：
- **相对变化是可靠的**：同一编码器下，-81 tokens 就是真实的 -81 tokens
- **绝对值是参考性的**：实际模型可能是 ±10% 的差异
- **没装 tiktoken 时的降级**：`len(text) // 4` 是粗略估算，适合快速迭代但不适合精确对比

### 条件注入机制

不是所有 prompt 组件都会在每次对话中加载：

```python
# builder.py 中的条件注入逻辑
_CONDITIONAL_COMPONENT_KEYWORDS = {
    "strategy_visualization.md": {"chart", "plot", "图", "可视化", ...},
    "strategy_report.md": {"report", "报告", "总结", ...},
    "strategy_phases.md": {"文献", "实验设计", "论文", ...},
}
```

当用户的消息不包含这些关键词时，对应组件不会加载。所以：
- `measure_baseline.py` 固定传入 `{"chart", "stat_test"}`，会加载 `strategy_visualization.md`
- `strategy_report.md` 和 `strategy_phases.md` 不会被加载，精简它们不影响 baseline 测量
- 但它们在运行时仍会被加载，所以精简仍有价值

---

## 六、学习路径

### 阶段 1：理解系统（1-2 小时）

1. **阅读本文档**（你正在看）
2. **阅读 `autoresearch_program.md`** — 理解实验循环
3. **运行一次 `python scripts/measure_baseline.py --compare`** — 亲眼看指标输出
4. **阅读 `results.tsv`** — 理解已有实验的历史

### 阶段 2：理解 Nini 的 prompt 架构（2-3 小时）

1. **阅读 `src/nini/agent/prompts/builder.py`** — PromptBuilder 如何装配 system prompt
   - 重点理解 `_load_components()`、`_filter_conditional_components()`、`_dedupe_paragraphs()`
2. **阅读 `data/prompt_components/strategy_core.md`** — 最大的组件，理解 Nini 的分析流程
3. **阅读 `src/nini/agent/prompt_policy.py`** — 运行时上下文的裁剪机制
   - 重点理解 `RUNTIME_CONTEXT_BLOCK_PRIORITY` 和 `trim_runtime_context_by_priority()`
4. **阅读 `src/nini/tools/registry.py`** — 工具注册，理解 tool_schema_tokens 的来源

### 阶段 3：手动做一个实验（30 分钟）

1. 选一个简单目标：精简 `strategy_visualization.md` 中的一个冗余段落
2. 按 `run_experiment.sh` 跑完整流程
3. 体验 keep/discard 的判定过程

### 阶段 4：让 Agent 自动跑（持续）

1. 把 `AUTORESEARCH_AGENT_PROTOCOL.md` 交给 Claude Code
2. 指示它执行实验循环
3. 监控 `results.tsv` 的变化
4. 每 5-10 个实验做一次人工审查

### 阶段 5：拓展优化维度（进阶）

当 prompt 精简的收益趋于平稳后，可以考虑：
- 优化 `PDCA_DETAIL_BLOCK` 的文本（目前约 2200 字符，条件注入）
- 优化工具定义中的 `parameters` 描述（影响 tool_schema_tokens）
- 调整运行时上下文预算（影响长对话的质量）
- 重新设计条件注入关键词映射（减少误加载）

---

## 七、FAQ

### Q: 为什么不直接用 LLM 评估 prompt 质量？

因为 LLM 评估 prompt 是主观的、不稳定的。Token 数是客观指标，测试通过率是客观指标。我们只优化客观指标。

### Q: 优化 prompt 会不会让 Agent 变笨？

有可能。这就是测试护栏的作用：如果删除了关键指令导致行为退化，测试会失败。但测试无法覆盖所有情况，所以我们强调「只删冗余，不删指令」。

### Q: 一个实验大概能节省多少 token？

从已有数据看：
- 精简 strategy 文本：-50 到 -500 tokens/次
- 降低预算常量：不影响 token 但节省运行时内存
- 精简工具 description：-10 到 -100 tokens/次（但容易触发测试失败）

### Q: results.tsv 里的 exp1/exp2 为什么没有真实 commit hash？

这是早期手动记录的实验。新的 `run_experiment.sh` 会自动用 `git rev-parse --short HEAD` 填入真实 hash。

### Q: 能否并行跑多个实验？

不能。单变量控制要求每次只有一个改动。如果要加速，可以让 Agent 在一个实验的 discard 后立即开始下一个（不需要人工介入）。

### Q: 为什么 baseline 的 test_failed 是 0 但 exp1/exp2 是 6→7？

baseline 是在干净状态下测量的（所有测试通过）。exp1 和 exp2 的改动导致了 6-7 个测试失败（不是原来就有 6 个失败然后变成 7 个，而是原来 0 个失败变成了 6-7 个）。`results.tsv` 中的记录方式可能产生歧义——实际含义是 `test_failed` 从 0 变为 6 或 7。
