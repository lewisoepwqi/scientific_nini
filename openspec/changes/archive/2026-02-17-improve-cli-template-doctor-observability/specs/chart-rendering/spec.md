## ADDED Requirements

### Requirement: 图表默认配置降级可观测
系统 MUST 在图表默认样式配置发生异常时记录可观测日志，并继续执行后续流程。

#### Scenario: Matplotlib 默认配置异常时记录日志并降级
- **WHEN** Matplotlib 默认样式设置阶段抛出异常
- **THEN** 系统记录包含异常信息的降级日志
- **AND** 不中断后续代码执行

#### Scenario: Plotly 默认配置异常时记录日志并降级
- **WHEN** Plotly 默认样式设置阶段抛出异常
- **THEN** 系统记录包含异常信息的降级日志
- **AND** 不中断后续代码执行
