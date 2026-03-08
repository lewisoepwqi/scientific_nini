# prompt-runtime-context-safety Specification

## Purpose
TBD - created by archiving change refactor-prompt-architecture. Update Purpose after archive.
## Requirements
### Requirement: Runtime context injection has one canonical builder
The system SHALL build runtime context for LLM messages through one canonical implementation, including Markdown Skill bodies and referenced skill resources.

#### Scenario: AgentRunner delegates runtime context assembly to the canonical builder
- **WHEN** the Agent prepares messages for an LLM turn
- **THEN** runtime context SHALL be assembled through one canonical builder path
- **AND** the system SHALL NOT maintain parallel production implementations that can diverge in label protocol, ordering, filtering rules, or skill resource expansion behavior

### Requirement: Untrusted runtime context uses a uniform label protocol
The system SHALL label untrusted runtime context with a uniform contract so the model can distinguish reference material from instructions; Markdown Skill bodies and referenced skill resources SHALL use the same untrusted-context protocol as other runtime references.

#### Scenario: Every injected runtime context block carries a normalized untrusted header
- **WHEN** dataset metadata, knowledge references, Markdown Skill bodies, referenced skill resources, analysis memories, or research profile preferences are injected
- **THEN** each block SHALL use the normalized untrusted-context header format defined by the prompt policy
- **AND** the formatting, punctuation, and explanatory text SHALL be consistent across all injected context categories

#### Scenario: Untrusted context ordering is deterministic
- **WHEN** multiple runtime context categories are available for the same turn
- **THEN** they SHALL be injected in a deterministic order defined by the canonical builder
- **AND** the same input state SHALL produce the same context ordering across runs

#### Scenario: Skill referenced resources follow skill body in a stable order
- **WHEN** a turn injects both a Markdown Skill body and one or more referenced skill resources
- **THEN** the skill body SHALL appear before referenced resource content
- **AND** referenced resources SHALL be ordered deterministically by resolved relative path or an equivalent stable rule

### Requirement: Prompt safety policy is centrally defined
The system SHALL maintain suspicious-pattern filtering, non-dialog event exclusion, prompt budget thresholds, and skill-context budget thresholds in one centrally defined policy module.

#### Scenario: Suspicious context filtering is shared across builder paths
- **WHEN** runtime context text is sanitized for injection
- **THEN** all builder paths SHALL use the same suspicious-pattern policy
- **AND** changing the policy in one place SHALL update the effective behavior of all runtime context injection paths

#### Scenario: Non-dialog events remain excluded from LLM history
- **WHEN** conversation history is prepared for LLM context
- **THEN** chart, data, artifact, and image events SHALL be filtered according to the centralized prompt safety policy
- **AND** tool payload trimming SHALL continue to apply before history is sent to the model

#### Scenario: Skill runtime context has an independent budget
- **WHEN** Markdown Skill bodies or referenced skill resources exceed the configured runtime-context budget
- **THEN** the system SHALL truncate or drop lower-priority skill context before trimming conversation history
- **AND** the final runtime context SHALL include explicit truncation markers where truncation occurs

#### Scenario: Unreferenced skill resources are not read into runtime context
- **WHEN** a turn activates a Markdown Skill but only references a subset of its resources
- **THEN** the canonical runtime-context builder SHALL only read the referenced resource contents
- **AND** unreferenced resource files SHALL NOT be read just to decide whether to inject them

### Requirement: Skill runtime context must not expose absolute filesystem paths
The system SHALL avoid exposing server absolute paths in untrusted runtime context for Markdown Skills and their referenced resources.

#### Scenario: Skill body source path is normalized
- **WHEN** the runtime context references the origin of a Markdown Skill
- **THEN** the source identifier SHALL use a skill-relative path, logical identifier, or equivalent non-absolute representation
- **AND** the server absolute filesystem path SHALL NOT be injected into the model context

#### Scenario: Referenced resource path is normalized
- **WHEN** the runtime context includes content loaded from a referenced skill resource
- **THEN** the path label SHALL use a skill-relative path or logical identifier
- **AND** the server absolute filesystem path SHALL NOT be injected into the model context
