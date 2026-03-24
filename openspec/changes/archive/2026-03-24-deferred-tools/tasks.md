## 1. search_tools 工具实现

- [x] 1.1 新建 `src/nini/tools/search_tools.py`，实现 `SearchToolsTool`
- [x] 1.2 实现 `select:` 精确查询逻辑：解析名称列表，从注册表获取工具的完整 schema
- [x] 1.3 实现关键词搜索逻辑：对所有工具（含隐藏工具）的名称和 description 做不区分大小写子字符串匹配，返回最多 5 个结果
- [x] 1.4 `SearchToolsTool.__init__` 接收 `registry: ToolRegistry` 构造参数并存为实例变量，参考 `DispatchAgentsTool(spawner=spawner)` 的模式
- [x] 1.5 在 `src/nini/tools/registry.py` 的 `create_default_tool_registry()` 中注册 `SearchToolsTool`

## 2. 工具可见性分层

- [x] 2.1 在以下工具文件中将 `expose_to_llm` 改为返回 `False`：
  - `src/nini/tools/statistics/t_test.py`
  - `src/nini/tools/statistics/anova.py`（`AnovaTool`）
  - `src/nini/tools/statistics/nonparametric.py`（`MannWhitneyTool`、`KruskalWallisTool`）
  - `src/nini/tools/statistics/correlation.py`
  - `src/nini/tools/statistics/regression.py`
  - `src/nini/tools/export.py` 或对应的 `export_chart`、`export_document`、`export_report` 工具文件
  - `src/nini/tools/analysis_memory_tool.py`
  - `src/nini/tools/search_archive.py`（`search_memory_archive`）
  - `src/nini/tools/profile_notes.py`（`update_profile_notes`，如已设为 False 则跳过）
  - `src/nini/tools/fetch_url.py`

## 3. System Prompt 更新

- [x] 3.1 在 `src/nini/agent/prompts/builder.py` 中补充 `search_tools` 使用说明：当需要的工具不在工具列表时，通过 `search_tools` 按名称或关键词获取 schema

## 4. 测试

- [x] 4.1 新建 `tests/test_search_tools.py`
- [x] 4.2 测试 `select:` 精确查询：返回指定工具的 schema，不存在的工具名在结果中标注未找到
- [x] 4.3 测试关键词搜索：匹配工具名或 description 均能返回结果
- [x] 4.4 测试关键词无匹配：返回空列表
- [x] 4.5 测试 LLM 可见工具数量减少：`get_tool_definitions()` 返回结果不包含已隐藏的 13 个工具
- [x] 4.6 测试隐藏工具仍可通过 `search_tools` 发现
- [x] 4.7 运行 `pytest -q` 确认全量测试无回归

## 5. 验收

- [x] 5.1 确认 `get_tool_definitions()` 返回工具数量 ≤ 20 个（含 `search_tools`）
- [x] 5.2 手动验证：LLM 收到 `search_tools` 查询结果后能在同一轮对话中正确调用对应工具
- [x] 5.3 运行 `black --check src tests` 格式检查通过
- [x] 5.4 运行 `mypy src/nini/tools/search_tools.py` 无类型错误
