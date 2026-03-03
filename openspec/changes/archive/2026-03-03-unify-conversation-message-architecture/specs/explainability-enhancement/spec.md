## MODIFIED Requirements

### Requirement: Reasoning event visualization

The system SHALL provide enhanced visualization for REASONING events in the chat interface and SHALL preserve one stable reasoning identity across streaming, completion, and history restoration.

#### Scenario: Collapsible reasoning steps

- **WHEN** a REASONING event is received from the Agent
- **THEN** the system SHALL render it as a collapsible panel in the message stream
- **AND** the panel SHALL show a summary title (e.g., "分析思路", "决策过程")
- **AND** the user SHALL be able to expand/collapse the panel to view full reasoning

#### Scenario: Highlighted decision points

- **WHEN** the reasoning content contains decision keywords (e.g., "选择", "决定", "因此", "因为")
- **THEN** those keywords SHALL be visually highlighted (bold or colored text)
- **AND** the system SHALL parse and display decision chains in a structured format

#### Scenario: Streaming reasoning updates merge into one panel

- **WHEN** multiple REASONING events with the same stable reasoning identity are emitted for a single reasoning chain
- **THEN** the client SHALL merge them into one logical reasoning panel
- **AND** the completed reasoning event SHALL finalize that same panel instead of creating another reasoning bubble

#### Scenario: Refreshed transcript restores completed reasoning without duplication

- **WHEN** the user refreshes the page after a reasoning stream has completed
- **THEN** the restored transcript SHALL contain one completed reasoning panel for that reasoning identity
- **AND** the transcript SHALL NOT replay duplicated reasoning fragments as separate panels
