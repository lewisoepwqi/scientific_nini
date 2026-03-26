## Why

C1 在提示词层面定义了实验设计阶段策略（问题定义→设计选择→参数计算→方案生成），C3 为 `research_planning` Capability 标注了 phase=experiment_design 和 risk_level=high。但目前没有实际的 Skill 工作流支撑实验设计能力。本 change 创建第一个使用 C4 Skill 契约的 Markdown Skill——`experiment-design-helper`，实现 L1 级别的实验设计引导能力。

## What Changes

- **新建 Markdown Skill**：在 `.nini/skills/experiment-design-helper/SKILL.md` 中创建实验设计引导 Skill，包含 contract 段声明步骤 DAG、trust_ceiling=t1、review_gate 在方案生成步骤。
- **Skill 正文工作流**：提供实验设计四步骤的提示词引导（问题定义、设计选择、参数计算、方案生成），每步包含 LLM 提示模板和输出规范。
- **新增样本量计算工具**：在 `tools/` 中新增 `sample_size` 工具，基于效应量、显著性水平和功效计算样本量（使用 statsmodels 或 scipy）。

## Non-Goals

- 不实现 L2/L3 级别的自动化实验设计。
- 不实现伦理审查自动化（仅提示需人工提交 IRB）。
- 不实现与实验管理系统的集成。

## Capabilities

### New Capabilities

- `experiment-design-skill`: 实验设计引导 Skill——涵盖四步骤工作流、contract 契约、review_gate、样本量计算工具

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`.nini/skills/experiment-design-helper/SKILL.md`（新建）、`src/nini/tools/sample_size.py`（新建）、`src/nini/tools/registry.py`（注册新工具）
- **影响范围**：新增一个可调用的 Skill 和一个 Tool，不影响现有功能
- **API / 依赖**：依赖 statsmodels（已是现有依赖），无新增外部依赖
- **风险**：实验设计涉及高风险判断，通过 trust_ceiling=t1 和 review_gate 限制输出等级为 O2 草稿级
- **回滚**：删除新建的 Skill 文件和 Tool 文件即可恢复
- **验证方式**：单元测试验证 sample_size 工具计算准确性；集成测试验证 Skill contract 可解析、步骤可执行
