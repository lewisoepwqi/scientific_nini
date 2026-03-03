## ADDED Requirements

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
