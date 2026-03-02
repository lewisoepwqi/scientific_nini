## ADDED Requirements

### Requirement: Statistical tests auto-degrade on non-normal data
The system SHALL automatically degrade statistical tests when normality assumptions are violated.

#### Scenario: t_test degrades to mann_whitney
- **WHEN** a t_test is requested on non-normal data
- **THEN** the system SHALL execute mann_whitney instead
- **AND** the system SHALL push a REASONING event explaining the degradation

#### Scenario: anova degrades to kruskal_wallis
- **WHEN** anova is requested on non-normal data
- **THEN** the system SHALL execute kruskal_wallis instead
- **AND** the system SHALL push a REASONING event explaining the degradation

### Requirement: Fallback mechanism is transparent to user
The system SHALL notify users when statistical test degradation occurs.

#### Scenario: REASONING event on degradation
- **WHEN** a statistical test is automatically degraded
- **THEN** a REASONING event SHALL be emitted with explanation
- **AND** the event SHALL include original_test and fallback_test names
