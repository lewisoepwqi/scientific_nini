## Why

V1 纲领的核心价值之一是「证据溯源」——每个结论可追溯到数据来源和分析步骤。现有代码中有 `EvidenceBlock`、`SourceRecord`、`MethodsLedgerEntry` 等基础模型，但缺少跨步骤的证据链追踪机制。当用户从数据分析过渡到论文写作时，无法自动追踪「结论 A 来自统计检验 B，使用数据集 C，图表 D 支撑」这样的证据链。本 change 实现证据链追踪系统，使每个输出都可回溯到原始数据和分析步骤。

## What Changes

- **新增证据链模型**：在 `models/` 中扩展 `EvidenceBlock`，新增 `EvidenceChain` 模型，支持多层级证据关联（结论 → 统计结果 → 数据 → 来源）。
- **新增证据链收集器**：在 `agent/` 中新增 `evidence_collector.py`，在 Tool 执行过程中自动收集和关联证据节点。
- **与 Skill 契约集成**：当 SkillContract 的 evidence_required=true 时，ContractRunner 在每步执行后自动调用证据收集器。
- **证据链查询工具**：新增 `query_evidence` 工具，允许 Agent 和用户查询特定结论的证据链。

## Non-Goals

- 不实现证据链的可视化 UI。
- 不实现跨会话的证据链持久化。
- 不实现自动化的证据完整性验证（仅收集和查询）。

## Capabilities

### New Capabilities

- `evidence-chain`: 证据链追踪——涵盖 EvidenceChain 模型、证据收集器、Skill 契约集成、查询工具

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`src/nini/models/session_resources.py`（扩展模型）、`src/nini/agent/evidence_collector.py`（新建）、`src/nini/tools/query_evidence.py`（新建）、`src/nini/skills/contract_runner.py`（集成证据收集）、`src/nini/tools/registry.py`（注册）
- **影响范围**：Tool 执行流程新增证据收集钩子（可选，不影响无 evidence 需求的场景）
- **API / 依赖**：无新增外部依赖
- **风险**：证据收集可能增加执行开销——仅在 evidence_required=true 的 Skill 中启用
- **回滚**：删除新建文件 + revert session_resources.py 和 contract_runner.py 即可恢复
- **验证方式**：单元测试验证证据链模型、收集器逻辑、查询功能；集成测试验证 Skill 契约中的证据收集
