# Capability: Conversation Session Reconciliation

## Purpose

Define how refresh, reconnect, retry, and stop operations reconcile the visible transcript with canonical persisted conversation state.

## Requirements
### Requirement: Refresh rebuilds conversation from canonical history
The system SHALL rebuild the chat transcript after page refresh from canonical persisted message metadata rather than from content-based heuristics.

#### Scenario: Refresh restores a previously streamed assistant reply without duplicates
- **WHEN** the user refreshes the page after an assistant reply has completed
- **THEN** the client SHALL fetch canonical session history
- **AND** the rebuilt transcript SHALL contain exactly one logical assistant message for each persisted `message_id`

#### Scenario: Refresh restores completed reasoning state
- **WHEN** the user refreshes the page after a reasoning event stream has completed
- **THEN** the client SHALL restore the reasoning content using its stable identity
- **AND** the reasoning panel SHALL appear in its completed state instead of replaying duplicate incremental fragments

### Requirement: WebSocket reconnection performs session reconciliation
The system SHALL treat WebSocket reconnection as a session reconciliation step and SHALL re-synchronize visible conversation state with persisted history.

#### Scenario: Reconnect clears stale in-flight buffers before syncing history
- **WHEN** the WebSocket connection is re-established after being interrupted during an active turn
- **THEN** the client SHALL clear stale in-flight buffers for incomplete messages
- **AND** it SHALL fetch the current session history before resuming normal event handling

#### Scenario: Reconnect converges transcript to persisted state
- **WHEN** the client receives session history after reconnect
- **THEN** it SHALL reconcile existing UI messages by `message_id`, `reasoning_id`, and `turn_id`
- **AND** any stale duplicate bubbles that do not correspond to canonical history SHALL be removed or replaced

### Requirement: Retry and stop preserve turn boundaries
The system SHALL preserve turn-level message boundaries so that retry and stop actions can remove or reconcile only the affected logical turn.

#### Scenario: Retry removes only messages from the retried turn
- **WHEN** the user retries the last turn
- **THEN** the client and server SHALL identify messages belonging to that turn by `turn_id`
- **AND** only messages from the retried turn SHALL be removed or replaced before the new attempt begins

#### Scenario: Stop leaves transcript in a reconcilable partial state
- **WHEN** the user stops an in-progress request
- **THEN** any persisted partial messages SHALL remain associated with their original `message_id` and `turn_id`
- **AND** a later refresh or reconnect SHALL reconstruct the same partial transcript without creating duplicate logical messages
