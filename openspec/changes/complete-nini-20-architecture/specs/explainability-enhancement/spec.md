## ADDED Requirements

### Requirement: Reasoning event visualization
The system SHALL provide enhanced visualization for REASONING events in the chat interface.

#### Scenario: Collapsible reasoning steps
- **WHEN** a REASONING event is received from the Agent
- **THEN** the system SHALL render it as a collapsible panel in the message stream
- **AND** the panel SHALL show a summary title (e.g., "分析思路", "决策过程")
- **AND** the user SHALL be able to expand/collapse the panel to view full reasoning

#### Scenario: Highlighted decision points
- **WHEN** the reasoning content contains decision keywords (e.g., "选择", "决定", "因此", "因为")
- **THEN** those keywords SHALL be visually highlighted (bold or colored text)
- **AND** the system SHALL parse and display decision chains in a structured format

### Requirement: Analysis reasoning timeline
The system SHALL display the Agent's reasoning process as a timeline view.

#### Scenario: Timeline view for analysis steps
- **WHEN** the user initiates a multi-step analysis
- **THEN** a timeline component SHALL appear showing each reasoning step
- **AND** each step SHALL display: step number, title, status (pending/active/completed), timestamp

#### Scenario: Step detail expansion
- **WHEN** the user clicks on a timeline step
- **THEN** the step SHALL expand to show detailed reasoning content
- **AND** any associated tool calls or data references SHALL be shown as sub-items

#### Scenario: Timeline progression
- **WHEN** the Agent completes a reasoning step
- **THEN** the timeline SHALL automatically scroll to show the next active step
- **AND** completed steps SHALL be marked with a success indicator

### Requirement: Decision rationale display
The system SHALL display the rationale behind key analysis decisions.

#### Scenario: Tool selection explanation
- **WHEN** the Agent decides to use a specific statistical test (e.g., t_test vs mann_whitney)
- **THEN** the reasoning SHALL include why that test was chosen
- **AND** the UI SHALL display this rationale adjacent to the tool call result

#### Scenario: Assumption checking explanation
- **WHEN** the Agent checks statistical assumptions (normality, homogeneity)
- **THEN** the reasoning SHALL explain the assumption check results
- **AND** if assumptions are violated, the reasoning SHALL explain the fallback strategy

### Requirement: Reasoning event structure enhancement
The system MAY extend the REASONING event structure to support enhanced visualization.

#### Scenario: Structured reasoning metadata
- **WHEN** the Agent generates a REASONING event
- **THEN** the event MAY include structured fields:
  - reasoning_type: "analysis" | "decision" | "planning" | "reflection"
  - confidence_score: 0.0 to 1.0
  - key_decisions: list of key decision points
  - references: citations to data or prior steps

#### Scenario: Reasoning chain linking
- **WHEN** multiple REASONING events are generated in sequence
- **THEN** each event SHALL include a reference to the parent reasoning (if applicable)
- **AND** the UI SHALL be able to display them as a connected chain

### Requirement: Export reasoning for documentation
The system SHALL allow users to export reasoning for documentation purposes.

#### Scenario: Copy reasoning to clipboard
- **WHEN** the user clicks the "复制分析思路" button on a reasoning panel
- **THEN** the full reasoning content SHALL be formatted and copied to clipboard
- **AND** the format SHALL be suitable for pasting into research documentation

#### Scenario: Include reasoning in report export
- **WHEN** the user generates a research report
- **THEN** there SHALL be an option to include the reasoning timeline in the export
- **AND** the reasoning SHALL be formatted as a methodological appendix
