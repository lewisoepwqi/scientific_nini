## Context

C3 定义了 `ResearchPhase` 枚举和 Capability 的阶段标注。C6/C7/C8 创建了三个新阶段 Skill。`context_builder.py` 已负责向 Agent 注入运行时上下文（数据集、技能列表、知识库等）。本 change 在此基础上增加阶段感知能力。

## Goals / Non-Goals

**Goals:**
- 实现基于消息的阶段自动检测
- 在 Agent 上下文中注入阶段信息
- 创建 L1 基线验收测试

**Non-Goals:**
- 不实现自动阶段流转
- 不实现前端 UI

## Decisions

### D1: 阶段检测策略

**选择**：关键词匹配 + LLM 意图分类的混合策略。

1. **快速路径**：基于用户消息的关键词匹配，将常见表达映射到 ResearchPhase（如「文献综述」→ literature_review，「样本量」→ experiment_design，「写论文」→ paper_writing）。
2. **默认路径**：无匹配时默认为 data_analysis（核心优势阶段）。

实现为 `detect_phase` Tool，返回 `ResearchPhase` 值和置信度。

**理由**：V1 用关键词匹配足够覆盖常见场景。不引入额外 LLM 调用开销。后续可升级为 LLM 意图分类。

### D2: 上下文注入方式

**选择**：在 `context_builder.py` 的上下文构建流程中，调用 detect_phase 获取当前阶段，然后：
1. 在运行时上下文中注入 `current_phase` 字段
2. 根据阶段过滤并排序推荐的 Capability/Skill 列表（阶段匹配的排前面）
3. 在策略提示中附加该阶段的条件触发说明（引用 C1 strategy.md 中的阶段策略）

**理由**：复用现有 context_builder 机制，最小改动。阶段信息作为运行时上下文的一部分，不修改 System Prompt 层。

### D3: L1 基线测试设计

**选择**：创建 `tests/test_l1_baseline.py`，包含三类端到端测试：

1. **阶段检测准确性**：给定典型用户消息，验证 detect_phase 返回正确阶段
2. **Skill 可用性**：验证三个新 Skill（experiment-design-helper、literature-review、writing-guide）可被扫描发现且 contract 可解析
3. **阶段路由集成**：验证阶段检测后，context_builder 正确注入阶段信息和推荐列表

**理由**：L1 基线测试不要求端到端 LLM 交互（成本高），而是验证基础设施层面的正确性。

## Risks / Trade-offs

- **[风险] 关键词匹配误判** → 误判仅影响推荐排序，不阻断功能。默认 data_analysis 保护最核心的使用场景。
- **[风险] context_builder 注入增加 token 消耗** → 阶段信息约 50 tokens，在 Runtime Context 预算内。
- **[回滚]** 删除新建文件 + revert context_builder.py 即可恢复。
