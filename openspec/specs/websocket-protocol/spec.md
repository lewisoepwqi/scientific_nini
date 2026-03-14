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
