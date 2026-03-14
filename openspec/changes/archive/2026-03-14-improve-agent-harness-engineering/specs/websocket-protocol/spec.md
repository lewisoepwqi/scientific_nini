## ADDED Requirements

### Requirement: Harness run context event
WebSocket 协议 SHALL 支持表达当前轮 harness 运行所采用的关键上下文摘要。

#### Scenario: 运行开始后推送 run_context
- **WHEN** harness 完成当前轮运行上下文装配并准备进入执行
- **THEN** 服务端 SHALL 推送 `run_context` 事件
- **AND** 事件 SHALL 包含当前轮关联标识以及数据集、产物、工具提示或关键运行约束等摘要字段

#### Scenario: run_context 保持摘要级表达
- **WHEN** 服务端推送 `run_context` 事件
- **THEN** 事件内容 SHALL 仅表达运行所需的关键摘要
- **AND** 不得要求客户端依赖完整系统提示词或原始 runtime context 文本才能理解该事件

### Requirement: Completion check event
WebSocket 协议 SHALL 支持表达完成前校验的结果与缺口。

#### Scenario: 校验执行后推送 completion_check
- **WHEN** 系统执行 completion verification
- **THEN** 服务端 SHALL 推送 `completion_check` 事件
- **AND** 事件 SHALL 包含校验项列表、是否通过以及缺失动作或说明

#### Scenario: completion_check 与 done 结果一致
- **WHEN** `completion_check` 显示未通过
- **THEN** 服务端 SHALL 不得在同一校验分支上直接推送表示正常完成的 `done`

### Requirement: Blocked event for unresolved runs
WebSocket 协议 SHALL 支持显式表达进入阻塞态的运行，而不是仅通过通用错误文本表示。

#### Scenario: 恢复失败后推送 blocked
- **WHEN** 坏循环恢复、验证补救或重规划仍未使当前轮继续推进
- **THEN** 服务端 SHALL 推送 `blocked` 事件
- **AND** 事件 SHALL 包含原因代码、可恢复性标记与建议动作

#### Scenario: blocked 事件保持协议兼容
- **WHEN** 旧客户端忽略新增的 `blocked` 事件
- **THEN** 其他既有事件流 SHALL 继续保持可消费
- **AND** 新增事件不得破坏现有会话基础交互
