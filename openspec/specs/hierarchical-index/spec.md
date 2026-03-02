## ADDED Requirements

### Requirement: Parse Markdown document structure
The system SHALL parse Markdown documents to extract hierarchical structure including document title, sections (H1-H3), and paragraphs.

#### Scenario: Parse document with multiple sections
- **WHEN** a Markdown file with H1, H2, H3 headings is loaded
- **THEN** the system extracts the document tree with proper parent-child relationships

#### Scenario: Handle documents without clear structure
- **WHEN** a Markdown file without standard headings is loaded
- **THEN** the system creates a flat structure with the entire document as a single section

### Requirement: Build three-level hierarchical index
The system SHALL build and maintain three-level indexes: L0 (document level), L1 (section level), and L2 (chunk level).

#### Scenario: Build index from knowledge directory
- **WHEN** the knowledge directory contains multiple Markdown files
- **THEN** the system builds L0, L1, L2 indexes with proper cross-references

#### Scenario: Incremental index update
- **WHEN** a Markdown file is added, modified, or removed
- **THEN** the system updates only affected index entries without full rebuild

### Requirement: Support hierarchical search
The system SHALL support searching at specific levels or across all levels with level-aware scoring.

#### Scenario: Search at document level
- **WHEN** user searches with intent type "concept"
- **THEN** system primarily searches L0 index (document summaries)

#### Scenario: Search at section level
- **WHEN** user searches with intent type "how-to"
- **THEN** system primarily searches L1 index (section contents)

#### Scenario: Search at chunk level
- **WHEN** user searches with intent type "reference" or "code"
- **THEN** system searches L2 index (paragraph chunks)

### Requirement: Maintain parent-child relationships
The system SHALL maintain bidirectional parent-child relationships between index levels for context assembly.

#### Scenario: Retrieve with context
- **WHEN** a L2 chunk is retrieved
- **THEN** the system can traverse up to get its parent section and document context

#### Scenario: Navigate down
- **WHEN** a document is selected at L0
- **THEN** the system can retrieve all child sections and chunks

### Requirement: Persist hierarchical index
The system SHALL persist hierarchical index to disk with version tracking for cache invalidation.

#### Scenario: Save and load index
- **WHEN** the index is built successfully
- **THEN** the system saves it to disk and can reload on restart

#### Scenario: Detect stale index
- **WHEN** source files change
- **THEN** the system detects stale index and triggers incremental update
