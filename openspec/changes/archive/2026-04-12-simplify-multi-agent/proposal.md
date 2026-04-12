## Why

多 Agent 系统在近十个 PR（#196～#206）中持续修复但问题不断复现：工具暴露 bug、task_state 循环、上下文丢失、dispatch 重试风暴、preflight 预检误报……每次修复都是对症状的局部补丁，根因在于架构层面的过度设计。

当前多 Agent 链路包含五个独立子系统（路由器、DAG 执行引擎、preflight 预检、融合引擎、artifact 引用），总计约 3900 行专用代码，但实际用户从不使用 DAG 依赖格式，路由器只是在 LLM 判断之外重复推理一次，融合引擎让主 Agent 失去对子 Agent 原始输出的判断能力，preflight 只是引入延迟和 mock 负担。

简化目标：移除过度设计层，让多 Agent 回归"并行执行、原始结果、主 Agent 综合"的最小可用形态，同时保留前端可见的子 Agent 事件流。

## What Changes

**删除**
- `agent/router.py`：移除 TaskRouter 双轨路由（规则路由 + LLM 兜底）。主 Agent LLM 直接在 dispatch_agents 参数中声明 `agent_id`，不再有二次路由推理。
- `agent/dag_executor.py`：移除 DAG 拓扑排序执行引擎。用户通过自然语言提出需求，不会写依赖声明；有序执行通过主 Agent 多次调用 dispatch_agents 实现。
- `agent/fusion.py`：移除 ResultFusionEngine 及其四种融合策略（concatenate / summarize / consensus / hierarchical）。子 Agent 原始输出直接拼接返回，主 Agent 自己综合，不再有额外的 LLM fusion 调用。
- `agent/artifact_ref.py`：暂不删除。虽与 DAG/fusion 关联，但 `spawner.py`、`code_runtime.py`、`visualization.py` 中仍有沙箱产物路径的使用，超出本次 change 范围，留待后续清理。

**重写**
- `tools/dispatch_agents.py`（1070 行 → ~150 行）：仅保留参数校验、spawn_batch 调用、结果拼接三个职责。schema 改为 `agents: [{agent_id, task}]`，LLM 直接声明派发目标。

**大幅精简**
- `agent/spawner.py`（1708 行 → ~500 行）：移除 preflight_batch、spawn_with_retry、_spawn_hypothesis_driven、OpenTelemetry 集成、BatchPreflightPlan。核心保留：spawn_batch（并行执行）、_execute_agent（子会话 + runner 循环）、事件中继（agent_start / agent_complete / agent_error）。

**修改**
- `agent/runner.py`：简化 `_handle_dispatch_agents`，去掉路由路径和 DAG 分叉，对齐新 schema。
- `tools/registry.py`：移除对 `fusion` / `router` 的导入引用（随对应文件删除）。
- 各 Agent YAML（`prompts/agents/builtin/*.yaml`）：确认 `allowed_tools` 白名单完整正确，不包含 `dispatch_agents`（防止递归派发）。

**保留不变**
- `agent/lane_queue.py`：技能串行执行队列，与多 Agent 无关。
- 前端 WebSocket 事件协议：agent_start / agent_complete / agent_error 事件格式不变。
- 子 Agent 的 runner 执行逻辑（独立会话、工具调用、事件推送）。

## Non-Goals

- 不重写 runner.py 主循环结构。
- 不修改子 Agent 的 YAML 内容（除确认 allowed_tools 外）。
- 不改变多模型路由（model_resolver）逻辑。
- 不动前端代码。
- 不添加任何新依赖。
- 不改变现有的单 Agent 会话行为。

## Capabilities

### Removed Capabilities
- `multi-agent-routing`：任务路由能力（TaskRouter）随本次改动移除。
- `multi-agent-dag`：DAG 依赖声明与分 wave 执行能力移除。
- `multi-agent-fusion`：结果融合引擎移除。

> 注：`agent/artifact_ref.py` 暂保留（被 spawner/code_runtime/visualization 引用，超出本次范围）。`agent/tool_exposure_policy.py` 无需修改——子 Agent 工具限制已通过 `ToolExposurePolicy.from_agent_def()` 直接读取 YAML `allowed_tools` 实现，现有机制已满足需求。

### Modified Capabilities
- `multi-agent-dispatch`：dispatch_agents 工具从"路由 → DAG → 执行 → 融合"简化为"校验 → 并行执行 → 拼接返回"。

## Impact

- 受影响代码：`src/nini/agent/`（router/dag_executor/fusion/spawner/runner）、`src/nini/tools/`（dispatch_agents.py、registry.py）。`artifact_ref.py` 和 `tool_exposure_policy.py` 本次不改动。
- 需同步更新测试：删除 router/DAG/fusion 相关测试，更新 spawner 测试以对齐新接口，更新 dispatch_agents 集成测试。
- 与路由器、DAG、fusion 相关的测试 mock patch 可以一并删除，降低测试维护负担。
- 回滚策略：所有删除文件在 git 历史可恢复；新 dispatch_agents schema 与旧 schema 不兼容，若需回滚须同时回退 runner.py 的拦截路径。
- 风险：现有的 `tests/test_dispatch_agents*.py`、`tests/test_spawner*.py`、`tests/test_router*.py` 需全部评估并更新，存在测试批量失效的可能，需在执行阶段统一处理。
