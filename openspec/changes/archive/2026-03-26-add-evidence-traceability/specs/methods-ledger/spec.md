## ADDED Requirements

### Requirement: 系统必须记录 METHODS 台账最小字段

系统 SHALL 在深任务执行过程中记录 METHODS 台账，至少包含数据来源、分析步骤、统计方法或工具名称、关键参数、模型版本与执行时间。

#### Scenario: 执行分析步骤后写入 METHODS 台账
- **WHEN** deep task 完成一个会影响研究输出的分析步骤
- **THEN** 系统将该步骤写入 METHODS 台账
- **AND** 记录步骤名称、方法名称、关键参数与执行时间

#### Scenario: 引用模型生成内容时记录模型版本
- **WHEN** 研究输出依赖模型生成解释或文本内容
- **THEN** 系统在 METHODS 台账中记录模型名称或版本标识

### Requirement: METHODS 台账必须可生成 METHODS v1 文本

系统 SHALL 能根据 METHODS 台账生成结构化的 METHODS v1 内容，供报告或导出管线直接引用。

#### Scenario: 报告请求 METHODS 内容
- **WHEN** 报告会话请求生成 METHODS 区块
- **THEN** 系统根据当前台账输出 METHODS v1 文本
- **AND** 内容至少覆盖数据来源、分析流程与关键参数

#### Scenario: METHODS 台账信息不足
- **WHEN** 当前会话缺少完整方法记录
- **THEN** 系统生成部分 METHODS 内容
- **AND** 明确标记缺失字段而不是伪造完整描述
