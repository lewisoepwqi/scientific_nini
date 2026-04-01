# 工具 Schema 修复清单

日期：2026-04-01

状态：进行中

## 当前状态

截至 2026-04-01，本轮整改已经完成以下工具的实现与基础回归：

- 已完成：`dataset_transform`
- 已完成：`workspace_session`
- 已完成：`chart_session`
- 已完成：`report_session`
- 已完成：`dataset_catalog`
- 已完成：`code_session`
- 已完成：`task_state`
- 已完成：`stat_test`
- 已完成：`stat_model`

本轮已落地的统一治理：

- 已为多操作/多方法工具补充 `oneOf` 判别分支，`stat_model` 保持扁平 Schema，但增加了 method 级前置校验。
- 已为高频工具补充最小示例与失败恢复提示。
- 已将结构化输入错误统一收口到 `src/nini/tools/base.py` 的 `build_input_error()`。
- 已补充跨工具约束测试，防止后续回退到“宽 Schema + 运行时隐式校验”。

当前验证结果：

- `pytest -q tests/test_foundation_tools.py` 通过，`54 passed`
- `pytest -q tests/test_foundation_regression.py` 通过，`14 passed`
- `pytest -q tests/test_harness_runner.py` 通过，`20 passed`

## 背景

本清单用于修复 LLM 可调用工具中“Schema 暴露信息不足，运行时校验规则隐藏在实现内部”的问题。

本次排查结论如下：

- `src/nini/tools/` 下共识别到 45 个 `Tool` 子类。
- 其中 8 个工具属于多操作入口（multiplexer）模式，且顶层 Schema 仅要求 `operation`。
- 其中 7 个属于默认暴露给模型的高频工具，最容易导致模型反复试错、留下未解决失败动作，并最终被完成校验拦截。

## 核心问题模式

高风险问题主要集中在以下模式：

1. 顶层 `parameters` 只要求 `operation`，但各 `operation` 的必填参数藏在实现里。
2. `description` 只说明“支持哪些功能”，没有说明参数层级、最小示例和失败恢复方式。
3. 工具内部使用表达式语言、上下文注入变量或 DSL，但没有把语法边界写进 Schema 和描述。
4. 工具失败时只返回自然语言报错，没有统一的 `error_code`、`expected_fields`、`recovery_hint`。

## P0

这些工具需要优先修复，直接影响模型在分析链路中的稳定性。

### 1. `dataset_transform`

状态：已完成

文件：`src/nini/tools/dataset_transform.py`

问题：

- 顶层 Schema 只暴露了 `operation` 和 `steps[].op` 枚举。
- `derive_column`、`rename_columns`、`filter_rows` 等步骤的参数结构未在 Schema 中明示。
- `derive_column` 和 `filter_rows` 的表达式实际上受 `pandas.eval/query` 限制，但上下文没有明确写出。
- 容易让模型误用 `df[...]`、`lambda`、三元表达式 `if ... else ...`。

修复项：

- 将顶层 `parameters` 改为按 `operation` 分支的 `oneOf`。
- 将 `run` 分支中的 `steps[].params` 按 `op` 再拆成 `oneOf`。
- 为每个步骤声明明确的必填字段：
  - `derive_column`: `column`, `expr`
  - `filter_rows`: `query`
  - `group_aggregate`: `by`, `metrics`
  - `sort_rows`: `by`
  - `rename_columns`: `mapping`
  - `select_columns`: `columns`
- 在 `description` 中明确写出表达式边界：
  - 使用 `pandas.eval/query` 风格表达式
  - 不支持 `df[...]`
  - 不支持 `lambda`
  - 不支持三元 `if ... else ...`
- 为每个步骤补最小示例。
- 为失败结果补充结构化字段：
  - `error_code`
  - `invalid_step_id`
  - `expected_params`
  - `recovery_hint`
  - `minimal_example`

测试补充：

- `derive_column` 缺 `column`
- `rename_columns` 错把映射写在 `params.mapping` 之外
- `expr` 中出现 `df[...]`
- `expr` 中出现三元表达式

### 2. `workspace_session`

状态：已完成

文件：`src/nini/tools/workspace_session.py`

问题：

- 只有顶层 `operation` 是 Schema 必填。
- `read`、`write`、`append`、`fetch_url` 的必填字段依赖运行时校验。
- 现有 `description` 有示例，但没有把约束正式写进 Schema。

修复项：

- 按 `operation` 拆成 `oneOf`：
  - `list`
  - `read`
  - `write`
  - `append`
  - `edit`
  - `organize`
  - `fetch_url`
- 对各分支声明必填字段：
  - `read`: `file_path`
  - `write`: `file_path`, `content`
  - `append`: `file_path`, `content`
  - `fetch_url`: `url`
- 把当前 `description` 中的最小示例保留并扩展。
- 保留现有 `recovery_hint`，同时补 `minimal_example`。

测试补充：

- 缺 `operation`
- `read` 缺 `file_path`
- `write` 缺 `content`
- `fetch_url` 缺 `url`

### 3. `chart_session`

状态：已完成

文件：`src/nini/tools/chart_session.py`

问题：

- `create/update/get/export` 共用一套顶层 Schema。
- `create/update` 实际需要 `dataset_name` 和 `chart_type`，`get/export` 需要 `chart_id`，但 Schema 未显式表达。

修复项：

- 按 `operation` 分支重写 Schema：
  - `create`: 必填 `dataset_name`, `chart_type`
  - `update`: 必填 `chart_id`
  - `get`: 必填 `chart_id`
  - `export`: 必填 `chart_id`
- 在 `description` 中补最小示例：
  - 创建图表
  - 更新图表
  - 导出图表
- 明确 `render_engine` 合法值及默认行为。
- 为错误结果补 `expected_fields` 和 `recovery_hint`。

测试补充：

- `create` 缺 `dataset_name`
- `update` 缺 `chart_id`
- `export` 缺 `chart_id`

### 4. `report_session`

状态：已完成

文件：`src/nini/tools/report_session.py`

问题：

- `create/patch_section/attach_artifact/get/export` 共用一套宽松 Schema。
- `patch_section`、`attach_artifact`、`export` 的必填字段都藏在实现中。
- `sections`、`methods_entries`、`evidence_blocks` 的对象结构较宽泛。

修复项：

- 按 `operation` 分支重写 Schema：
  - `create`
  - `patch_section`: 必填 `report_id`, `section_key`
  - `attach_artifact`: 必填 `report_id`, `section_key`, `artifact_resource_id`
  - `get`: 必填 `report_id`
  - `export`: 必填 `report_id`
- 收紧 `sections`、`methods_entries`、`evidence_blocks` 的对象字段定义。
- 在 `description` 中补最小示例。
- 为失败结果补 `error_code`、`expected_fields`、`recovery_hint`。

测试补充：

- `patch_section` 缺 `section_key`
- `attach_artifact` 缺 `artifact_resource_id`
- `export` 缺 `report_id`

## P1

这些工具也有契约不够清楚的问题，但严重度低于 P0。

### 5. `dataset_catalog`

状态：已完成

文件：`src/nini/tools/dataset_catalog.py`

问题：

- `load` 和 `profile` 都依赖 `dataset_name`，但顶层 Schema 只要求 `operation`。
- `view` 与 `n_rows` 的关系没有写清。

修复项：

- 按 `operation` 分支重写 Schema：
  - `list`
  - `load`: 必填 `dataset_name`
  - `profile`: 必填 `dataset_name`
- 在 `description` 中补最小示例。
- 在 `profile` 描述中明确：
  - `view=preview/full` 时 `n_rows` 生效
  - 各视图会返回哪些内容

测试补充：

- `load` 缺 `dataset_name`
- `profile` 缺 `dataset_name`

### 6. `code_session`

状态：已完成

文件：`src/nini/tools/code_session.py`

问题：

- `description` 已经比大多数工具清楚，但仍然是多操作共用宽松 Schema。
- `patch_script` 的 `patch` 对象在不同模式下需要不同字段，当前没有用分支 Schema 表达。

修复项：

- 按 `operation` 分支重写 Schema：
  - `create_script`: 必填 `language`, `content`
  - `get_script`: 必填 `script_id`
  - `run_script`: 必填 `script_id`
  - `patch_script`: 必填 `script_id`, `patch`
  - `rerun`: 必填 `script_id`
  - `promote_output`: 明确合法输入组合
- 将 `patch.mode` 再拆分为 `oneOf`：
  - `replace_range`
  - `replace_string`
  - `append`
- 将“传入 `dataset_name` 时注入 `df`”写入参数描述，而不仅是工具说明。
- 错误结果统一补充：
  - `error_code`
  - `expected_fields`
  - `recovery_hint`

测试补充：

- `patch_script` 缺 `patch`
- `replace_string` 缺 `old_string`
- `replace_range` 缺 `start_line` 或 `end_line`

### 7. `task_state`

状态：已完成

文件：`src/nini/tools/task_state.py`

问题：

- `init/update/get/current` 共用一套顶层 Schema。
- `init` 和 `update` 实际都依赖 `tasks`，但 Schema 未分支表达。

修复项：

- 按 `operation` 分支重写 Schema：
  - `init`: 必填 `tasks`
  - `update`: 必填 `tasks`
  - `get`
  - `current`
- 将 `tasks` 的对象结构进一步区分：
  - `init` 建议要求 `id`, `title`, `status`
  - `update` 至少要求 `id`, `status`
- 在 `description` 中补最小示例。

测试补充：

- `init` 空 `tasks`
- `update` 缺 `id`

### 8. `stat_test`

状态：已完成

文件：`src/nini/tools/stat_test.py`

问题：

- 虽然不是 `operation` 分支工具，但本质上是 `method` 路由器。
- `description` 过于简短，没有像 `stat_model` 那样给出最小示例和不同 `method` 的参数要求。

修复项：

- 按 `method` 使用 `oneOf` 约束不同参数组合：
  - `independent_t`
  - `paired_t`
  - `one_sample_t`
  - `mann_whitney`
  - `one_way_anova`
  - `kruskal_wallis`
  - `multiple_comparison_correction`
- 在 `description` 中补每类方法的最小示例。
- 明确说明多数据集场景下必须显式传 `dataset_name`。

测试补充：

- `independent_t` 缺 `value_column`
- `multiple_comparison_correction` 缺 `p_values`

### 9. `stat_model`

状态：已完成，采用“扁平 Schema + method 级前置校验”方案

文件：`src/nini/tools/stat_model.py`

问题：

- 当前已经相对清楚，但仍可进一步把 `method` 条件约束正式写进 Schema。

修复项：

- 用 `oneOf` 按 `method` 约束：
  - `correlation`: 必填 `columns`
  - `linear_regression`: 必填 `dependent_var`, `independent_vars`
  - `multiple_regression`: 必填 `dependent_var`, `independent_vars`
- 在参数说明里明确：
  - `columns`、`independent_vars` 必须是数组
  - 字符串化 JSON 数组会被自动归一化，但不建议依赖该行为

测试补充：

- `correlation` 的 `columns` 不是数组
- 回归缺 `independent_vars`

## P2

这些工具总体可用，但可以纳入统一治理范围。

### 10. `search_tools`

状态：已完成

文件：`src/nini/tools/search_tools.py`

已完成项：

- 在 `description` 中补充 `select:` 与关键词查询的最小示例。
- 顶层 schema 增加 `additionalProperties: false`。
- 为空 `query` 与空 `select:` 查询补充结构化输入错误：
  - `error_code`
  - `expected_fields`
  - `recovery_hint`
  - `minimal_example`
- 返回结果增加 `matched_by` 字段，明确是 `exact_select`、`name` 还是 `description` 命中。

### 11. `dispatch_agents`

状态：已完成

文件：`src/nini/tools/dispatch_agents.py`

已完成项：

- 在 `description` 中强调每个任务都应可独立并行，并补充最小示例。
- 顶层 schema 增加 `additionalProperties: false`。
- 依赖未初始化、无可用 Agent 时返回结构化错误：
  - `error_code`
  - `expected_fields`
  - `recovery_hint`
  - `minimal_example`
- 成功与空任务返回均增加元数据：
  - `task_count`
  - `routed_agents`
- 保留空任务快速返回语义，避免影响既有调用链兼容性。

## 统一治理项

以下改造建议跨工具统一执行。

### A. 为所有 multiplexer 工具统一引入判别联合 Schema

状态：核心目标已完成

统一原则：

- 顶层保留 `operation`
- 使用 `oneOf` 按 `operation` 分支
- 分支内部声明本操作的 `required`
- 避免“Schema 通过，运行时报缺字段”

适用工具：

- `dataset_transform`
- `workspace_session`
- `chart_session`
- `report_session`
- `dataset_catalog`
- `code_session`
- `task_state`

说明：

- 上述工具已完成顶层 `oneOf` 分支约束。
- `stat_model` 不属于 `operation` multiplexer，本轮未强行改为 `oneOf`，以避免影响既有扁平调用路径。

### B. 为所有 LLM-facing 工具统一错误返回结构

状态：核心目标已完成

建议统一字段：

- `success`
- `message`
- `error_code`
- `expected_fields`
- `recovery_hint`
- `minimal_example`

目标：

- 让模型在失败后能直接构造下一次正确调用
- 降低重复试错和“只复述错误，不执行修复”的概率

说明：

- 已修工具均已补齐结构化错误字段。
- 同时已在 `Tool` 基类中抽取 `build_input_error()` 作为统一构造入口。

### C. 为所有 DSL/表达式类工具显式说明语法边界

状态：`dataset_transform` 已完成

必须明确：

- 可用语法
- 不可用语法
- 可用上下文变量
- 最小合法示例

当前优先适用：

- `dataset_transform`
- 未来若新增表达式类筛选/转换工具，也必须遵守同一规范

### D. 为所有默认暴露给模型的工具补最小示例

状态：已完成

建议每个工具至少提供：

- 1 个最小成功示例
- 1 个常见分支示例
- 1 个失败恢复示例

### E. 测试策略统一化

状态：已完成基础护栏

每个高频工具至少补 3 类测试：

- Schema 与实现一致性测试
- 缺字段错误测试
- 错误返回结构测试

补充：

- 已新增跨工具护栏测试，统一检查最小示例、`oneOf`/扁平 Schema 约束，以及结构化错误字段形状。
- 已新增 `search_tools` 与 `dispatch_agents` 的针对性回归测试，锁定查询/调度类工具的说明与错误返回行为。

## 建议实施顺序

1. `dataset_transform`
2. `workspace_session`
3. `chart_session`
4. `report_session`
5. `dataset_catalog`
6. `code_session`
7. `task_state`
8. `stat_test`
9. `stat_model`
10. 统一错误结构和通用测试模板

## Done 标准

以下条件全部满足后，可视为本轮修复完成：

- 所有 P0 工具的 Schema 已改为可判别分支结构
- `description` 中已包含最小示例
- 高风险工具已补 `error_code` 与 `recovery_hint`
- 关键失败路径均有测试覆盖
- 至少完成一次“模型调用工具失败后自动恢复”的端到端验证

当前完成情况：

- 5 项已全部满足。
- `search_tools` 与 `dispatch_agents` 的收尾整改已完成。
