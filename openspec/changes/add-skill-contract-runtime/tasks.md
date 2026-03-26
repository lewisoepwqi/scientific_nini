## 1. Skill 契约数据模型

- [ ] 1.1 创建 `src/nini/models/skill_contract.py`，定义 `SkillStep`、`SkillContract`、`ContractResult` Pydantic 模型
- [ ] 1.2 在 `SkillContract` 中实现 depends_on 引用验证（model_validator）
- [ ] 1.3 在 `SkillContract` 中实现循环依赖检测（model_validator）
- [ ] 1.4 在 `SkillContract` 中实现 trust_ceiling 约束验证（step.trust_level 不超过 contract.trust_ceiling）
- [ ] 1.5 在 `src/nini/models/__init__.py` 中导出新模型

## 2. Observability 事件

- [ ] 2.1 在 `src/nini/models/event_schemas.py` 中新增 `SkillStepEventData` 模型

## 3. 契约解析器

- [ ] 3.1 扩展 `src/nini/tools/markdown_scanner.py`，在 frontmatter 解析时检测 `contract` 键并实例化为 `SkillContract`，存入 `MarkdownTool.metadata["contract"]`
- [ ] 3.2 处理 contract 格式错误的优雅降级（记录警告，不阻断 Skill 加载）

## 4. 契约运行时

- [ ] 4.1 创建 `src/nini/skills/contract_runner.py`，实现 `ContractRunner` 类
- [ ] 4.2 实现拓扑排序逻辑（`_topological_sort`）
- [ ] 4.3 实现步骤逐步执行循环（start 事件 → 执行 → complete/failed 事件）
- [ ] 4.4 实现 review_gate 阻塞机制（asyncio.Event 等待 + 超时处理）
- [ ] 4.5 实现 retry_policy 失败处理（retry / skip / abort）
- [ ] 4.6 实现 ContractResult 汇总（completed / partial / failed）

## 5. 工具适配器路由

- [ ] 5.1 扩展 `src/nini/tools/tool_adapter.py`，检测 metadata["contract"] 存在时路由到 ContractRunner

## 6. 测试与验证

- [ ] 6.1 编写 `tests/test_skill_contract_model.py`：模型实例化、序列化、依赖验证、循环检测、trust_ceiling 约束
- [ ] 6.2 编写 `tests/test_contract_runner.py`：线性 DAG 执行、review_gate 模拟、失败处理、事件发射
- [ ] 6.3 编写 `tests/test_scanner_contract.py`：带 contract 的 Skill 解析、无 contract 兼容、格式错误降级
- [ ] 6.4 运行 `pytest -q` 确认全部测试通过且无回归
