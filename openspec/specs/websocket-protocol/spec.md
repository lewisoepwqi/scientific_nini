# websocket-protocol Specification

## Purpose
TBD - created by archiving change fix-message-deduplication-architecture. Update Purpose after archive.
## Requirements
### Requirement: Message ID metadata
WebSocket events SHALL include `message_id` in the metadata field.

#### Scenario: TEXT event with message_id
- **GIVEN** a backend TEXT event is generated
- **WHEN** the event is sent to the client
- **THEN** the event metadata SHALL contain `message_id` as a string

#### Scenario: Message ID format
- **GIVEN** a conversation turn with ID "turn-abc123"
- **WHEN** the first message of this turn is generated
- **THEN** the `message_id` SHALL be formatted as "turn-abc123-0"

#### Scenario: Multiple messages in same turn
- **GIVEN** a conversation turn with ID "turn-abc123"
- **WHEN** multiple messages are generated in sequence
- **THEN** the `message_id` values SHALL be "turn-abc123-0", "turn-abc123-1", etc.

### Requirement: Operation metadata
WebSocket TEXT events SHALL include `operation` in the metadata field.

#### Scenario: Streaming chunk with append operation
- **GIVEN** a LLM streaming chunk is being sent
- **WHEN** the TEXT event is created
- **THEN** the metadata SHALL contain `operation: "append"`

#### Scenario: Tool result with replace operation
- **GIVEN** a tool (e.g., generate_report) returns complete content
- **WHEN** the TEXT event is created for the tool output
- **THEN** the metadata SHALL contain `operation: "replace"`

#### Scenario: Stream completion
- **GIVEN** a message stream is ending
- **WHEN** the final TEXT event is sent
- **THEN** the metadata SHALL contain `operation: "complete"`

### Requirement: Backward compatibility
The protocol SHALL remain backward compatible with clients that ignore new metadata fields.

#### Scenario: Legacy client receives new format
- **GIVEN** a client that does not process `message_id` or `operation`
- **WHEN** events with these metadata fields are received
- **THEN** the client SHALL still display the message content correctly

#### Scenario: Old backend sends to new client
- **GIVEN** an old backend without message_id support
- **WHEN** events are sent to a new client
- **THEN** the client SHALL fall back to legacy append behavior

### Requirement: Event type coverage
The `message_id` and `operation` metadata SHALL apply to relevant event types.

#### Scenario: TEXT events have metadata
- **GIVEN** a TEXT type WebSocket event
- **WHEN** the event is generated
- **THEN** it SHALL include `message_id` and `operation` metadata

#### Scenario: Non-TEXT events unaffected
- **GIVEN** a CHART, DATA, or TOOL_CALL type event
- **WHEN** the event is generated
- **THEN** `message_id` and `operation` metadata are OPTIONAL

### Requirement: WebSocket 必须支持沙盒包审批事件流
系统 SHALL 在 WebSocket 通道中完整表达由沙盒扩展包审批触发的 `ask_user_question`、用户回答与工具恢复执行流程。

#### Scenario: 审批问题通过 ask_user_question 推送
- **WHEN** `run_code` 返回 `_sandbox_review_required`
- **THEN** 服务端 SHALL 推送 `ask_user_question` 事件
- **AND** 事件中包含当前工具调用关联的 `tool_call_id`
- **AND** 问题内容 SHALL 包含待审批包与授权选项

#### Scenario: 用户回答后恢复工具执行
- **WHEN** 前端通过 `ask_user_question_answer` 提交审批决定
- **THEN** 服务端 SHALL 将回答绑定到原始 `tool_call_id`
- **AND** 后端 SHALL 恢复原始工具调用的后续处理流程
- **AND** 最终继续推送对应的 `tool_result` 与后续事件

### Requirement: 审批事件流必须保持现有协议兼容性
系统 SHALL 在新增沙盒审批交互时继续兼容现有 `ask_user_question` 与 `tool_result` 事件消费者。

#### Scenario: 现有客户端继续消费审批结果
- **WHEN** 客户端已支持通用 `ask_user_question` 事件但不知道“沙盒审批”这一业务语义
- **THEN** 客户端仍 SHALL 能显示问题、提交回答并接收后续结果
- **AND** 不需要依赖新增专用事件类型

#### Scenario: 拒绝授权时返回明确结果
- **WHEN** 用户拒绝某个扩展包授权
- **THEN** 服务端 SHALL 返回对应的 `tool_result`
- **AND** 结果中包含明确的拒绝说明
- **AND** 不得让前端停留在无完成状态的悬挂请求中

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

### Requirement: WebSocket 协议必须支持 Recipe 生命周期事件

系统 SHALL 在 WebSocket 通道中表达 Recipe 启动、任务分类与生命周期状态变化，使前端能够稳定展示模板任务执行过程。

#### Scenario: Recipe 启动后推送任务初始化事件
- **WHEN** 用户通过 Recipe Center 或接受推荐启动模板任务
- **THEN** 服务端推送包含 `recipe_id`、任务类型与初始状态的事件
- **AND** 前端可据此切换到 deep task 展示模式

#### Scenario: deep task 状态变化时推送生命周期事件
- **WHEN** deep task 状态在 `queued`、`running`、`retrying`、`blocked`、`completed`、`failed` 之间变化
- **THEN** 服务端推送对应状态事件
- **AND** 事件中包含任务标识、当前步骤与原因摘要

### Requirement: WebSocket 协议必须支持 Recipe 步骤进度事件

系统 SHALL 提供可增量消费的 Recipe 步骤进度事件，表达总步骤数、当前步骤、步骤状态与下一步提示。

#### Scenario: deep task 进入某一步骤
- **WHEN** 系统开始执行某个 Recipe 步骤
- **THEN** 服务端推送步骤进度事件
- **AND** 事件中包含步骤索引、步骤标题、步骤状态与总步骤数

#### Scenario: deep task 进入重试
- **WHEN** 当前步骤因可恢复错误进入重试
- **THEN** 服务端推送步骤进度事件
- **AND** 事件中包含 `retrying` 状态与失败原因摘要

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
