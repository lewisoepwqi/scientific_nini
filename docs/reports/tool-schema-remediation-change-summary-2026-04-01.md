# 工具契约整改变更摘要

日期：2026-04-01

## 范围

本次变更聚焦默认暴露给模型、且最容易出现“Schema 过宽、运行时报缺参”的基础工具。

涉及工具：

- `dataset_transform`
- `workspace_session`
- `dataset_catalog`
- `chart_session`
- `report_session`
- `code_session`
- `task_state`
- `stat_test`
- `stat_model`
- `search_tools`
- `dispatch_agents`

## 主要改动

### 1. 显式化工具契约

- 为多操作工具补充顶层 `oneOf` 判别分支。
- 为步骤级或模式级参数补充 `oneOf` 分支：
  - `dataset_transform.steps[].op`
  - `code_session.patch.mode`
- 为统计类工具补充 method 级前置校验：
  - `stat_test`
  - `stat_model`

### 2. 补充最小示例

- 为高频 LLM-facing 工具补充最小成功示例。
- 为易错分支补充参数约束说明和恢复提示。
- 为 DSL/表达式类工具补充语法边界说明，重点覆盖 `dataset_transform`。

### 3. 统一结构化错误

- 为高频工具补充统一字段：
  - `error_code`
  - `expected_fields` 或 `expected_params`
  - `recovery_hint`
  - `minimal_example`
- 在 `src/nini/tools/base.py` 中新增 `build_input_error()`，统一构造结构化输入错误。

### 4. 补充护栏测试

- 为各工具补充 Schema 一致性测试。
- 为缺字段错误补充结构化返回测试。
- 新增跨工具护栏测试，避免未来回退到“宽 Schema + 隐式校验”。
- 为 `search_tools` 与 `dispatch_agents` 补充针对性回归测试，锁定查询/调度类工具的关键行为。

### 5. 收尾低优先级工具

- 为 `search_tools` 补充 `select:` 最小示例、结构化输入错误，以及结果级 `matched_by` 字段。
- 为 `dispatch_agents` 补充独立并行任务说明、结构化失败返回，以及 `task_count`、`routed_agents` 元数据。
- 保留 `dispatch_agents` 空任务快速返回语义，避免影响既有调用链兼容性。

## 验证结果

已执行：

- `pytest -q tests/test_search_tools.py`
- `pytest -q tests/test_dispatch_agents.py`
- `pytest -q tests/test_foundation_tools.py`
- `pytest -q tests/test_foundation_regression.py`
- `pytest -q tests/test_harness_runner.py`
- `python3 -m compileall src/nini/tools/base.py src/nini/tools/dataset_catalog.py src/nini/tools/chart_session.py src/nini/tools/report_session.py src/nini/tools/code_session.py src/nini/tools/task_state.py src/nini/tools/stat_test.py src/nini/tools/stat_model.py src/nini/tools/workspace_session.py src/nini/tools/dataset_transform.py src/nini/tools/search_tools.py src/nini/tools/dispatch_agents.py`

结果：

- `tests/test_foundation_tools.py`: `54 passed`
- `tests/test_foundation_regression.py`: `14 passed`
- `tests/test_harness_runner.py`: `20 passed`

## 剩余工作

本轮工具契约整改已完成。

如需继续扩展，建议下一阶段将本轮规范整理成单独开发文档或 PR 模板检查项，并对未来新增工具默认启用同样的契约与错误返回要求。
