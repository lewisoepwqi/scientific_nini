## ADDED Requirements

### Requirement: 系统必须为结论建立结构化证据绑定

系统 SHALL 为每条进入最终回答或报告正文的结论建立结构化证据绑定，至少记录 `claim_id`、来源列表、来源类型、标题或资源名、时间戳、稳定标识与获取方式。

#### Scenario: 结论绑定单个来源
- **WHEN** 系统生成带来源支撑的结论
- **THEN** 该结论包含唯一 `claim_id`
- **AND** 至少绑定一个结构化来源记录

#### Scenario: 结论绑定多个来源
- **WHEN** 某个结论由多个来源共同支撑
- **THEN** 系统在同一 `claim_id` 下记录多个来源
- **AND** 保留来源顺序与来源类型

### Requirement: 系统必须归一化不同来源的最小溯源字段

系统 SHALL 对知识检索、网页抓取、工作区文件或结构化资源等不同来源统一产出最小溯源字段，以便上层报告和引用展示复用。

#### Scenario: 知识检索来源归一化
- **WHEN** 结论引用知识库检索结果
- **THEN** 来源记录包含来源标题、文档标识、检索方式与获取时间

#### Scenario: 工作区文件来源归一化
- **WHEN** 结论引用当前会话工作区内的文件或结构化资源
- **THEN** 来源记录包含资源类型、资源标识、文件名或资源名与生成时间

### Requirement: 系统必须输出最小 Evidence Block

系统 SHALL 为报告或长回答中的关键结论生成 Evidence Block，至少展示结论摘要、来源列表、获取方式与来源时间信息。

#### Scenario: 报告中生成 Evidence Block
- **WHEN** 用户生成带结论摘要的报告
- **THEN** 每个关键结论均可附带对应的 Evidence Block
- **AND** Evidence Block 可通过 `claim_id` 回溯到底层来源记录

#### Scenario: 长回答中附带证据摘要
- **WHEN** 系统输出长篇研究回答
- **THEN** 回答可附带最小证据摘要
- **AND** 不要求直接暴露全部底层原始文本
