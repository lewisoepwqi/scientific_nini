# phase-detection Specification

## Purpose
TBD - created by archiving change add-phase-navigation-and-l1-baseline. Update Purpose after archive.
## Requirements
### Requirement: detect_phase 工具
系统 SHALL 提供 `detect_phase` 工具，基于用户消息内容检测当前研究阶段，返回 ResearchPhase 值。

#### Scenario: 文献调研关键词匹配
- **WHEN** 用户消息包含「文献综述」「文献调研」「相关研究」等关键词
- **THEN** 返回 ResearchPhase.literature_review

#### Scenario: 实验设计关键词匹配
- **WHEN** 用户消息包含「实验设计」「样本量」「研究方案」等关键词
- **THEN** 返回 ResearchPhase.experiment_design

#### Scenario: 论文写作关键词匹配
- **WHEN** 用户消息包含「写论文」「论文写作」「方法章节」等关键词
- **THEN** 返回 ResearchPhase.paper_writing

#### Scenario: 默认阶段
- **WHEN** 用户消息无法匹配任何特定阶段
- **THEN** 返回 ResearchPhase.data_analysis（默认阶段）

### Requirement: 阶段信息上下文注入
`context_builder.py` SHALL 在运行时上下文中包含当前检测到的阶段信息。

#### Scenario: 上下文包含阶段
- **WHEN** Agent 处理用户消息时构建上下文
- **THEN** 运行时上下文中包含 current_phase 字段

#### Scenario: 推荐列表按阶段排序
- **WHEN** 当前阶段为 experiment_design
- **THEN** 推荐的 Capability/Skill 列表中，阶段匹配的排在前面

### Requirement: 工具注册
detect_phase SHALL 在 `tools/registry.py` 中注册。

#### Scenario: 工具可查询
- **WHEN** 从 ToolRegistry 中查询 "detect_phase"
- **THEN** 返回对应的 Tool 实例

