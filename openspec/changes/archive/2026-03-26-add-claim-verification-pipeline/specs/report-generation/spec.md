## ADDED Requirements

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
