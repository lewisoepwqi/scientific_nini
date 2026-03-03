## MODIFIED Requirements

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
