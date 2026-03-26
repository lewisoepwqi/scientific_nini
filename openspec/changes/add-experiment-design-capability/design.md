## Context

C4 提供了 Skill 执行契约运行时（SkillContract、ContractRunner）。C3 已为 `research_planning` Capability 标注 phase=experiment_design, risk_level=high, max_output_level=o2。现有 `tools/` 中有丰富的统计工具（t_test、anova 等），但缺少样本量计算工具。

## Goals / Non-Goals

**Goals:**
- 创建 experiment-design-helper Skill（带 contract）
- 实现 sample_size 计算工具
- 验证 C4 契约运行时的端到端可用性

**Non-Goals:**
- 不实现自动化实验设计
- 不集成外部实验管理系统

## Decisions

### D1: Skill 契约设计

**选择**：四步线性 DAG，trust_ceiling=t1：

```
define_problem → choose_design → calculate_params → generate_plan
                                                     ↑ review_gate=true
```

- `define_problem`：LLM 引导用户明确研究假设、自变量/因变量、比较目标
- `choose_design`：基于问题类型推荐实验设计（RCT、配对、析因等）
- `calculate_params`：调用 sample_size 工具计算样本量
- `generate_plan`：生成实验方案草稿，标注 O2 草稿级，review_gate=true 触发人工复核

**理由**：线性 DAG 满足 V1 需求。review_gate 在最终方案生成前触发，确保用户在方案定稿前复核。

### D2: sample_size 工具设计

**选择**：继承 `tools/base.py:Tool`，支持常见设计类型：
- 两组均值比较（t 检验功效分析）
- 多组比较（ANOVA 功效分析）
- 比例差异（卡方检验功效分析）

参数：effect_size、alpha（默认 0.05）、power（默认 0.8）、design_type、groups（组数）。

**理由**：使用 `statsmodels.stats.power` 模块（已是项目依赖），不引入新依赖。覆盖最常见的实验设计场景。

### D3: 输出规范

**选择**：所有 Skill 输出标注 O2 草稿级。实验方案包含以下结构：
1. 研究假设
2. 实验设计类型及理由
3. 样本量计算结果及参数
4. 实验步骤概要
5. 伦理提示（如涉及人体/动物实验）
6. 风险提示（局限性声明）

**理由**：L1 级别能力，输出仅供参考和作为用户进一步细化的起点。

## Risks / Trade-offs

- **[风险] 样本量计算参数选择（效应量）需要专业判断** → 在 Skill 步骤中引导用户选择或提供领域常见值参考。
- **[风险] 实验设计推荐可能不适用于特定学科** → 通过提示词强调「建议级，需结合学科特点调整」。
- **[回滚]** 删除 Skill 文件和 sample_size 工具即可恢复。
