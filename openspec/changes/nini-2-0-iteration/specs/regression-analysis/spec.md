## ADDED Requirements

### Requirement: Regression analysis composite skill template
The system SHALL provide a regression_analysis composite skill template.

#### Scenario: Execute regression workflow
- **WHEN** regression analysis is triggered
- **THEN** the system SHALL perform data quality check
- **AND** perform assumption testing (linearity, normality, homoscedasticity)
- **AND** execute linear or multiple regression as appropriate
- **AND** perform residual diagnostics
- **AND** generate visualization
- **AND** format results in APA style

### Requirement: Regression analysis capability is executable
The regression_analysis capability SHALL be fully implemented and executable.

#### Scenario: Regression capability returns 200
- **WHEN** the regression_analysis capability is invoked
- **THEN** it SHALL return HTTP 200 with analysis results
- **AND** it SHALL NOT return 409 (not implemented)

#### Scenario: Regression capability handles various data types
- **WHEN** regression is requested on different dataset types
- **THEN** it SHALL automatically select simple linear or multiple regression
- **AND** it SHALL handle categorical predictors appropriately
