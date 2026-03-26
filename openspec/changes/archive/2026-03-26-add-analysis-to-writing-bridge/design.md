## Context

现有 `article-draft` Skill 是提示词驱动的论文生成工作流。`methods_ledger`（`models/session_resources.py`）已在会话中记录统计方法使用情况。`workspace/manager.py` 管理会话产物（图表、数据文件、报告）。`evidence_traceability` spec 定义了证据溯源机制。这些现有基础设施为写作桥接提供了数据来源。

## Goals / Non-Goals

**Goals:**
- 创建 writing-guide Skill（带 contract）
- 实现 collect_artifacts 工具（从会话收集分析产物）
- 利用现有 methods_ledger 和 workspace 基础设施

**Non-Goals:**
- 不实现 LaTeX/Word 格式化
- 不替代现有 article-draft Skill

## Decisions

### D1: Skill 契约设计

**选择**：四步线性 DAG，trust_ceiling=t1：

```
collect_materials → plan_structure → write_sections → review_revise
```

- `collect_materials`：调用 collect_artifacts 工具，收集当前会话中的统计结果、图表 URL、方法记录
- `plan_structure`：LLM 基于素材包推荐论文结构（章节大纲）
- `write_sections`：LLM 逐章节引导用户撰写，嵌入统计结果和图表引用
- `review_revise`：LLM 对已写章节提供修订建议，检查数据-结论一致性

**理由**：与 C1 strategy 中论文写作策略的四步流程（结构规划→分节撰写→修订→格式化）对应。格式化步骤（LaTeX/Word 导出）不在 V1 范围。

### D2: collect_artifacts 工具设计

**选择**：继承 Tool 基类，从 Session 中收集：
1. 已执行的统计检验结果（从 tool_call 历史提取）
2. 已生成的图表列表及 URL（从 workspace artifacts 提取）
3. 方法记录（从 MethodsLedgerEntry 提取）
4. 数据集概要（从 loaded datasets 提取）

返回结构化的「写作素材包」JSON。

**理由**：利用现有会话状态和 workspace 管理机制，不引入新的存储依赖。素材包为 JSON 格式，便于 LLM 消费。

### D3: 与现有 article-draft Skill 的关系

**选择**：writing-guide 是新的独立 Skill，不修改 article-draft 的行为。两者区别：
- `article-draft`：整体生成（LLM 自主完成全文初稿），适合快速出稿
- `writing-guide`：分步引导（每步与用户交互），适合深度写作

**理由**：两种使用模式并存，满足不同用户需求。不强制迁移现有 Skill。

### D4: 无分析结果时的降级

**选择**：collect_materials 步骤检测会话中是否有分析产物。若无，收集步骤输出空素材包，后续步骤切换为纯引导模式（不引用统计结果，仅提供结构和写作建议）。

**理由**：用户可能直接使用写作引导而未先做数据分析。降级模式仍有价值。

## Risks / Trade-offs

- **[风险] 会话中的分析产物结构不统一** → collect_artifacts 对不同类型的产物分别处理，缺失字段用 null 填充。
- **[风险] LLM 引导写作的质量依赖提示词** → trust_ceiling=t1，所有输出标注 O2 草稿级。
- **[回滚]** 删除新建文件 + revert registry.py 即可恢复。
