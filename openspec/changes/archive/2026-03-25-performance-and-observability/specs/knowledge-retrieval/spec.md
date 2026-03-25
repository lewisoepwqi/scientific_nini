## MODIFIED Requirements

### Requirement: Hybrid knowledge retrieval
The system SHALL integrate vector search with keyword search for improved knowledge retrieval. 查询结果 SHALL 包含 `availability` 元数据字段，使调用方可区分"无匹配结果"和"检索系统未就绪"。

#### Scenario: Combined search results
- **WHEN** the Agent queries the knowledge base
- **THEN** the system SHALL perform both vector similarity search AND keyword matching
- **AND** the results SHALL be ranked using a combined relevance score
- **AND** the top N results (configurable, default 5) SHALL be returned

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
