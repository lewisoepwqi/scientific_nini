## ADDED Requirements

### Requirement: Message identification
Each message SHALL have a unique identifier (`message_id`) that remains constant across all updates to that message.

#### Scenario: Streamed message has consistent ID
- **GIVEN** a conversation turn generates a message
- **WHEN** the message is streamed in multiple chunks
- **THEN** all chunks SHALL share the same `message_id`

#### Scenario: Different messages have unique IDs
- **GIVEN** multiple messages in a conversation
- **WHEN** each message is generated
- **THEN** each message SHALL have a distinct `message_id`

### Requirement: Message deduplication
The system SHALL prevent displaying duplicate content based on `message_id`.

#### Scenario: Duplicate message update is ignored
- **GIVEN** a message with `message_id="msg-123"` has been displayed
- **WHEN** a new event arrives with the same `message_id` and identical content
- **THEN** the duplicate event SHALL be silently ignored

#### Scenario: Message update with new content is applied
- **GIVEN** a message with `message_id="msg-123"` has been displayed with content "Hello"
- **WHEN** an update arrives with the same `message_id` but content "Hello World"
- **THEN** the message SHALL be updated to "Hello World"

### Requirement: Message buffer management
The frontend SHALL maintain a message buffer to track in-flight messages by their IDs.

#### Scenario: Buffer tracks message state
- **GIVEN** a message with `message_id="msg-123"` is being streamed
- **WHEN** multiple chunks arrive with the same `message_id`
- **THEN** the buffer SHALL accumulate the content for that message ID

#### Scenario: Buffer cleanup on completion
- **GIVEN** a message with `message_id="msg-123"` has been marked as `complete`
- **WHEN** 5 minutes have passed since completion
- **THEN** the message buffer entry SHALL be removed

### Requirement: Backward compatibility
The system SHALL handle events without `message_id` using legacy behavior.

#### Scenario: Legacy event without message_id
- **GIVEN** an event without `message_id` metadata
- **WHEN** the event is processed
- **THEN** it SHALL be treated as a new message using the old append logic
