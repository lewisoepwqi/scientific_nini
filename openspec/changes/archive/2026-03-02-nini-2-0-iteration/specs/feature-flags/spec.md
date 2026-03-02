## ADDED Requirements

### Requirement: Feature flags are configurable
The system SHALL provide feature flags for toggling major functionality.

#### Scenario: Cost tracking flag
- **WHEN** enable_cost_tracking is set to false
- **THEN** token usage tracking SHALL be disabled
- **AND** CostPanel SHALL show disabled state

#### Scenario: Reasoning flag
- **WHEN** enable_reasoning is set to false
- **THEN** REASONING events SHALL NOT be emitted
- **AND** reasoning display SHALL be hidden

#### Scenario: Knowledge flag
- **WHEN** enable_knowledge is set to false
- **THEN** RAG retrieval SHALL be skipped
- **AND** knowledge injection SHALL be disabled

### Requirement: Feature flags have sensible defaults
All feature flags SHALL default to enabled for backward compatibility.

#### Scenario: Default configuration
- **WHEN** no environment variables are set
- **THEN** enable_cost_tracking SHALL default to True
- **AND** enable_reasoning SHALL default to True
- **AND** enable_knowledge SHALL default to True
- **AND** knowledge_max_tokens SHALL default to 2000
- **AND** knowledge_top_k SHALL default to 5
