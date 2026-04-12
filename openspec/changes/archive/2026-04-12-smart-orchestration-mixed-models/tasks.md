## 1. AgentDefinition 字段扩展

- [x] 1.1 修改 `registry.py:AgentDefinition`：新增 `model_preference: str | None = None` 字段（dataclass 向后兼容，默认 `None`）
- [x] 1.2 修改 YAML 解析逻辑：`model_preference` 字段缺失时设为 `None`；值非法（不在 `{"haiku","sonnet","opus",None}` 中）时记录 WARNING 并设为 `None`
- [x] 1.3 更新 `tests/test_phase1_agent_registry.py`：验证 model_preference 字段正确解析、缺失时默认 None、非法值降级为 None

## 2. 更新 9 个 Specialist Agent YAML

- [x] 2.1 `agents/data_cleaner.yaml`：新增 `model_preference: haiku`
- [x] 2.2 `agents/literature_searcher.yaml`：新增 `model_preference: haiku`（实现：literature_search.yaml）
- [x] 2.3 `agents/visualizer.yaml`：新增 `model_preference: haiku`（实现：viz_designer.yaml）
- [x] 2.4 `agents/statistician.yaml`：新增 `model_preference: sonnet`
- [x] 2.5 `agents/report_writer.yaml`：新增 `model_preference: sonnet`（实现：writing_assistant.yaml）
- [x] 2.6 `agents/data_analyst.yaml`：新增 `model_preference: sonnet`（实现：literature_reading.yaml）
- [x] 2.7 `agents/hypothesis_tester.yaml`：新增 `model_preference: sonnet`（实现：citation_manager.yaml）
- [x] 2.8 `agents/research_planner.yaml` 和 `agents/peer_reviewer.yaml`：不添加 `model_preference`（继承默认 `null`）

## 3. spawner 模型选择逻辑

- [x] 3.1 修改 `spawner.py:_execute_agent()`：读取 `agent_def.model_preference`，按 purpose 映射表传入子 Agent resolver（`"haiku"→"fast"`，`"sonnet"→"analysis"`，`"opus"→"deep_reasoning"`，`None→"analysis"`）
- [x] 3.2 更新 `tests/test_spawner.py`：验证 `model_preference="haiku"` 时子 Agent runner 使用 `purpose="fast"`，`None` 时使用 `purpose="analysis"`

## 4. 集成验证

- [x] 4.1 运行 `pytest -q tests/test_phase1_agent_registry.py tests/test_spawner.py` 全部通过
- [x] 4.2 运行 `pytest -q` 全量测试通过（重点检查 YAML 解析变更无回归）
- [x] 4.3 （可选）手动测试：派发 `data_cleaner` 子 Agent，确认实际调用模型符合 `model_preference=haiku` 的配置
