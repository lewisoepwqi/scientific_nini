# prompt-system-composition Specification

## Purpose
TBD - created by archiving change refactor-prompt-architecture. Update Purpose after archive.
## Requirements
### Requirement: System prompt composition has one trusted assembly boundary
The system SHALL assemble runtime system prompts from trusted prompt components only and SHALL keep runtime context injection out of the system prompt layer.

#### Scenario: System prompt contains only trusted prompt components
- **WHEN** the Agent builds messages for an LLM call
- **THEN** the system prompt SHALL be produced by the prompt component builder
- **AND** dataset metadata, retrieved knowledge, AGENTS.md content, research profiles, and completed analysis memories SHALL NOT be appended directly to the system prompt

#### Scenario: Prompt components support runtime refresh without service restart
- **WHEN** a prompt component file is updated on disk
- **THEN** subsequent system prompt builds SHALL reflect the updated component content
- **AND** the runtime SHALL NOT require a process restart to load the change

### Requirement: Prompt component budget protection preserves core directives
The system SHALL enforce per-component and total prompt budgets while preserving core system directives.

#### Scenario: Budget protection truncates lower-priority components first
- **WHEN** the assembled system prompt exceeds the configured total budget
- **THEN** lower-priority components SHALL be truncated or dropped before higher-priority components
- **AND** identity, strategy, and security directives SHALL remain present in the final system prompt

#### Scenario: Component truncation is explicit
- **WHEN** a prompt component exceeds its configured per-component budget
- **THEN** the resulting prompt text SHALL include an explicit truncation marker
- **AND** the truncated output SHALL remain syntactically readable to the model

