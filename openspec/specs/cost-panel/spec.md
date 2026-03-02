# Capability: Cost Panel

## Purpose

Provide a user interface for viewing and managing session costs and token usage.

## Requirements

### Requirement: CostPanel is accessible from main UI

The CostPanel component SHALL be rendered and accessible from the main application interface.

#### Scenario: Open CostPanel via toolbar

- **WHEN** user clicks the Coins icon in the top toolbar
- **THEN** the CostPanel SHALL toggle visible
- **AND** the panel SHALL display current session token usage

#### Scenario: CostPanel displays token statistics

- **WHEN** CostPanel is visible
- **THEN** it SHALL display input tokens, output tokens, and total cost
- **AND** it SHALL show cost breakdown by model tier

### Requirement: CostPanel integrates with store state

The CostPanel SHALL read from and write to the Zustand store.

#### Scenario: Display stored cost data

- **WHEN** CostPanel renders
- **THEN** it SHALL read cost data from store.state.costs
- **AND** it SHALL update when store state changes
