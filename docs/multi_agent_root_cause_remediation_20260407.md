# 多 Agent 误派发与失败伪成功问题系统性治理方案

> 文档日期：2026-04-07  
> 关联会话：`58d945e77a5b`  
> 目标：从根源解决多 agent 会话中“错误路由、子任务越权、失败伪装成功、子会话不可审计”四类问题。

## 1. 背景与问题定义

在会话 `58d945e77a5b` 中，多 agent 执行链路暴露出以下系统性问题：

1. 路由失败后退到注册表第一个 agent，实际把数据分析任务错误派发给 `citation_manager`。
2. 子 agent 在收到窄子任务后，仍重新初始化自己的 `task_state/task_write` 任务板，造成重复规划、循环调用和主任务漂移。
3. 子 agent 内部已经出现错误事件或 error 型工具结果，但 `SubAgentResult.success` 仍可能被写成 `True`，导致父级 `dispatch_agents_result` 被统计为成功。
4. `SubSession` 默认纯内存运行，不落盘消息与元信息，导致 `child_session_id` 只能出现在父会话事件里，无法单独审计。

这些问题不是单点 bug，而是由路由策略、会话模型、工具暴露、成功语义四层组合造成的结构性故障。

## 2. 根因分析

### 2.1 路由层根因

源文件：`src/nini/tools/dispatch_agents.py`、`src/nini/agent/router.py`

原始实现中，`dispatch_agents` 在 `_build_task_pairs()` 和 `_route_dag_tasks()` 内部存在“无法路由时退到第一个 agent”的默认值。  
当前内置 agent 的加载顺序来自 `builtin/*.yaml` 的字母序，而第一个正好是 `citation_manager`。  
因此，只要路由没有给出结果，系统就会把未知任务误派发给引用管理专家。

这属于有害默认值，不是合理降级。

### 2.2 子任务边界根因

源文件：`src/nini/agent/spawner.py`、`src/nini/agent/sub_session.py`、`src/nini/agent/prompt_policy.py`

子 agent 使用 `SubSession`，且自带一个新的空 `TaskManager`。  
与此同时，系统提示策略要求多步分析先执行 `task_state(init)`。  
再加上多个 specialist agent 的 `allowed_tools` 显式包含 `task_state`。

结果是：即便父 agent 分配的是窄子任务，子 agent 仍会认为自己需要重新规划完整流程。

### 2.3 执行结果语义根因

源文件：`src/nini/agent/spawner.py`

原始 `_execute_agent()` 的完成判定逻辑近似等于：

- 没有 `stop_event` -> `success=True`
- 有 `stop_event` -> `stopped=True`

这意味着：

- 子 runner 内部出现 `EventType.ERROR`
- 工具返回 `status="error"`
- 模型额度报错被包装进工具错误消息

这些都不一定会影响最终 `SubAgentResult.success`。

于是父层 `dispatch_agents` 会把真实失败序列化成 `success`，再进入融合阶段。

### 2.4 审计链路根因

源文件：`src/nini/agent/sub_session.py`

`SubSession` 的默认设计是纯内存执行，不写 `data/sessions/<child_id>/`。  
这对轻量隔离有利，但代价是：

- 子会话消息历史不可回放
- 子会话 meta 不可追踪
- `child_session_id` 成为“只存在于父日志中的弱引用”

这直接削弱了多 agent 故障排查能力。

## 3. 本次重构原则

本次治理遵循以下原则：

1. 不再允许危险兜底路由。
2. 子 agent 默认是“执行单子任务”，而不是“重跑一遍主流程”。
3. 成功语义必须由真实执行信号决定，而不是由“是否自然返回”决定。
4. 子会话可以继续保持资源隔离，但必须具备审计落盘能力。
5. 对历史单 agent/单 specialist 场景保留最小兼容路径，避免无谓破坏。

## 4. 已落地改造

### 4.1 移除多 agent 场景下的危险默认兜底

变更文件：`src/nini/tools/dispatch_agents.py`

已实施：

1. `_build_task_pairs()` 不再在多 agent 场景下默认退到第一个 agent。
2. `_route_dag_tasks()` 同样移除默认“第一个 agent”兜底。
3. 当任务无法匹配兼容 specialist 时，系统会生成显式的 `routing_failed` 子结果。
4. 仅在“注册表中只有唯一一个 agent”时保留兼容性退路，避免破坏极简场景与旧测试。

效果：

- 未匹配任务不再被错误派发到 `citation_manager`
- 父级能看到结构化失败，而不是假成功
- DAG 路径在路由失败时也会明确终止

### 4.2 增加 agent 兼容性过滤器

变更文件：`src/nini/agent/router.py`

已实施：

1. 新增 `_AGENT_COMPATIBILITY_HINTS`。
2. 对 `citation_manager`、`literature_search`、`literature_reading`、`review_assistant` 增加硬兼容性过滤。
3. 即便 LLM 路由输出了这些 agent，只要任务文本不包含最低兼容信号，就会被剔除。

效果：

- `citation_manager` 不再能处理“检查数据结构是否完整”这类明显不属于引用管理的任务
- LLM 路由被加上了最小安全边界

### 4.3 固化子 agent 的单任务执行边界

变更文件：`src/nini/agent/spawner.py`

已实施：

1. `SubAgentSpawner._build_subagent_task()` 为子任务注入显式执行约束。
2. 普通 specialist 子 agent 默认移除 `task_state/task_write` 暴露。
3. 只有未来明确声明 `allow_subtask_planning=True` 的 agent 才允许重新规划。

效果：

- 子 agent 会被明确告知“这是单个窄子任务”
- specialist 不再默认重建自己的 PDCA 任务板
- 可以从根上压制 `task_state(init)` 死循环

### 4.4 将子 agent 成功语义改为“基于失败信号”

变更文件：`src/nini/agent/spawner.py`

已实施：

1. 从 runner 事件流中提取 `EventType.ERROR` 和 error 型 `TOOL_RESULT`。
2. 从子会话消息中补采集 `status="error"` 的工具结果，作为兜底信号。
3. 只要存在失败信号，最终 `SubAgentResult.success=False`，`stop_reason="child_execution_failed"`。
4. `_finalize_result()` 为真正成功的子结果补齐 `stop_reason="completed"`。

效果：

- quota error、工具错误、执行失败不会再被父层当作成功
- `dispatch_agents` 的失败计数和结构化日志终于可信

### 4.5 让 spawned 子会话默认进入审计落盘模式

变更文件：`src/nini/agent/sub_session.py`、`src/nini/agent/session.py`、`src/nini/agent/spawner.py`

已实施：

1. `SubSession` 新增双模式：
   - `persist_runtime_state=False`：旧的纯内存模式
   - `persist_runtime_state=True`：新的审计模式
2. `SubAgentSpawner` 创建的真实子会话默认使用 `persist_runtime_state=True`
3. `SessionManager.save_subsession_metadata()` 持久化：
   - `is_subsession`
   - `parent_session_id`
   - `resource_owner_session_id`
4. 子 agent 原始事件会追加写入自己的 `agent_runs.jsonl`

效果：

- `child_session_id` 现在对应真实磁盘目录
- 子会话有自己的消息、meta 和运行事件
- 多 agent 故障排查不再只能依赖父会话残片

### 4.6 修复失败归档路径中的阻塞隐患

变更文件：`src/nini/agent/spawner.py`

已实施：

1. 将 `_archive_sandbox()` 中的 `asyncio.to_thread(shutil.move, ...)` 改为直接同步 `shutil.move(...)`

原因：

- 在当前测试与运行环境下，这条线程切换路径存在卡住现象
- 沙箱归档不是高频热点，直接同步移动更简单稳定

### 4.7 增加模型额度预检

变更文件：`src/nini/agent/model_resolver.py`、`src/nini/agent/spawner.py`、`src/nini/tools/dispatch_agents.py`、`src/nini/api/session_routes.py`

已实施：

1. 在 `ModelResolver` 中新增 `preflight(purpose=...)`。
2. 预检与 `chat()` 共用同一条候选客户端解析逻辑，避免预检与真实发送决策漂移。
3. `SubAgentSpawner` 在真正启动子 Agent 前执行模型预检。
4. 若预检失败，直接返回 `stop_reason="preflight_failed"` 的结构化失败结果，不创建子执行循环。
5. `spawn_with_retry()` 将 `preflight_failed` 视为永久失败，不再做指数退避重试。
6. `spawn_batch()` 会先完成整批预检，已知不可执行的子任务直接生成失败结果，仅让通过预检的任务进入并发执行。
7. `dispatch_agents` 在真正执行前会独立生成 dispatch 级预检摘要，并写入 `dispatch_agents_preflight` 运行事件。
8. 会话运行摘要接口会把 dispatch 预检阶段收敛到同一条 dispatch 线程上，显式暴露预检失败计数与可执行任务数。

效果：

- 配额不足会在 spawn 前被拦截
- 不会再出现“子 agent 启动后立刻因额度不足失败”的噪声事件流
- `dispatch_agents` 会直接收到可解释、可统计的 quota 失败结果
- 批量调度不会再对同一子任务重复执行“预检一次、spawn 前再预检一次”
- `agent-runs` 摘要和 `dispatch_agents_result` 事件之间，终于补上了独立的 preflight 阶段

## 5. 行为变化说明

### 5.1 旧行为

- 未匹配任务 -> 随机退到第一个内置 agent
- 子 agent 内部失败 -> 可能仍返回 success
- 子会话 -> 默认无磁盘记录
- specialist 子 agent -> 可以继续使用 `task_state/task_write`

### 5.2 新行为

- 未匹配任务 -> `routing_guard/routing_failed`
- 子 runner 中出现错误信号 -> 子结果显式失败
- spawned 子会话 -> 默认审计落盘
- specialist 子 agent -> 默认禁止再做任务规划

## 6. 测试与验证

本次新增/更新的验证重点包括：

1. `tests/test_router.py`
   - 验证 LLM 误派发到 `citation_manager` 时会被过滤
2. `tests/test_dispatch_agents.py`
   - 验证多 agent 未匹配场景不再退到第一个 agent
   - 验证部分未匹配任务会变成 `routing_failed`
3. `tests/test_spawner.py`
   - 验证 error 型 `TOOL_RESULT` 会把子结果标为失败
   - 验证 spawned 子会话会落盘审计元信息
   - 验证普通 specialist 会剥离 `task_state/task_write`
4. `tests/test_sub_session.py`
   - 验证 `persist_runtime_state=True` 时子会话会写审计 meta

本轮验证命令：

```bash
pytest -q tests/test_router.py tests/test_dispatch_agents.py tests/test_spawner.py tests/test_sub_session.py
python3 -m black --check src/nini/agent/router.py src/nini/agent/sub_session.py src/nini/agent/session.py src/nini/agent/spawner.py src/nini/tools/dispatch_agents.py tests/test_router.py tests/test_dispatch_agents.py tests/test_spawner.py tests/test_sub_session.py
```

当前结果：

- 后端验证：`134 passed`
- 前端验证：`36 passed`
- `cd web && npm run build` 通过

本轮补充验证：

- `pytest -q tests/test_phase4_session_persistence.py` -> `30 passed`
- `cd web && npm test -- --run src/store/event-handler.test.ts src/components/ChatPanel.test.tsx src/components/AgentRunTabsPanel.test.tsx src/components/WorkflowTopology.test.tsx` -> `42 passed`
- `cd web && npm run build` 通过

后续补充验证：

- `pytest -q tests/test_phase4_session_persistence.py` -> `31 passed`
- `cd web && npm test -- --run src/store/store.test.ts src/store/event-handler.test.ts src/components/ChatPanel.test.tsx src/components/DispatchLedgerOverviewPanel.test.tsx` -> `53 passed`
- `cd web && npm run build` 通过

## 7. 尚未完全解决但已明确收敛的问题

以下问题本次没有全部落地，但已经从“隐性结构债”收敛为明确后续项：

### 7.1 dispatch 独立预检阶段已落地，UI 已接入最小可见闭环

当前预检已经进入 `SubAgentSpawner.spawn()`、`spawn_batch()`，而 `dispatch_agents` 也已经在真正执行前产出独立的 preflight 阶段，并显式汇总：

1. `preflight_failure_count`
2. `preflight_failures`
3. `routing_failure_count`
4. `execution_failure_count`

也就是说，父级工具返回、`dispatch_agents_preflight` 事件、`dispatch_agents_result` 事件以及 `/sessions/{id}/agent-runs` 摘要里，都已经能直接区分“额度/配置失败”和“实际执行失败”。

前端当前已完成两层消费：

1. `AgentRunTabsPanel` 会展示 dispatch 线程的预检摘要，例如“可执行 2 · 预检失败 1”
2. `WorkflowTopology` 会在任务派发阶段直接显示“任务派发预检”卡片，即使此时还没有任何子 agent 真正启动

此外，后台会话收到 `workflow_status(scope=dispatch_agents)` 时，也会把 dispatch 线程写入 `session-ui-cache`，不再只对当前激活会话有效。

本轮又向前推进了一层：

1. `/sessions/{id}/agent-runs` 摘要已携带 `preflight_failures` 明细，而不只是失败计数
2. `ChatPanel` 选中 dispatch 线程时，会显示“派发账本”卡片
3. “派发账本”里会直接展示预检失败明细，包括 `agent_id`、任务文本和失败原因
4. 这些明细既支持当前会话实时更新，也支持会话恢复后从摘要直接恢复显示

进一步地，dispatch 账本已经不再只覆盖预检失败：

1. `dispatch_agents_result` 现在会同时产出 `routing_failures` 与 `execution_failures`
2. `/sessions/{id}/agent-runs` 摘要会恢复这三类失败明细，而不只是恢复失败计数
3. `ChatPanel` 的“派发账本”会分别展示“预检失败明细 / 路由失败明细 / 执行失败明细”
4. `dispatch_agents_result.subtasks` 现已被归一化为统一 `dispatch_ledger`，成功子任务与已停止子任务也会进入同一张账本

本轮又补上了“独立查询模型 + 工作区总览”：

1. 后端新增 `/sessions/{id}/dispatch-ledger` 独立查询接口
2. 前端 `switchSession()` 会单独恢复 `dispatchLedgers`，不再只能依赖聊天线程选中态
3. 工作区 `任务` tab 新增“调度账本”总览面板，可直接跳转到对应 dispatch 线程
4. 当前会话运行中收到 `workflow_status(scope=dispatch_agents)` 时，总览与线程详情会同步更新

本轮继续把账本提升到了“跨会话聚合审计”层：

1. 后端新增 `/sessions/dispatch-ledger/aggregate` 聚合接口，直接返回跨会话的 dispatch 统计结果
2. 聚合结果会输出：
   - `dispatch_session_count`
   - `dispatch_run_count`
   - `subtask_count`
   - `success_count`
   - `stopped_count`
   - `preflight_failure_count`
   - `routing_failure_count`
   - `execution_failure_count`
   - `failure_count`
3. 聚合接口同时返回最近有 dispatch 记录的会话摘要，包括：
   - `session_id`
   - `title`
   - `latest_run_id`
   - `last_dispatch_at`
   - 会话级失败计数
4. 前端 `fetchSessions()` 现在会同步拉取这份聚合摘要
5. 工作区“调度账本”面板顶部已接入跨会话审计区，可直接展示高风险会话并跳转到对应会话 / dispatch 线程

当前剩余缺口变为：

1. 跨会话聚合目前仍以“最近会话列表 + 汇总计数”为主，还没有 stop_reason/agent 维度的排行
2. 全局聚合目前依赖查询接口刷新，尚未在 `workflow_status(fused)` 后做节流式实时刷新
3. 调度前的显式交互拦截还未做，仍是服务器返回预检结果后再展示

### 7.2 specialist 能力画像仍偏弱

当前 agent 兼容性过滤器是最小硬约束，不是完整能力图谱。  
长期建议将 `AgentDefinition` 扩展为：

- `capability_tags`
- `routing_keywords`
- `forbidden_keywords`
- `allow_subtask_planning`
- `preferred_stage`

然后由 `TaskRouter` 基于结构化画像路由，而不是依赖少量关键词和自由文本。

### 7.3 父任务板与子任务账本尚未完全统一

本次已经阻止子 agent 自建任务板，但父任务板与子任务执行账本仍是两套数据结构。  
长期建议引入统一的 dispatch ledger：

- 父任务 ID
- 子任务 ID
- agent_id
- run_id
- route_status
- execution_status
- stop_reason
- artifact refs

这样前端、审计和恢复都能基于同一套真相模型。

## 8. 回滚策略

若需要回滚本轮改造，建议按以下顺序局部撤回：

1. 仅关闭 spawned 子会话的 `persist_runtime_state=True`
2. 保留失败语义修复
3. 保留 `routing_failed` 显式结果
4. 保留 `citation_manager` 兼容性过滤

不建议回滚的部分：

- 多 agent 默认退到第一个内置 agent
- 子 agent 失败仍记为成功

这两项属于明确的系统错误行为，不应恢复。

## 9. 结论

这次治理的核心不是“修一个会话”，而是把多 agent 的四条关键边界重新立住：

1. 路由边界：未匹配就失败，不再危险兜底
2. 任务边界：子 agent 执行子任务，而不是重跑主流程
3. 状态边界：失败信号必须进入 `SubAgentResult`
4. 审计边界：子会话必须可追踪、可复盘

本轮改造完成后，多 agent 系统从“可运行但不可审计、不可置信”的状态，提升到了“可审计、可定位、可回归”的状态。后续再继续做 dispatch 层预检和统一任务账本，系统就可以进入更稳态的多 agent 编排阶段。
