## ADDED Requirements

### Requirement: Support multi-source retrieval
The system SHALL support retrieving from multiple sources: BM25 index, vector index, and long-term memory.

#### Scenario: Parallel retrieval from BM25 and vector
- **WHEN** a query is submitted with hybrid strategy
- **THEN** system retrieves from BM25 and vector indexes in parallel

#### Scenario: Include long-term memory
- **WHEN** unified retrieval is requested
- **THEN** system also searches long-term memory store

### Requirement: Implement RRF fusion
The system SHALL implement Reciprocal Rank Fusion (RRF) to merge results from multiple sources.

#### Scenario: Fuse BM25 and vector results
- **WHEN** BM25 returns [docA, docB, docC] and vector returns [docB, docD, docA]
- **THEN** RRF produces fused ranking [docB, docA, docD, docC]

#### Scenario: Handle different result counts
- **WHEN** sources return different numbers of results
- **THEN** RRF handles gracefully without errors

### Requirement: Support configurable weights
The system SHALL support configurable weights for different retrieval sources.

#### Scenario: Prioritize BM25 results
- **WHEN** bm25_weight=0.7 and vector_weight=0.3
- **THEN** BM25 results have higher influence in final ranking

### Requirement: Assemble retrieval context
The system SHALL assemble retrieved content into a coherent context for LLM consumption.

#### Scenario: Assemble with token budget
- **WHEN** max_tokens=3000 is specified
- **THEN** system assembles context within token limit, prioritizing higher-ranked results

#### Scenario: Include source attribution
- **WHEN** context is assembled
- **THEN** each section includes source reference for citation

### Requirement: Support caching
The system SHALL cache retrieval results for identical queries to improve performance.

#### Scenario: Cache hit
- **WHEN** identical query is submitted within cache TTL
- **THEN** system returns cached results without re-retrieval

#### Scenario: Cache invalidation
- **WHEN** underlying index is updated
- **THEN** related cache entries are invalidated
