## ADDED Requirements

### Requirement: 工具暴露策略必须在本轮运行前计算
系统 SHALL 在每轮 agent 运行开始前，根据任务阶段、风险等级和授权状态计算本轮可见工具面，而不是仅在工具执行时被动拦截。

#### Scenario: 运行前裁剪可见工具面
- **WHEN** 新的一轮 agent 运行即将开始
- **THEN** 系统 SHALL 基于当前运行上下文计算本轮 `ToolExposurePolicy`
- **AND** 仅将策略允许的工具暴露给模型

#### Scenario: 工具暴露策略不替代语义规划
- **WHEN** 系统计算本轮 `ToolExposurePolicy`
- **THEN** 策略 SHALL 仅负责移除当前阶段不应出现的工具
- **AND** SHALL NOT 用简单关键词匹配直接替代模型对分析方法的语义判断

### Requirement: 工具暴露策略必须支持阶段化工具池
系统 SHALL 至少支持按 `profile`、`analysis` 和 `export` 三类阶段裁剪当前工具面。

#### Scenario: profile 阶段暴露最小工具面
- **WHEN** 当前阶段为数据概览或前置确认阶段
- **THEN** 系统 SHALL 仅暴露完成概览、任务状态和必要用户确认所需的最小工具集
- **AND** SHALL NOT 暴露与导出或复杂脚本执行无关的高风险工具

#### Scenario: export 阶段只暴露导出相关工具
- **WHEN** 当前阶段为导出或交付阶段
- **THEN** 系统 SHALL 暴露报告、图表或工作区导出相关工具
- **AND** SHALL 收缩与前置数据分析无关的工具面

### Requirement: 工具暴露策略必须考虑授权状态
系统 SHALL 在生成本轮工具面时考虑用户授权状态，对未授权的高风险操作做前置收缩或替换为确认路径。

#### Scenario: 未授权时不暴露高风险导出或写入操作
- **WHEN** 本轮涉及高风险写入、整理或导出操作且当前会话未获得对应授权
- **THEN** 系统 SHALL 不直接暴露该高风险操作
- **AND** SHALL 暴露确认路径或等价的安全占位行为

#### Scenario: 已授权时可恢复对应工具暴露
- **WHEN** 会话已获得某类高风险工具的会话级授权
- **THEN** 系统 SHALL 在后续轮次中恢复该类工具的可见性
- **AND** SHALL 保留可追踪的授权来源
