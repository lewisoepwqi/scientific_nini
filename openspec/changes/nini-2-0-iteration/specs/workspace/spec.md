## ADDED Requirements

### Requirement: Knowledge base document upload
The system SHALL provide API endpoints for uploading knowledge documents and triggering index rebuild.

#### Scenario: Upload knowledge document
- **WHEN** user uploads a document via knowledge management UI
- **THEN** the system SHALL save the file to knowledge base directory
- **AND** the system SHALL trigger async indexing
- **AND** progress SHALL be reported via WebSocket events

#### Scenario: Trigger index rebuild
- **WHEN** user requests index rebuild via API
- **THEN** the system SHALL rebuild the vector index
- **AND** the new index SHALL be used for subsequent RAG queries

#### Scenario: Knowledge retrieval results visualization
- **WHEN** knowledge retrieval is triggered during conversation
- **THEN** retrieval results SHALL be displayed in UI with source, relevance score, and excerpt
- **AND** users SHALL be able to click to view source document
