## Requirements

### Requirement: 系统必须抽取可验证结论

系统 SHALL 从深任务回答或报告草稿中抽取可验证结论，并仅对已经完成 `claim_id` 绑定的结论生成待校验记录。

#### Scenario: 从研究摘要中抽取结论
- **WHEN** 系统准备生成研究摘要或报告结论
- **THEN** 系统抽取可验证结论列表
- **AND** 每条进入校验流水线的结论均保留已有 `claim_id`

#### Scenario: 不可验证文本不进入校验队列
- **WHEN** 文本属于流程说明、礼貌表达或纯操作提示
- **THEN** 系统不将其作为可验证结论加入校验队列

#### Scenario: 缺少 claim_id 的结论不进入校验流水线
- **WHEN** 某条候选结论尚未完成 `claim_id` 绑定
- **THEN** 系统不将其送入 Claim 校验流水线
- **AND** 该情况被视为上游证据绑定缺口而不是当前阶段重新绑定

### Requirement: 系统必须执行证据对齐与验证状态判定

系统 SHALL 对每条可验证结论执行证据对齐，并输出至少 `verified`、`pending_verification`、`conflicted` 三类验证状态。

#### Scenario: 证据充分时标记为 verified
- **WHEN** 某结论存在足够且一致的来源记录
- **THEN** 系统将该结论标记为 `verified`
- **AND** 输出对应的证据集合

#### Scenario: 证据不足时标记为 pending_verification
- **WHEN** 某结论缺少足够来源或来源支撑不足
- **THEN** 系统将该结论标记为 `pending_verification`
- **AND** 记录缺口原因

#### Scenario: 来源冲突时标记为 conflicted
- **WHEN** 结论对应来源之间出现关键事实冲突
- **THEN** 系统将该结论标记为 `conflicted`
- **AND** 记录冲突来源或冲突摘要

### Requirement: 系统必须输出置信度评分与原因摘要

系统 SHALL 为每条结论输出置信度评分与原因摘要，供报告渲染、引用展示与后续评测使用。

#### Scenario: 已验证结论输出评分
- **WHEN** 结论完成校验
- **THEN** 系统输出该结论的置信度评分
- **AND** 输出简短原因摘要

#### Scenario: 待验证结论输出低置信度
- **WHEN** 结论被标记为 `pending_verification`
- **THEN** 系统输出低于已验证结论的置信度评分
- **AND** 原因摘要说明缺失证据或校验不足
