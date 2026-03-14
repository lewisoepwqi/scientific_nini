## ADDED Requirements

### Requirement: Completion verification visibility
系统 SHALL 在用户界面中展示完成前校验的状态，而不是仅在后台静默执行。

#### Scenario: 用户可见 completion check 结果
- **WHEN** 前端收到 `completion_check` 事件
- **THEN** 系统 SHALL 在现有分析过程界面中展示校验结果
- **AND** 用户 SHALL 能看到哪些检查项已经满足、哪些仍待补齐

#### Scenario: 未通过校验时显示继续执行原因
- **WHEN** completion check 未通过且系统继续执行当前轮
- **THEN** 界面 SHALL 明确说明“为何尚未结束”
- **AND** 不得仅表现为模型继续输出而没有解释

### Requirement: Recovery and blocked state visibility
系统 SHALL 让 loop recovery 与 blocked 状态成为可理解的运行诊断信息。

#### Scenario: 坏循环恢复过程可见
- **WHEN** 系统识别到坏循环并触发恢复
- **THEN** 界面 SHALL 显示当前处于恢复、重规划或重新验证状态
- **AND** 用户 SHALL 能理解这是系统主动纠偏而非普通推理文本

#### Scenario: blocked 原因对用户可见
- **WHEN** 系统进入 `blocked` 状态
- **THEN** 界面 SHALL 显示阻塞原因和建议动作
- **AND** 用户 SHALL 能区分“任务失败终止”与“需要补充信息或调整策略”

### Requirement: Harness diagnostics integrate with existing analysis views
系统 SHALL 将 harness 诊断状态整合到现有分析计划、推理或任务视图中，而不是要求用户跳转到完全独立的新界面才能理解运行状态。

#### Scenario: 诊断信息与现有任务状态并列展示
- **WHEN** completion check、loop recovery 或 blocked 事件发生
- **THEN** 这些状态 SHALL 能与现有计划步骤、任务尝试或推理面板一起呈现
- **AND** 用户 SHALL 能从同一轮分析视图追踪运行进度与诊断结果
