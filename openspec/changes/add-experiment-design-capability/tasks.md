## 1. sample_size 工具

- [ ] 1.1 创建 `src/nini/tools/sample_size.py`，继承 Tool 基类，实现两组 t 检验、ANOVA、比例差异三种设计的样本量计算
- [ ] 1.2 在 `src/nini/tools/registry.py` 的 `create_default_tool_registry()` 中注册 sample_size 工具

## 2. experiment-design-helper Skill

- [ ] 2.1 创建 `.nini/skills/experiment-design-helper/SKILL.md`，编写 YAML frontmatter（含 contract 段：4 步线性 DAG、trust_ceiling=t1、generate_plan 步骤 review_gate=true）
- [ ] 2.2 编写 Skill 正文工作流：每步的 LLM 提示模板、输出规范、伦理提示规则、O2 等级标注声明

## 3. 测试与验证

- [ ] 3.1 编写 `tests/test_sample_size.py`：验证三种设计类型的计算准确性、参数缺失错误处理
- [ ] 3.2 编写 `tests/test_experiment_design_skill.py`：验证 Skill 可被扫描发现、contract 可解析、步骤顺序正确、review_gate 位置正确
- [ ] 3.3 运行 `pytest -q` 确认全部测试通过且无回归
