## 1. 证据链模型

- [x] 1.1 在 `src/nini/models/session_resources.py` 中新增 `EvidenceNode` 和 `EvidenceChain` Pydantic 模型

## 2. 证据收集器

- [x] 2.1 创建 `src/nini/agent/evidence_collector.py`，实现 `EvidenceCollector` 类（add_data_node、add_analysis_node、add_chart_node、add_conclusion_node、get_chain_for）
- [x] 2.2 在 Session 中挂载 EvidenceCollector 实例

## 3. Skill 契约集成

- [x] 3.1 在 `src/nini/skills/contract_runner.py` 中，当 evidence_required=true 时，在每步 Tool 执行后自动调用 EvidenceCollector

## 4. 查询工具

- [x] 4.1 创建 `src/nini/tools/query_evidence.py`，继承 Tool 基类，实现证据链查询
- [x] 4.2 在 `tools/registry.py` 中注册 query_evidence 工具

## 5. 测试与验证

- [x] 5.1 编写 `tests/test_evidence_chain.py`：模型创建、节点添加、上游链查询、Skill 集成（mock ContractRunner）
- [x] 5.2 运行 `pytest -q` 确认全部测试通过且无回归
