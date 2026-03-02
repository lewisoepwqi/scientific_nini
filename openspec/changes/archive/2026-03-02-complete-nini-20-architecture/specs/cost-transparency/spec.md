## ADDED Requirements

### Requirement: Real-time token consumption display
The system SHALL display real-time token consumption for the current session in the chat interface.

#### Scenario: Token counter updates on each LLM interaction
- **WHEN** the Agent receives a response from the LLM
- **THEN** the system SHALL update the session token counter with input_tokens, output_tokens, and total_tokens
- **AND** the updated counts SHALL be visible in the cost panel

#### Scenario: Cost estimation based on model pricing
- **WHEN** the user views the cost panel
- **THEN** the system SHALL display the estimated cost in CNY based on the current model's pricing
- **AND** the cost SHALL be calculated as: (input_tokens * input_price_per_1k + output_tokens * output_price_per_1k) / 1000

### Requirement: Session history cost statistics
The system SHALL provide cost statistics for historical sessions in the session list view.

#### Scenario: Display total cost per session
- **WHEN** the user opens the session list
- **THEN** each session SHALL display its total token consumption and estimated cost
- **AND** the information SHALL be sorted by most recent session first

#### Scenario: Aggregate cost summary
- **WHEN** the user views the session list
- **THEN** the system SHALL display an aggregate summary showing total cost across all sessions
- **AND** the summary SHALL include total tokens used and total estimated cost

### Requirement: Model cost comparison hints
The system SHALL display cost comparison information when users select or switch models.

#### Scenario: Cost hint in model selector
- **WHEN** the user opens the model selector dropdown
- **THEN** each model option SHALL display its pricing tier (e.g., "经济", "标准", "高级")
- **AND** the relative cost ratio compared to the current model SHALL be shown

#### Scenario: Cost warning for expensive models
- **WHEN** the user selects a model with significantly higher cost (2x+ the default)
- **THEN** the system SHALL display a warning toast indicating the higher cost
- **AND** the user SHALL be able to confirm or cancel the selection

### Requirement: Token usage API endpoint
The system SHALL expose an API endpoint for retrieving token usage statistics.

#### Scenario: Get session token stats
- **WHEN** a GET request is made to `/api/cost/session/{session_id}`
- **THEN** the system SHALL return a JSON response containing:
  - input_tokens: total input tokens for the session
  - output_tokens: total output tokens for the session
  - total_tokens: sum of input and output tokens
  - estimated_cost_cny: calculated cost in Chinese Yuan
  - model_breakdown: token usage per model used

#### Scenario: Token counter persistence
- **WHEN** a session is saved to disk
- **THEN** the token counter data SHALL be persisted alongside the session metadata
- **AND** the data SHALL be recoverable when the session is loaded

### Requirement: Cost transparency UI components
The system SHALL provide dedicated UI components for cost visualization.

#### Scenario: Cost panel in chat interface
- **WHEN** the user is in an active chat session
- **THEN** a cost panel SHALL be accessible (collapsible sidebar or header indicator)
- **AND** the panel SHALL display current session's real-time token usage and cost

#### Scenario: Cost history chart
- **WHEN** the user expands the cost panel
- **THEN** a simple line chart SHALL display token usage over time for the current session
- **AND** the chart SHALL show input/output tokens as separate lines
