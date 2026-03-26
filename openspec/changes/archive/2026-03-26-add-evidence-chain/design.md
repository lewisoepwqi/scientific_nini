## Context

现有模型：`SourceRecord`（来源记录：type/label/detail/url/metadata）、`EvidenceBlock`（证据块：claim/evidence_text/sources/confidence）、`MethodsLedgerEntry`（方法记录：tool_name/parameters/results_ref/evidence_blocks）。C4 的 SkillContract 有 evidence_required 字段。这些为证据链提供了数据基础。

## Goals / Non-Goals

**Goals:**
- 建立跨步骤的证据链关联模型
- 实现自动证据收集（Tool 执行钩子）
- 与 Skill 契约的 evidence_required 集成
- 提供证据链查询能力

**Non-Goals:**
- 不实现 UI 可视化
- 不实现跨会话持久化

## Decisions

### D1: EvidenceChain 模型

**选择**：

```python
class EvidenceNode(BaseModel):
    id: str                                    # 节点 ID（UUID）
    node_type: str                             # "data" | "analysis" | "result" | "chart" | "conclusion"
    label: str                                 # 节点描述
    source_ref: str | None = None              # 来源引用（数据集名、工具名、图表路径等）
    parent_ids: list[str] = []                 # 上游节点 ID 列表
    metadata: dict[str, Any] = {}              # 附加信息

class EvidenceChain(BaseModel):
    session_id: str
    nodes: list[EvidenceNode] = []
    created_at: datetime
```

**理由**：DAG 结构的证据链，每个节点可有多个上游节点（如一个结论基于多个统计结果）。node_type 区分不同类型的证据节点。

### D2: 证据收集器设计

**选择**：`EvidenceCollector` 类，挂载在 Session 上，提供：
- `add_data_node(dataset_name)` → 添加数据来源节点
- `add_analysis_node(tool_name, params, result_ref, parent_ids)` → 添加分析节点
- `add_chart_node(chart_path, parent_ids)` → 添加图表节点
- `add_conclusion_node(claim, parent_ids)` → 添加结论节点
- `get_chain_for(node_id)` → 获取指定节点的完整上游链

**理由**：会话级别的收集器，生命周期与 Session 一致。方法名按节点类型区分，便于在不同 Tool 的执行后调用。

### D3: 与 Skill 契约的集成

**选择**：在 `ContractRunner` 中，当 contract.evidence_required=true 时：
1. 在每步 Tool 调用后，自动调用 EvidenceCollector 添加对应类型的节点
2. 在 contract 完成时，将证据链附加到 ContractResult

**理由**：自动化收集，不依赖 LLM 主动调用。仅在 evidence_required=true 时启用。

### D4: query_evidence 工具

**选择**：继承 Tool 基类，参数：query（结论或关键词）。返回该结论相关的完整证据链（从结论节点回溯到数据来源）。

**理由**：允许 Agent 在写作阶段查询分析阶段的证据链，实现跨阶段溯源。也可被用户直接使用。

## Risks / Trade-offs

- **[风险] 证据收集增加执行开销** → 仅在 evidence_required=true 时启用，且为内存操作，开销极小。
- **[风险] 证据链不完整** → V1 仅收集 Tool 执行产生的节点，LLM 推理过程中的中间结论不追踪。后续可扩展。
- **[回滚]** 删除新建文件 + revert contract_runner.py 即可恢复。
