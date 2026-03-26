## 1. search_literature 工具

- [ ] 1.1 创建 `src/nini/tools/search_literature.py`，继承 Tool 基类，实现 Semantic Scholar API 和 CrossRef API 集成
- [ ] 1.2 实现 API 降级链（Semantic Scholar → CrossRef → 降级 ToolResult）
- [ ] 1.3 实现请求限流（每秒 1 请求）
- [ ] 1.4 实现 NetworkPlugin 可用性检测前置检查
- [ ] 1.5 在 `tools/registry.py` 中注册 search_literature 工具

## 2. NetworkPlugin 扩展

- [ ] 2.1 在 `src/nini/plugins/network.py` 中扩展 is_available() 检测 Semantic Scholar API 端点可达性

## 3. literature-review Skill

- [ ] 3.1 创建 `.nini/skills/literature-review/SKILL.md`，编写 YAML frontmatter（含 contract 段：4 步 DAG、trust_ceiling=t1、evidence_required=true）
- [ ] 3.2 编写 Skill 正文工作流：检索/手动模式切换、筛选引导、综合模板（含证据溯源）、输出规范和 O2 等级标注

## 4. 测试与验证

- [ ] 4.1 编写 `tests/test_search_literature.py`：API 调用（mock）、降级链、限流、离线降级
- [ ] 4.2 编写 `tests/test_literature_review_skill.py`：Skill 发现、contract 解析、离线降级路径
- [ ] 4.3 运行 `pytest -q` 确认全部测试通过且无回归
