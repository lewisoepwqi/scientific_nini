## ADDED Requirements

### Requirement: EvidenceNode 模型
系统 SHALL 定义 `EvidenceNode` Pydantic 模型，包含 id、node_type、label、source_ref、parent_ids、metadata 字段。

#### Scenario: 节点可创建
- **WHEN** 创建 `EvidenceNode(id="n1", node_type="data", label="blood_pressure.csv")`
- **THEN** 实例创建成功，parent_ids 默认为空列表

#### Scenario: 节点类型限定
- **WHEN** node_type 取值
- **THEN** SHALL 为 "data"、"analysis"、"result"、"chart"、"conclusion" 之一

### Requirement: EvidenceChain 模型
系统 SHALL 定义 `EvidenceChain` Pydantic 模型，包含 session_id、nodes 列表、created_at。

#### Scenario: 链可创建
- **WHEN** 创建 EvidenceChain 并添加多个节点
- **THEN** nodes 列表包含所有添加的节点

### Requirement: EvidenceCollector 收集器
系统 SHALL 提供 `EvidenceCollector` 类，挂载在 Session 上，支持按节点类型添加证据节点。

#### Scenario: 添加数据节点
- **WHEN** 调用 `collector.add_data_node("blood_pressure.csv")`
- **THEN** 证据链中新增一个 node_type="data" 的节点

#### Scenario: 添加分析节点关联数据
- **WHEN** 调用 `collector.add_analysis_node("t_test", params={...}, parent_ids=["data_node_id"])`
- **THEN** 新节点的 parent_ids 包含数据节点 ID

#### Scenario: 获取上游链
- **WHEN** 调用 `collector.get_chain_for(conclusion_node_id)`
- **THEN** 返回从结论节点到所有上游数据来源的完整路径

### Requirement: Skill 契约集成
当 SkillContract.evidence_required=true 时，ContractRunner SHALL 在每步 Tool 执行后自动调用 EvidenceCollector。

#### Scenario: evidence_required 触发自动收集
- **WHEN** Skill 的 evidence_required=true 且某步骤调用了统计工具
- **THEN** EvidenceCollector 自动添加对应的分析节点

#### Scenario: evidence_required=false 不收集
- **WHEN** Skill 的 evidence_required=false
- **THEN** ContractRunner 不调用 EvidenceCollector

### Requirement: query_evidence 工具
系统 SHALL 提供 `query_evidence` 工具，允许查询特定结论的完整证据链。

#### Scenario: 查询返回证据链
- **WHEN** 调用 query_evidence(query="治疗组血压显著低于对照组")
- **THEN** 返回该结论相关的证据链（结论→统计结果→数据来源）

#### Scenario: 无匹配时返回空
- **WHEN** 调用 query_evidence 但会话中无相关证据
- **THEN** 返回空证据链提示

### Requirement: 工具注册
query_evidence SHALL 在 `tools/registry.py` 中注册。

#### Scenario: 工具可查询
- **WHEN** 从 ToolRegistry 中查询 "query_evidence"
- **THEN** 返回对应的 Tool 实例
