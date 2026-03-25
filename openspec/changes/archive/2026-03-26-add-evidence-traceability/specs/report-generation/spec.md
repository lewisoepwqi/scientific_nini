## ADDED Requirements

### Requirement: 报告必须支持 Evidence Block 输出

系统 SHALL 允许报告会话为关键结论附加 Evidence Block，并将 `claim_id` 与来源信息稳定写入报告资源。

#### Scenario: 报告章节附加 Evidence Block
- **WHEN** 报告章节包含关键结论
- **THEN** 系统可在对应章节输出 Evidence Block
- **AND** Evidence Block 包含结论摘要与来源列表

#### Scenario: 报告资源保存证据映射
- **WHEN** 报告保存到会话资源
- **THEN** 报告资源中保留 `claim_id` 到来源记录的映射
- **AND** 后续渲染或导出可复用该映射

### Requirement: 报告必须支持 METHODS v1 区块

系统 SHALL 支持在报告会话中生成和更新 METHODS v1 区块，而不要求用户手工重写全部方法说明。

#### Scenario: 生成包含 METHODS 的报告
- **WHEN** 用户请求生成研究报告
- **THEN** 系统可为报告附加 METHODS v1 区块
- **AND** METHODS 内容来源于 METHODS 台账

#### Scenario: 后续步骤补充方法记录
- **WHEN** 同一报告会话后续新增分析步骤
- **THEN** 报告中的 METHODS v1 区块可被增量更新
