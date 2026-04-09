## 1. 删除死代码与对应测试（Phase 1）

- [x] 1.1 删除 `src/nini/agent/router.py`（TaskRouter 及双轨路由实现）
- [x] 1.2 删除 `src/nini/agent/dag_executor.py`（DagExecutor 拓扑排序引擎）
- [x] 1.3 删除 `src/nini/agent/fusion.py`（ResultFusionEngine 及四种融合策略）
- [x] 1.4 保留 `src/nini/agent/artifact_ref.py`（spawner/code_runtime/visualization 仍在使用，超出本次范围）
- [x] 1.5 删除 `tests/test_router.py`（TaskRouter 单元测试，共 283 行）
- [x] 1.6 删除 `tests/test_dag_engine.py`（DAG 引擎测试，共 228 行）
- [x] 1.7 删除 `tests/test_dag_executor.py`（DagExecutor 单元测试，共 291 行）
- [x] 1.8 删除 `tests/test_fusion.py`（ResultFusionEngine 单元测试，共 275 行）
- [x] 1.9 删除 `tests/test_spawner_hypothesis.py`（假说驱动模式测试，共 244 行）
- [x] 1.10 移除 `src/nini/agent/__init__.py` 中所有对已删除模块的导出（如有）
- [x] 1.11 移除 `src/nini/tools/registry.py` 中对 `fusion` / `router` 的导入引用（第 345-346 行）
- [x] 1.12 移除 `src/nini/tools/dispatch_agents.py` 顶部对 `dag_executor` 的导入（`DagExecutor, DagTask`），将 `has_dependencies` 分叉路径临时降级为空实现或直接走旧并行路径（避免 import 报错，完整重写在 Phase 2 进行）
- [x] 1.13 运行 `pytest -q` 确认全部现有测试通过

## 2. 重写 dispatch_agents 工具（Phase 2）

- [x] 2.1 重写 `src/nini/tools/dispatch_agents.py`：移除路由路径、DAG 路径、融合路径，仅保留参数校验 + `spawn_batch` 调用 + 结果拼接（目标约 150 行）
- [x] 2.2 新 `execute()` 参数签名改为 `agents: list[dict]`，每项包含 `agent_id: str` 和 `task: str`
- [x] 2.3 实现 agent_id 合法性校验：对照 AgentRegistry，非法 agent_id 返回 `ToolResult(success=False, message=...)` 并列出可用列表
- [x] 2.4 实现结果拼接：格式为 `[{agent_id}] {task}\n{summary}` 多段拼接，失败子 Agent 以 `[{agent_id}] 执行失败: {error}` 格式包含
- [x] 2.5 更新 `parameters` 属性，schema 改为 `{"agents": [{"agent_id": ..., "task": ...}]}`，移除 `tasks` / `depends_on` / `id` 字段
- [x] 2.6 更新 `description` 属性：说明直接声明 agent_id、给出最小示例
- [x] 2.7 在 `spawn_batch` 调用前保留 `_build_dispatch_run_id` 与 dispatch 事件推送（agent_start / agent_complete 前端事件）
- [x] 2.8 重写 `tests/test_dispatch_agents.py`：覆盖新 schema 的正常执行、空列表、非法 agent_id、部分失败四种场景
- [x] 2.9 运行 `pytest -q tests/test_dispatch_agents.py` 确认通过

## 3. 精简 SubAgentSpawner（Phase 3）

- [x] 3.1 删除 `SubAgentSpawner._preflight_agent_execution` 方法（约 60 行）
- [x] 3.2 删除 `SubAgentSpawner.preflight_batch` 方法（约 40 行）
- [x] 3.3 删除 `SubAgentSpawner._emit_preflight_failure_event` 方法（约 35 行）
- [x] 3.4 删除 `BatchPreflightPlan` 数据类及对 `skip_preflight` 参数的所有引用
- [x] 3.5 删除 `SubAgentSpawner.spawn_with_retry` 方法（约 85 行）
- [x] 3.6 删除 `SubAgentSpawner._spawn_hypothesis_driven` 方法（约 215 行）
- [x] 3.7 保留 `_FixedPurposeResolver` 类及 `_MODEL_PREFERENCE_TO_PURPOSE` 映射表（各子 Agent YAML 的 `model_preference: haiku/sonnet` 依赖此机制控制成本，不可删除）
- [x] 3.8 删除 OpenTelemetry 集成代码（`_start_span`、`_tracer`、`_OTEL_AVAILABLE` 及所有 span 调用，约 30 行）
- [x] 3.9 在 `spawn_batch` 中新增 `asyncio.Semaphore` 并发控制（当前为裸 `asyncio.gather`，无上限），默认上限 4，可通过 `settings.max_sub_agent_concurrency` 配置
- [x] 3.10 确认保留：`spawn_batch`、`_execute_agent`、`_make_subagent_event_callback`、`_relay_child_event`、`_finalize_result`、`_attach_snapshot`、`_build_run_metadata`、`_emit_progress`、`_push_event`
- [x] 3.11 更新 `SubAgentResult` 数据类：移除 `stop_reason="preflight_failed"` 相关逻辑（保留 `success`、`summary`、`error`、`agent_id`、`task`、`artifacts`、`documents`）
- [x] 3.12 更新 `tests/test_spawner.py`：删除 preflight / hypothesis 相关测试（约 10 个函数），补充并发上限（semaphore）行为测试
- [x] 3.13 运行 `pytest -q tests/test_spawner.py` 确认通过

## 4. 简化 runner.py 中的 dispatch 拦截路径（Phase 3 同步）

- [x] 4.1 更新 `runner.py` 的 `_handle_dispatch_agents`：解析 `agents` 参数（`list[dict]`）替代旧的 `tasks` 参数
- [x] 4.2 移除 `_handle_dispatch_agents` 中对 `task_router`、`dag_executor`、`fusion_engine` 的任何残留引用
- [x] 4.3 确认 `ORCHESTRATOR_TOOL_NAMES` 仍包含 `"dispatch_agents"` 且拦截逻辑不变
- [x] 4.4 运行 `pytest -q` 确认全量测试通过

## 5. 更新 system prompt，注入可用 agent_id 列表（Phase 4）

- [x] 5.1 在 `src/nini/agent/prompts/builder.py` 的主 Agent system prompt 适当位置，注入可用 agent_id 简表（agent_id + 一行中文描述，9 个 agent）
- [x] 5.2 在 `dispatch_agents` 工具描述或 system prompt 中给出最小调用示例（至少一个）
- [x] 5.3 确认各子 Agent YAML（`prompts/agents/builtin/*.yaml`）的 `allowed_tools` 列表中均不包含 `dispatch_agents`（防递归）

## 6. 更新集成测试与配置（Phase 4）

- [x] 6.1 更新 `tests/test_multi_agent_foundation_integration.py`：对齐新 schema（`agents` 参数格式），移除路由相关断言
- [x] 6.2 检查 `tests/test_orchestrator_mode.py`（如存在）中对 `preflight_batch` 的 mock patch，按需更新或删除
- [x] 6.3 检查 `src/nini/config.py`：如需添加 `max_sub_agent_concurrency` 配置项，默认值为 4
- [x] 6.4 运行 `python scripts/check_event_schema_consistency.py` 确认事件 schema 一致性（dispatch 事件格式不变）
- [x] 6.5 运行 `pytest -q` 确认全量测试通过（2099 passed, 0 failed）
- [x] 6.6 运行 `cd web && npm run build` 确认前端构建无报错（前端事件协议不变，预期无影响）
