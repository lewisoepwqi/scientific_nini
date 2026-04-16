## MODIFIED Requirements

### Requirement: Analysis loop recovery and blocking
系统 SHALL 识别科研分析场景中的坏循环，并基于结构化错误码执行分级恢复；当错误属于“调度语义误用”时，系统 MUST 优先切换执行路径或收紧错误工具形态，而不是仅依赖重复计数后阻断。

#### Scenario: 调度语义错误优先触发路径纠偏
- **WHEN** 同一恢复链路中连续出现 `dispatch_agents` 的调度上下文错误或等价误用错误
- **THEN** 系统 SHALL 先注入恢复提示并收紧错误工具路径
- **AND** SHALL 优先引导模型切换到推荐的直接工具路径
- **AND** 不得在第一次恢复前就仅以通用坏循环处理

#### Scenario: 路径切换后仍无推进才进入 blocked
- **WHEN** 系统已经对调度误用执行过路径收紧或切换
- **AND** 后续运行仍未推进任务、结论或产物状态
- **THEN** 系统 SHALL 将当前轮标记为 `blocked`
- **AND** 阻塞原因 SHALL 明确指出已尝试的恢复动作和仍未解决的原因

### Requirement: Harness runtime 必须维护统一的 pending_actions 账本
系统 SHALL 在运行时维护统一的 `pending_actions` 账本，用于显式追踪未完成动作、失败恢复线索和待确认状态；对于同一逻辑调度错误，系统 SHALL 进行归并，避免在压缩和恢复轮次中无限累积重复项。

#### Scenario: 同一逻辑调度错误只保留一条规范化待处理动作
- **WHEN** 同一恢复链路中多次出现语义等价的 `dispatch_agents` 误用
- **THEN** 系统 SHALL 将其归并为一条规范化的 `pending_action`
- **AND** 该条目 SHALL 保留最近一次错误摘要、来源工具和恢复建议

#### Scenario: 恢复动作生效后更新待处理动作状态
- **WHEN** 调度误用已被路径切换、显式放弃或成功恢复
- **THEN** 系统 SHALL 更新对应 `pending_action` 的状态或将其清理
- **AND** 不得将已过时错误继续作为当前阻塞动作注入后续上下文

### Requirement: Harness runtime 摘要必须包含 pending_actions
系统 SHALL 在当前轮的 runtime context 或等价运行时摘要中注入 `pending_actions` 的精简摘要，以支持跨压缩和跨恢复链路保持状态连续性；对于调度类错误，摘要 SHALL 同时包含当前执行任务与推荐恢复动作。

#### Scenario: 调度类待处理动作摘要包含上下文字段
- **WHEN** 当前轮存在与任务调度相关的未解决 `pending_actions`
- **THEN** 摘要 SHALL 包含当前 `in_progress` 任务或当前 `pending wave` 的关键上下文
- **AND** SHALL 包含推荐恢复动作
- **AND** SHALL 避免只保留无法指导恢复的通用报错文案

## ADDED Requirements

### Requirement: Harness recovery 必须基于错误码收紧错误路径
系统 SHALL 为可识别的工具误用错误维护恢复策略表，并根据错误码生成恢复建议、推荐工具与阻塞判定依据；涉及 turn 级工具拦截时，harness SHALL 通过结构化恢复结果驱动 runner 更新护栏，而不得维护第二套独立拦截状态。

#### Scenario: 非法 agent 错误触发定向收紧
- **WHEN** 运行中出现非法 `agent_id` 的结构化错误
- **THEN** harness SHALL 将其识别为可恢复的路径误用
- **AND** SHALL 生成“收紧相同错误形态”的结构化恢复建议并驱动 runner 执行

#### Scenario: 调度上下文错误触发直接工具推荐
- **WHEN** 运行中出现“当前任务应直接执行而非继续派发”的结构化错误
- **THEN** harness SHALL 在后续恢复链路中推荐直接执行工具
- **AND** SHALL 将该推荐写入运行时上下文或等价约束中
