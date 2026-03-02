## ADDED Requirements

### Requirement: Re-rank retrieval results
The system SHALL re-rank initial retrieval results using a cross-encoder model for improved relevance.

#### Scenario: Re-rank top-k candidates
- **WHEN** initial retrieval returns 20 candidates
- **THEN** cross-encoder re-ranks them and returns top 5 most relevant

#### Scenario: Handle empty results
- **WHEN** no candidates are retrieved
- **THEN** re-ranking returns empty list without error

### Requirement: Support optional reranking
The system SHALL make reranking optional and configurable.

#### Scenario: Disable reranking
- **WHEN** reranking is disabled in configuration
- **THEN** system skips reranking step and returns initial results

#### Scenario: Model unavailable fallback
- **WHEN** cross-encoder model fails to load
- **THEN** system gracefully falls back to initial ranking

### Requirement: Batch processing
The system SHALL process reranking in batches for efficiency.

#### Scenario: Batch encode query-document pairs
- **WHEN** 20 candidates need reranking
- **THEN** system processes them in configurable batch size (default 8)

### Requirement: Expose reranking scores
The system SHALL expose reranking scores for transparency and debugging.

#### Scenario: Return rerank scores in metadata
- **WHEN** results are reranked
- **THEN** response includes both initial score and rerank score

### Requirement: Support lightweight models
The system SHALL support lightweight cross-encoder models suitable for local deployment.

#### Scenario: Use BGE reranker
- **WHEN** configured with BAAI/bge-reranker-base
- **THEN** system loads and uses the specified model
