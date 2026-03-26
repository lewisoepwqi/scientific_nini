# l1-baseline-validation Specification

## Purpose
TBD - created by archiving change add-phase-navigation-and-l1-baseline. Update Purpose after archive.
## Requirements
### Requirement: 新阶段 Skill 可用性验证
L1 基线测试 SHALL 验证三个新 Skill（experiment-design-helper、literature-review、writing-guide）均可被 markdown_scanner 发现且 contract 可解析。

#### Scenario: 三个 Skill 均注册成功
- **WHEN** 运行 Skill 扫描
- **THEN** experiment-design-helper、literature-review、writing-guide 均出现在注册列表中

#### Scenario: 三个 Skill 的 contract 均有效
- **WHEN** 解析三个 Skill 的 contract
- **THEN** 每个 contract 的 steps 非空且拓扑排序无报错

### Requirement: 阶段检测准确性验证
L1 基线测试 SHALL 验证 detect_phase 对典型消息的检测准确性，准确率不低于 80%。

#### Scenario: 典型消息准确检测
- **WHEN** 使用预定义的 20 条典型消息测试 detect_phase
- **THEN** 至少 16 条返回正确的阶段

### Requirement: 阶段路由集成验证
L1 基线测试 SHALL 验证 context_builder 在检测到不同阶段时，正确注入阶段信息和推荐列表。

#### Scenario: 实验设计阶段推荐正确
- **WHEN** 当前阶段为 experiment_design
- **THEN** 推荐列表中包含 research_planning Capability 和 experiment-design-helper Skill

#### Scenario: 数据分析阶段推荐保持不变
- **WHEN** 当前阶段为 data_analysis
- **THEN** 推荐列表与现有逻辑一致，不引入新阶段 Skill 的干扰

