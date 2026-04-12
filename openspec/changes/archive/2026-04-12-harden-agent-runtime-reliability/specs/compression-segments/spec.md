## ADDED Requirements

### Requirement: 压缩摘要必须保留关键运行时状态引用
系统 SHALL 在对话压缩后保留关键运行时状态的可恢复引用，至少覆盖 `pending_actions`、任务进度和关键失败线索。

#### Scenario: 压缩后仍可恢复 pending_actions
- **WHEN** 会话触发历史压缩且当前存在未解决的 `pending_actions`
- **THEN** 压缩后的上下文或等价恢复状态 SHALL 保留这些待处理动作的可恢复信息
- **AND** 后续轮次 SHALL 能继续使用这些状态进行运行判断

#### Scenario: 压缩后仍保留关键失败线索
- **WHEN** 某轮存在未解决的工具失败且会话触发压缩
- **THEN** 压缩结果 SHALL 保留失败工具、失败类型或等价影响摘要
- **AND** completion verification SHALL 能继续感知这些未解决失败

### Requirement: 压缩预算不得优先裁掉关键运行时状态
系统 SHALL 在 runtime context 预算紧张时优先裁剪辅助资料，而不是优先裁掉影响执行连续性和完成校验的关键状态块。

#### Scenario: 预算紧张时优先保留关键状态
- **WHEN** runtime context 达到预算上限
- **THEN** 系统 SHALL 优先保留 `pending_actions`、任务进度和关键失败状态
- **AND** SHALL 优先裁剪不影响执行连续性的辅助参考块

#### Scenario: 压缩后任务状态不退化
- **WHEN** 会话经过一次或多次压缩
- **THEN** 系统 SHALL 保持任务进度的可恢复状态
- **AND** SHALL NOT 因压缩导致已完成任务整体退化为未知或待执行状态
