## ADDED Requirements

### Requirement: CLI 诊断必须支持运行快照摘要
系统 MUST 提供基于运行快照的 CLI 诊断入口，用于查看某个会话或轮次的摘要状态。

#### Scenario: 查看会话最新运行摘要
- **WHEN** 用户通过 CLI 请求某个会话的最新运行摘要
- **THEN** 系统 MUST 输出该会话最近一轮的 stop reason、pending actions、任务进度和关键失败摘要

#### Scenario: 查看指定轮次快照
- **WHEN** 用户通过 CLI 请求某个会话指定轮次的运行快照
- **THEN** 系统 MUST 输出对应轮次的结构化摘要
- **AND** 若轮次不存在，CLI MUST 返回明确的未找到提示

### Requirement: doctor 诊断必须支持 surface 观测
系统 MUST 提供 tools/skills/surface 的 CLI 诊断输出，用于分析当前轮或当前配置下的工具暴露面。

#### Scenario: 查看当前工具面与技能面
- **WHEN** 用户通过 `doctor --surface` 或等价入口请求 surface 诊断
- **THEN** 系统 MUST 输出当前可见工具、技能快照以及高风险工具摘要

#### Scenario: 查看策略过滤后的工具面
- **WHEN** 当前存在基于阶段、风险或授权状态的工具暴露策略
- **THEN** surface 诊断 MUST 输出过滤后的可见工具面
- **AND** MUST 说明哪些工具因策略被移除或隐藏
