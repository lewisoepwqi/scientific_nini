# Capability: Token Persistence

## Purpose

Persist token usage data across session restarts for accurate cost tracking.

## Requirements

### Requirement: Token usage is persisted across restarts

The SessionTokenTracker SHALL persist token usage data to disk.

#### Scenario: Record token usage to file

- **WHEN** token usage is recorded
- **THEN** it SHALL append to data/sessions/{session_id}/cost.jsonl
- **AND** the format SHALL be JSON Lines with timestamp

#### Scenario: Restore token usage on startup

- **WHEN** a session is loaded
- **THEN** the system SHALL read cost.jsonl if it exists
- **AND** it SHALL restore the SessionTokenTracker state

### Requirement: Real-time token usage WebSocket events

The system SHALL emit token usage events after each LLM call.

#### Scenario: Token usage event after LLM call

- **WHEN** an LLM call completes
- **THEN** a TOKEN_USAGE event SHALL be emitted via WebSocket
- **AND** the event SHALL include input_tokens, output_tokens, and cost

#### Scenario: Frontend updates CostPanel in real-time

- **WHEN** a TOKEN_USAGE event is received
- **THEN** the store SHALL update cost state
- **AND** CostPanel SHALL reflect the new values immediately
