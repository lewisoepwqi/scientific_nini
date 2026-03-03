# prompt-runtime-context-safety Specification

## Purpose
TBD - created by archiving change refactor-prompt-architecture. Update Purpose after archive.
## Requirements
### Requirement: Runtime context injection has one canonical builder
The system SHALL build runtime context for LLM messages through one canonical implementation.

#### Scenario: AgentRunner delegates runtime context assembly to the canonical builder
- **WHEN** the Agent prepares messages for an LLM turn
- **THEN** runtime context SHALL be assembled through one canonical builder path
- **AND** the system SHALL NOT maintain parallel production implementations that can diverge in label protocol, ordering, or filtering rules

### Requirement: Untrusted runtime context uses a uniform label protocol
The system SHALL label untrusted runtime context with a uniform contract so the model can distinguish reference material from instructions.

#### Scenario: Every injected runtime context block carries a normalized untrusted header
- **WHEN** dataset metadata, knowledge references, AGENTS.md content, analysis memories, or research profile preferences are injected
- **THEN** each block SHALL use the normalized untrusted-context header format defined by the prompt policy
- **AND** the formatting, punctuation, and explanatory text SHALL be consistent across all injected context categories

#### Scenario: Untrusted context ordering is deterministic
- **WHEN** multiple runtime context categories are available for the same turn
- **THEN** they SHALL be injected in a deterministic order defined by the canonical builder
- **AND** the same input state SHALL produce the same context ordering across runs

### Requirement: Prompt safety policy is centrally defined
The system SHALL maintain suspicious-pattern filtering, non-dialog event exclusion, and prompt budget thresholds in one centrally defined policy module.

#### Scenario: Suspicious context filtering is shared across builder paths
- **WHEN** runtime context text is sanitized for injection
- **THEN** all builder paths SHALL use the same suspicious-pattern policy
- **AND** changing the policy in one place SHALL update the effective behavior of all runtime context injection paths

#### Scenario: Non-dialog events remain excluded from LLM history
- **WHEN** conversation history is prepared for LLM context
- **THEN** chart, data, artifact, and image events SHALL be filtered according to the centralized prompt safety policy
- **AND** tool payload trimming SHALL continue to apply before history is sent to the model

