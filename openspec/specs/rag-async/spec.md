# Capability: RAG Async

## Purpose

Ensure RAG hybrid retrieval uses proper async/await patterns for reliable knowledge retrieval.

## Requirements

### Requirement: RAG hybrid retrieval uses proper async/await

The RAG hybrid retrieval system MUST use proper async/await patterns instead of run_until_complete.

#### Scenario: Async retrieval succeeds

- **WHEN** the agent triggers knowledge retrieval in an async context
- **THEN** the system SHALL await inject_knowledge_to_prompt() without RuntimeError

#### Scenario: Fallback to keyword search on empty results

- **WHEN** no documents are retrieved from hybrid search
- **THEN** the system SHALL gracefully fall back to keyword search
- **AND** the fallback SHALL NOT raise exceptions
