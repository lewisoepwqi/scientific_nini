## ADDED Requirements

### Requirement: Classify query intent
The system SHALL classify user queries into predefined intent categories: concept, how-to, reference, code, comparison, troubleshoot.

#### Scenario: Classify concept query
- **WHEN** user asks "什么是t检验"
- **THEN** system classifies intent as "concept"

#### Scenario: Classify how-to query
- **WHEN** user asks "如何做方差分析"
- **THEN** system classifies intent as "how-to"

#### Scenario: Classify reference query
- **WHEN** user asks "t检验的参数说明"
- **THEN** system classifies intent as "reference"

#### Scenario: Classify code query
- **WHEN** user asks "相关性分析的Python代码"
- **THEN** system classifies intent as "code"

### Requirement: Route query to appropriate index level
The system SHALL route queries to appropriate hierarchical index levels based on classified intent.

#### Scenario: Route concept query to L0
- **WHEN** intent is "concept"
- **THEN** system routes to L0 (document level) with top_k=3

#### Scenario: Route how-to query to L1
- **WHEN** intent is "how-to"
- **THEN** system routes to L1 (section level) with top_k=5

#### Scenario: Route reference/code query to L2
- **WHEN** intent is "reference" or "code"
- **THEN** system routes to L2 (chunk level) with top_k=5

### Requirement: Support hybrid routing
The system SHALL support hybrid routing that searches multiple levels and merges results.

#### Scenario: Comparison query searches multiple levels
- **WHEN** intent is "comparison"
- **THEN** system searches both L0 and L1, then merges results

### Requirement: Provide routing transparency
The system SHALL expose routing decisions for debugging and explainability.

#### Scenario: Return routing metadata
- **WHEN** a search is performed
- **THEN** the response includes intent classification and routing decisions
