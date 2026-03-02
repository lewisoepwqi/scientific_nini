## MODIFIED Requirements

### Requirement: Statistical skills support fallback degradation
The system SHALL automatically fallback to non-parametric alternatives when parametric test assumptions are violated.

#### Scenario: t_test degrades to mann_whitney on non-normal data
- **WHEN** t_test is called through execute_with_fallback
- **AND** the data fails normality test
- **THEN** mann_whitney SHALL be executed instead
- **AND** a REASONING event SHALL explain the degradation

#### Scenario: anova degrades to kruskal_wallis on non-normal data
- **WHEN** anova is called through execute_with_fallback
- **AND** the data fails normality test
- **THEN** kruskal_wallis SHALL be executed instead
- **AND** a REASONING event SHALL explain the degradation

#### Scenario: Fallback is transparent in tool results
- **WHEN** a statistical test is automatically degraded
- **THEN** the tool_result SHALL indicate the actual test executed
- **AND** the original requested test name SHALL be preserved in metadata
