## MODIFIED Requirements

### Requirement: System prompt composition has one trusted assembly boundary
The system SHALL assemble runtime system prompts from trusted prompt components only, SHALL keep runtime context injection out of the system prompt layer, and SHALL treat project `AGENTS.md` as part of the trusted assembly boundary. Markdown Skill user-editable text and metadata SHALL NOT enter the trusted prompt boundary verbatim.

#### Scenario: System prompt contains only trusted prompt components
- **WHEN** the Agent builds messages for an LLM call
- **THEN** the system prompt SHALL be produced by the prompt component builder
- **AND** dataset metadata, retrieved knowledge, Markdown Skill bodies, referenced skill resources, and completed analysis memories SHALL NOT be appended directly to the system prompt
- **AND** long-term memory summaries and user profile summaries SHALL be injected exclusively via the component_overrides mechanism into memory.md and user.md components respectively

#### Scenario: Project AGENTS.md is part of the trusted prompt assembly
- **WHEN** the Agent builds the trusted system prompt
- **THEN** the project-level `AGENTS.md` content SHALL be assembled as trusted project constraints
- **AND** it SHALL NOT be downgraded into an untrusted runtime-context block

#### Scenario: Root AGENTS.md wins over narrower directory rules
- **WHEN** both the repository root and a subdirectory provide `AGENTS.md`
- **THEN** the root `AGENTS.md` SHALL define the higher-priority repository-wide constraints
- **AND** any narrower-scope `AGENTS.md` content MAY only add more specific constraints for its own scope
- **AND** narrower rules SHALL NOT weaken or override root-level trusted constraints

#### Scenario: Markdown Skill snapshot uses trusted summaries only
- **WHEN** the prompt builder loads skill-related trusted components
- **THEN** it MAY include system-generated Markdown Skill summaries
- **AND** it SHALL NOT include raw user-editable `description`, frontmatter, or body excerpts from `SKILL.md`

### Requirement: Prompt component budget protection preserves core directives
The system SHALL enforce per-component and total prompt budgets while preserving core system directives, and trusted skill summaries SHALL remain lower priority than identity, strategy, and security directives.

#### Scenario: Budget protection truncates lower-priority components first
- **WHEN** the assembled system prompt exceeds the configured total budget
- **THEN** lower-priority components SHALL be truncated or dropped before higher-priority components
- **AND** identity, strategy, and security directives SHALL remain present in the final system prompt

#### Scenario: Trusted skill summaries do not displace core directives
- **WHEN** skill-related trusted summaries contribute to prompt growth
- **THEN** those summaries SHALL be truncated before identity, strategy, or security directives are removed

#### Scenario: Component truncation is explicit
- **WHEN** a prompt component exceeds its configured per-component budget
- **THEN** the resulting prompt text SHALL include an explicit truncation marker
- **AND** the truncated output SHALL remain syntactically readable to the model
