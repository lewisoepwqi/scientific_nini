# Capability: Report Generation

## Purpose

Enable users to generate and download analysis reports from their sessions.
## Requirements
### Requirement: Report generation calls backend API

The generateReport function SHALL call the backend API endpoint instead of using setTimeout mock.

#### Scenario: Generate report via API

- **WHEN** user clicks "Generate Report" button
- **THEN** the system SHALL POST to /api/sessions/{id}/generate-report
- **AND** it SHALL display loading state during generation
- **AND** it SHALL show success/error notification on completion

### Requirement: Report download fetches from workspace

The downloadReport function SHALL fetch the report file from workspace.

#### Scenario: Download generated report

- **WHEN** user clicks "Download Report" button
- **THEN** the system SHALL GET /api/sessions/{id}/workspace/files/{path}
- **AND** it SHALL trigger browser download with correct filename
- **AND** it SHALL handle download errors gracefully

### Requirement: 报告生成必须支持报告会话生命周期
系统 SHALL 将报告作为可持续更新的会话资源管理，支持创建、查询、章节级修改和导出，而不是仅支持一次性生成最终文档。

#### Scenario: 创建报告会话
- **WHEN** 用户或编排层请求创建新报告
- **THEN** 系统创建报告资源
- **AND** 返回报告 `resource_id`

#### Scenario: 按章节修改报告
- **WHEN** 用户或编排层针对已有报告指定章节 patch
- **THEN** 系统仅更新目标章节内容
- **AND** 保留其他章节不变

### Requirement: 报告必须可绑定结构化分析资源
系统 SHALL 支持将统计结果、图表、数据摘要等结构化资源绑定到报告会话，并在导出时稳定解析这些引用。

#### Scenario: 绑定图表资源到报告
- **WHEN** 报告会话附加图表资源
- **THEN** 系统记录图表资源引用
- **AND** 导出报告时包含对应图表内容或下载入口

#### Scenario: 绑定统计结果到报告
- **WHEN** 报告会话附加统计结果资源
- **THEN** 系统可在报告章节中引用该结构化结果
- **AND** 不要求重新手工拼接完整文本

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

### Requirement: 报告最终摘要必须排除未验证结论

系统 SHALL 默认只将 `verified` 状态的结论写入最终摘要；`pending_verification` 或 `conflicted` 结论不得直接进入最终摘要正文。

#### Scenario: 已验证结论进入摘要
- **WHEN** 报告生成最终摘要
- **THEN** 系统仅选取 `verified` 状态的结论写入摘要

#### Scenario: 待验证结论不进入摘要
- **WHEN** 结论状态为 `pending_verification` 或 `conflicted`
- **THEN** 系统不将该结论写入最终摘要正文
- **AND** 该结论可在单独区域标记展示

### Requirement: 报告必须显式标记待验证与冲突结论

系统 SHALL 在报告正文或附录中显式展示 `pending_verification` 与 `conflicted` 结论的状态和原因，避免用户误认为这些结论已经成立。

#### Scenario: 报告展示待验证结论
- **WHEN** 报告包含待验证结论
- **THEN** 系统以“待验证”标签展示该结论
- **AND** 附带缺口原因摘要

#### Scenario: 报告展示冲突结论
- **WHEN** 报告包含冲突结论
- **THEN** 系统以“证据冲突”标签展示该结论
- **AND** 附带冲突摘要或冲突来源说明

### Requirement: 报告会话必须支持模板化导出格式

系统 SHALL 支持基于同一报告会话导出 Word、PPTX 与 LaTeX 等模板化格式，而不是仅生成单一文件。

#### Scenario: 导出 Word 报告
- **WHEN** 用户为报告会话选择 Word 模板导出
- **THEN** 系统生成对应 Word 文件
- **AND** 导出结果登记为项目产物

#### Scenario: 导出 PPTX 或 LaTeX 报告
- **WHEN** 用户为报告会话选择 PPTX 或 LaTeX 导出
- **THEN** 系统生成对应格式文件
- **AND** 保持与当前报告会话内容一致

### Requirement: 报告导出必须保留证据与 METHODS 结构

系统 SHALL 在模板化导出时保留已生成的 Evidence Block、METHODS 区块、结论验证状态和结构化资源引用，而不是在导出阶段丢失这些信息。

#### Scenario: 导出包含 Evidence Block 的报告
- **WHEN** 当前报告会话已包含 Evidence Block
- **THEN** 模板化导出结果保留这些区块或其等价表达

#### Scenario: 导出包含 METHODS 的报告
- **WHEN** 当前报告会话已包含 METHODS v1 区块
- **THEN** 模板化导出结果保留 METHODS 内容

#### Scenario: 导出保留结论验证状态
- **WHEN** 当前报告会话已区分 `verified`、`pending_verification` 或 `conflicted` 结论
- **THEN** 模板化导出结果保留这些状态标签或其等价表达
