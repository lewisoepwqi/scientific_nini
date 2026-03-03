# Capability: Conversation Message Lifecycle

## Purpose

Define stable message identity and lifecycle semantics so realtime rendering, persisted history, and replay after refresh all refer to the same logical conversation messages.

## Requirements
### Requirement: Stable message identity across realtime and persisted conversation
The system SHALL assign a stable `message_id` to each user-visible assistant message and SHALL preserve that identity across streaming updates, tool-driven replacements, persisted session history, and history reads.

#### Scenario: Streaming chunks share one message identity
- **WHEN** the Agent emits multiple `text` events for the same assistant reply during a single turn
- **THEN** all events SHALL carry the same `message_id`
- **AND** the persisted conversation record SHALL store that `message_id` with the final assistant message

#### Scenario: Tool-generated final content reuses the original message identity
- **WHEN** an assistant preview message is later replaced by a tool-generated final result such as a report body
- **THEN** the replacement event SHALL reuse the original `message_id`
- **AND** the persisted conversation history SHALL record the final message under that same identity instead of creating a second logical message

### Requirement: Message lifecycle operations are explicit and replayable
The system SHALL represent assistant message updates with explicit lifecycle operations so that realtime rendering and history reconstruction can replay the same semantic transitions.

#### Scenario: Append operation extends existing message content
- **WHEN** a message update is marked with operation `append`
- **THEN** the client SHALL append the incoming delta to the existing message with the same `message_id`
- **AND** replaying persisted history SHALL produce the same final content as the realtime stream

#### Scenario: Replace operation supersedes previous message content
- **WHEN** a message update is marked with operation `replace`
- **THEN** the client SHALL replace the existing content of the message with the same `message_id`
- **AND** the system SHALL NOT render a second assistant bubble for that logical message

#### Scenario: Complete operation closes in-flight message state
- **WHEN** a message update is marked with operation `complete`
- **THEN** the client SHALL mark the message lifecycle as finalized
- **AND** any in-flight buffer for that `message_id` SHALL be cleared

### Requirement: History API returns canonical message metadata
The history API SHALL return canonical message metadata required to reconstruct the same conversation semantics after refresh.

#### Scenario: History response includes lifecycle metadata for assistant messages
- **WHEN** the client requests session messages from the canonical history endpoint
- **THEN** each assistant or reasoning message that has a stable identity SHALL include `message_id` or `reasoning_id`, `turn_id`, and relevant lifecycle metadata
- **AND** the response SHALL be sufficient for the client to rebuild message relationships without inferring them from content alone
