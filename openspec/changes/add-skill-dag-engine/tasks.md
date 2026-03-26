## 1. SkillStep 扩展

- [ ] 1.1 在 `src/nini/models/skill_contract.py` 的 SkillStep 中新增 condition、input_from、output_key 可选字段

## 2. DAG 执行引擎

- [ ] 2.1 在 `src/nini/skills/contract_runner.py` 中实现分层拓扑排序（输出分层列表而非扁平列表）
- [ ] 2.2 实现并行执行逻辑（asyncio.gather + return_exceptions=True）
- [ ] 2.3 实现步骤间共享上下文和数据传递（output_key 写入 / input_from 读取）
- [ ] 2.4 实现条件步骤评估（安全的表达式评估，白名单变量上下文）
- [ ] 2.5 在 SkillStepEventData 中新增 layer 字段

## 3. 测试与验证

- [ ] 3.1 编写 `tests/test_dag_engine.py`：并行分支执行、汇合点等待、条件跳过、数据传递、并行失败处理
- [ ] 3.2 编写回归测试：现有线性 Skill 在新引擎上行为不变
- [ ] 3.3 运行 `pytest -q` 确认全部测试通过且无回归
