## ADDED Requirements

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
