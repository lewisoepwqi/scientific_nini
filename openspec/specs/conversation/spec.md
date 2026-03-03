# Capability: Conversation

## Purpose

Manage real-time conversation events including token usage tracking and cost transparency.
## Requirements
### Requirement: Token usage event stream

The system SHALL emit TOKEN_USAGE events after each LLM call to enable real-time cost tracking.

#### Scenario: Token usage event emitted after LLM call

- **WHEN** an LLM chat completion finishes
- **THEN** a WebSocket event of type `token_usage` SHALL be emitted
- **AND** the event SHALL include input_tokens, output_tokens, model_name, and calculated cost

#### Scenario: Frontend receives token usage updates

- **WHEN** a `token_usage` event is received via WebSocket
- **THEN** the Zustand store SHALL update the cost state
- **AND** CostPanel SHALL display the updated values immediately

### Requirement: Conversation event stream carries canonical message metadata
The system SHALL emit user-visible conversation events with canonical metadata that can be reconciled with persisted history.

#### Scenario: Assistant text event includes stable identifiers
- **WHEN** the Agent emits a `text` event for an assistant message
- **THEN** the event SHALL include `turn_id`
- **AND** the event SHALL include lifecycle metadata sufficient to bind the event to one logical message across stream updates and history replay

#### Scenario: Tool-related visible messages can be traced to a logical turn
- **WHEN** the Agent emits user-visible tool-related conversation output
- **THEN** the event or persisted record SHALL include identifiers linking it to the originating logical turn
- **AND** the client SHALL be able to reconcile it during retry, refresh, or reconnect without relying on display content matching

### Requirement: Session message history uses a single canonical API contract
The system SHALL expose one canonical contract for session message history and SHALL return the metadata required for transcript reconstruction.

#### Scenario: History endpoint returns canonical assistant message fields
- **WHEN** the client requests `/api/sessions/{session_id}/messages`
- **THEN** the response SHALL include the canonical message metadata defined for persisted conversation messages
- **AND** the contract SHALL be stable regardless of whether the session is loaded from memory or disk

#### Scenario: Duplicate history implementations do not diverge externally
- **WHEN** the server serves session message history
- **THEN** there SHALL be exactly one externally supported response contract for that route
- **AND** any legacy or internal adapter implementation SHALL NOT expose a conflicting schema to clients

#### Scenario: Prompt runtime context is built consistently for the same conversation state
- **WHEN** the Agent prepares LLM messages for a conversation turn
- **THEN** the system SHALL use one canonical runtime context builder for that conversation state
- **AND** the resulting context ordering and labeling SHALL NOT depend on whether the call originated from a direct runner path or a helper abstraction

