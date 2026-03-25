## ADDED Requirements

### Requirement: WebSocket 关键事件必须携带任务标识与尝试标识

系统 SHALL 在 deep task 相关关键事件中携带 `task_id`，并在存在恢复或重试时携带尝试标识，以便前端与诊断系统稳定关联。

#### Scenario: 关键事件携带 task_id
- **WHEN** 服务端推送与 deep task 相关的关键事件
- **THEN** 事件中包含 `task_id`
- **AND** 前端可用该标识关联同一次 deep task 的不同事件

#### Scenario: 重试事件携带尝试标识
- **WHEN** deep task 的某个动作进入重试或恢复
- **THEN** 对应事件包含尝试标识
- **AND** 能区分原始尝试与恢复尝试

### Requirement: WebSocket 协议必须支持预算告警事件字段

系统 SHALL 在 deep task 触发预算阈值时输出可消费的预算告警字段或事件，并允许客户端在本阶段忽略这些字段而不影响基础交互。

#### Scenario: 任务超预算时推送告警
- **WHEN** deep task 超过预设预算阈值
- **THEN** 服务端推送预算告警相关字段或事件
- **AND** 告警中包含 `task_id` 与告警摘要

#### Scenario: 客户端忽略预算告警仍保持兼容
- **WHEN** 客户端尚未实现预算告警的专门展示
- **THEN** 客户端仍可继续消费其他 deep task 关键事件
- **AND** 预算告警至少被记录到 trace、日志或诊断事件中
