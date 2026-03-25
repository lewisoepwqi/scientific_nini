# Capability: Knowledge Retrieval

## Purpose

Enable the Agent to leverage domain-specific knowledge from a managed knowledge base to enhance analysis quality and accuracy.

## Requirements

### Requirement: Hybrid knowledge retrieval

The system SHALL integrate vector search with keyword search for improved knowledge retrieval. 查询结果 SHALL 包含 `availability` 元数据字段，使调用方可区分"无匹配结果"和"检索系统未就绪"。

#### Scenario: Combined search results

- **WHEN** the Agent queries the knowledge base
- **THEN** the system SHALL perform both vector similarity search AND keyword matching
- **AND** the results SHALL be ranked using a combined relevance score
- **AND** the top N results (configurable, default 5) SHALL be returned

#### Scenario: Vector search with local embedding

- **WHEN** the system performs vector search
- **THEN** it SHALL use the local BAAI/bge-small-zh-v1.5 embedding model (already available)
- **AND** the search SHALL support Chinese text with semantic understanding

#### Scenario: Keyword search fallback

- **WHEN** vector search returns insufficient results (below relevance threshold)
- **THEN** the system SHALL fallback to keyword search
- **AND** the combined results SHALL be marked with their source method

#### Scenario: 知识库未就绪时返回状态元数据

- **WHEN** 向量库未初始化或知识目录为空
- **THEN** 查询 SHALL 返回空结果，且 `availability` 字段 SHALL 为 `"not_ready"` 或 `"empty"`
- **AND** 调用方可据此决定是否向用户提示知识库状态

#### Scenario: 知识库正常但无匹配

- **WHEN** 向量库已初始化且知识目录非空，但查询无匹配结果
- **THEN** `availability` 字段 SHALL 为 `"available"`
- **AND** 结果列表为空

### Requirement: Knowledge citation in responses

The system SHALL display knowledge source citations in Agent responses.

#### Scenario: Inline citation markers

- **WHEN** the Agent uses knowledge base information in a response
- **THEN** the relevant text SHALL include citation markers (e.g., [1], [2])
- **AND** hovering over the marker SHALL show the source document title

#### Scenario: Citation list panel

- **WHEN** the user clicks a citation marker
- **THEN** a citation panel SHALL open showing all referenced sources
- **AND** each source SHALL display: document title, relevant excerpt, link to full document (if available)

#### Scenario: Confidence scoring display

- **WHEN** knowledge is retrieved and used
- **THEN** the citation SHALL include a relevance score indicator
- **AND** low-confidence retrievals (below 0.5) SHALL be visually flagged

### Requirement: Knowledge base management UI

The system SHALL provide a user interface for managing knowledge base documents.

#### Scenario: Document list view

- **WHEN** the user opens the knowledge base panel
- **THEN** a list of all indexed documents SHALL be displayed
- **AND** each document SHALL show: title, upload date, document type, index status

#### Scenario: Document upload

- **WHEN** the user clicks "上传文档"
- **THEN** a file picker SHALL allow selection of supported formats (PDF, TXT, MD)
- **AND** the document SHALL be processed and indexed asynchronously
- **AND** the user SHALL receive a notification when indexing is complete

#### Scenario: Document deletion

- **WHEN** the user selects a document and clicks "删除"
- **THEN** a confirmation dialog SHALL appear
- **AND** upon confirmation, the document SHALL be removed from the index
- **AND** the document SHALL no longer appear in search results

### Requirement: Knowledge search API endpoint

The system SHALL expose an API endpoint for knowledge base search.

#### Scenario: Search endpoint

- **WHEN** a POST request is made to `/api/knowledge/search` with query parameters
- **THEN** the system SHALL return search results including:
  - query: the original search query
  - results: array of matching documents with relevance scores
  - total_count: total number of matches
  - search_method: "vector" | "keyword" | "hybrid"

#### Scenario: Document management endpoints

- **WHEN** a GET request is made to `/api/knowledge/documents`
- **THEN** the system SHALL return a list of all indexed documents
- **AND** POST `/api/knowledge/documents` SHALL accept new document uploads
- **AND** DELETE `/api/knowledge/documents/{id}` SHALL remove a document

### Requirement: Knowledge retrieval integration with Agent

The system SHALL integrate knowledge retrieval into the Agent's context building process.

#### Scenario: Automatic knowledge retrieval

- **WHEN** the Agent is building context for a user query
- **THEN** the system SHALL automatically query the knowledge base
- **AND** relevant results SHALL be injected into the system prompt as context

#### Scenario: Domain-specific knowledge boost

- **WHEN** the user's research profile has a domain preference set
- **THEN** knowledge retrieval SHALL prioritize documents from that domain
- **AND** the relevance scoring SHALL be weighted by domain match

#### Scenario: Knowledge context size limit

- **WHEN** injecting knowledge into the context
- **THEN** the total knowledge context SHALL not exceed 2000 tokens
- **AND** if exceeded, only the top-ranked results within the limit SHALL be included
