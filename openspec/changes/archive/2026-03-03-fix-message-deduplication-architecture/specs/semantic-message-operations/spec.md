## ADDED Requirements

### Requirement: Message operation types
The system SHALL support three message operation types: `append`, `replace`, and `complete`.

#### Scenario: Append operation
- **GIVEN** a message with `message_id="msg-123"` and content "Hello"
- **WHEN** an event arrives with `operation="append"` and content " World"
- **THEN** the message SHALL become "Hello World"

#### Scenario: Replace operation
- **GIVEN** a message with `message_id="msg-123"` and content "Old content"
- **WHEN** an event arrives with `operation="replace"` and content "New content"
- **THEN** the message SHALL become "New content" (old content discarded)

#### Scenario: Complete operation
- **GIVEN** a message with `message_id="msg-123"` being streamed
- **WHEN** an event arrives with `operation="complete"`
- **THEN** the message SHALL be marked as finalized and the buffer cleaned up

### Requirement: Default operation behavior
The system SHALL default to `append` operation when `operation` is not specified.

#### Scenario: Event without operation field
- **GIVEN** an event with `message_id="msg-123"` and content "text"
- **WHEN** the event has no `operation` metadata field
- **THEN** it SHALL be treated as `operation="append"`

### Requirement: Operation semantic validation
The system SHALL validate operation semantics and handle invalid sequences gracefully.

#### Scenario: Replace on non-existent message
- **GIVEN** no message with `message_id="msg-123"` exists
- **WHEN** an event arrives with `operation="replace"` for that ID
- **THEN** a new message SHALL be created with the provided content

#### Scenario: Complete before any content
- **GIVEN** no prior events for `message_id="msg-123"`
- **WHEN** an event arrives with `operation="complete"`
- **THEN** the event SHALL be ignored (no message to complete)

### Requirement: Tool-generated message handling
The system SHALL use `replace` operation for tool-generated complete content.

#### Scenario: generate_report tool output
- **GIVEN** a generate_report tool has produced a complete markdown report
- **WHEN** the tool result is sent as a TEXT event
- **THEN** it SHALL have `operation="replace"` to replace any streamed preview

#### Scenario: Streaming before tool execution
- **GIVEN** LLM has streamed "正在生成报告..." as `message_id="msg-123"`
- **WHEN** generate_report returns and sends `operation="replace"` with full report
- **THEN** the streamed preview SHALL be replaced by the complete report
