## 1. collect_artifacts 工具

- [x] 1.1 创建 `src/nini/tools/collect_artifacts.py`，继承 Tool 基类，实现从 Session 收集统计结果、图表、方法记录、数据集概要
- [x] 1.2 定义素材包 JSON 结构（statistical_results、charts、methods、datasets、summary）
- [x] 1.3 在 `tools/registry.py` 中注册 collect_artifacts 工具

## 2. writing-guide Skill

- [x] 2.1 创建 `.nini/skills/writing-guide/SKILL.md`，编写 YAML frontmatter（含 contract 段：4 步 DAG、trust_ceiling=t1）
- [x] 2.2 编写 Skill 正文工作流：素材收集、结构规划、分节撰写引导（含统计结果/图表嵌入模板）、修订建议

## 3. 测试与验证

- [x] 3.1 编写 `tests/test_collect_artifacts.py`：有产物/无产物会话的收集、素材包结构验证
- [x] 3.2 编写 `tests/test_writing_guide_skill.py`：Skill 发现、contract 解析
- [x] 3.3 运行 `pytest -q` 确认全部测试通过且无回归
