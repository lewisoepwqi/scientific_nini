## 1. 修复 Harness 完成校验误判（BUG-001）

- [ ] 1.1 在 `src/nini/harness/runner.py` 顶部将 `promised_artifact` 匹配正则提取为模块级常量 `_PROMISED_ARTIFACT_RE`，采用"完成语义词 + 产物词共现"模式
- [ ] 1.2 将第 385 行的内联正则替换为 `bool(_PROMISED_ARTIFACT_RE.search(final_text))`
- [ ] 1.3 编写测试：发送能力介绍类回答（含"图表"/"报告"但无完成语义词），断言 `artifact_generated` 校验项 `passed=True`
- [ ] 1.4 编写测试：发送含"以下是分析报告"的回答，断言 `artifact_generated` 校验项 `passed=False`（触发校验）
- [ ] 1.5 运行 `pytest tests/ -q` 验证全部测试通过

## 2. 补全 TaskRouter 三条缺失路由规则（BUG-002）

- [ ] 2.1 在 `src/nini/agent/router.py` 的 `_BUILTIN_RULES` 末尾追加 `citation_manager` 规则：`frozenset({"引用格式", "参考文献", "文献管理", "bibliography", "citation"})`
- [ ] 2.2 追加 `research_planner` 规则：`frozenset({"研究规划", "研究设计", "实验设计", "研究方案", "研究思路"})`
- [ ] 2.3 追加 `review_assistant` 规则：`frozenset({"审稿", "同行评审", "评审意见", "回复审稿", "修改意见"})`
- [ ] 2.4 更新 `_LLM_ROUTING_PROMPT` 的可用 Agent 列表，补充三个 Agent 的 ID 和描述
- [ ] 2.5 更新 `_LLM_BATCH_ROUTING_PROMPT` 的 Agent 列表注释，与 2.4 保持一致
- [ ] 2.6 编写测试：断言"参考文献格式化"意图路由到 `citation_manager`，strategy 为 `"rule"`，confidence >= 0.7
- [ ] 2.7 编写测试：断言"实验设计方案"意图路由到 `research_planner`
- [ ] 2.8 编写测试：断言"回复审稿意见"意图路由到 `review_assistant`
- [ ] 2.9 运行 `pytest tests/ -q` 验证全部测试通过

## 3. 同义词表 YAML 外置化

- [ ] 3.1 运行 `python -c "import yaml"` 确认 PyYAML 可用；若不可用则在 `pyproject.toml` 的依赖中显式添加 `pyyaml`
- [ ] 3.2 在 `src/nini/intent/optimized.py` 中新增模块级私有函数 `_load_synonym_map() -> dict[str, list[str]]`，读取 `config/intent_synonyms.yaml`，失败时回退到 `_SYNONYM_MAP` 并记录日志；在文件顶部添加 `import yaml`
- [ ] 3.3 在 `OptimizedIntentAnalyzer.__init__` 中调用 `_load_synonym_map()` 替换内置 dict 的直接引用
- [ ] 3.4 创建 `config/intent_synonyms.yaml`，内容与现有 `_SYNONYM_MAP` 完全一致（8 个 capability 的同义词列表）
- [ ] 3.5 编写测试：配置文件存在时，分析器使用 YAML 中的同义词（可加入一个仅在 YAML 中存在的测试词）
- [ ] 3.6 编写测试：配置文件不存在时，分析器正常回退到内置 dict，不抛出异常
- [ ] 3.7 编写测试：配置文件格式非法（非 dict）时，分析器回退内置并记录 WARNING
- [ ] 3.8 编写测试：配置文件中某 value 非列表（如字符串）时，该条目被跳过，其余正常加载
- [ ] 3.9 运行 `pytest tests/ -q` 验证全部测试通过

## 4. 集成验证与收尾

- [ ] 4.1 启动开发服务器（`nini start --reload`），发送"你是谁"确认不触发双回答
- [ ] 4.2 发送"帮我整理审稿意见"，确认 harness trace 中路由到 `review_assistant`
- [ ] 4.3 发送"格式化参考文献"，确认路由到 `citation_manager`
- [ ] 4.4 修改 `config/intent_synonyms.yaml` 加入新词，重启后确认意图分析器识别新词
- [ ] 4.5 运行 `black --check src tests` 和 `mypy src/nini` 验证格式与类型检查通过
- [ ] 4.6 按 git workflow 规范创建分支 `fix/intent-routing-harness`，提交并创建 PR
