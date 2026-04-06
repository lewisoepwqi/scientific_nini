# nini TODO Refactor Plan

## [P0] 建立统一任务模型与生命周期
- File(s): `src/nini/todo/models.py`
- What changes: 新建 `Task`、`TaskStatus`、`TaskEvent`，把通用任务状态统一为 `pending -> assigned -> in_progress -> done | failed | cancelled`，并为 priority/dependencies/deadline 预留字段。
- Inspired by: Phase 1「线程安全的内存任务注册表」, Phase 2「4.1 任务模型分裂成三套状态源」
- Effort: Small
- Breaking change: No

## [P0] 引入会话级任务存储与事件审计日志
- File(s): `src/nini/todo/store.py`
- What changes: 在每个 session 目录下持久化 `todo_tasks.json` 与 `todo_events.jsonl`，提供 CRUD、事件追加、按状态/assignee 过滤查询。
- Inspired by: Phase 1「TODO 采用简单 JSON 文件持久化，并带验证完成提示」, Phase 2「4.2 恢复逻辑依赖消息重放，而且当前实现有字段不匹配缺陷」
- Effort: Medium
- Breaking change: No

## [P0] 建立 Dispatcher + Queue，收口状态转移与 claim/release
- File(s): `src/nini/todo/dispatcher.py`
- What changes: 新增 `TaskQueue` 和 `TaskDispatcher`，集中校验状态迁移、依赖是否满足、Agent 认领/释放/启动/完成/失败/取消。
- Inspired by: Phase 1「团队注册表只做任务归组，不做重调度」, Phase 2「4.4 Agent 编排与任务系统没有统一的 claim / release / owner 语义」
- Effort: Medium
- Breaking change: No

## [P1] 通过 hooks 统一广播任务事件
- File(s): `src/nini/todo/hooks.py`, `src/nini/agent/runner.py`, `src/nini/api/websocket.py`
- What changes: 抽出任务事件 hook 协议，后续让 Runner/WebSocket 订阅，而不是在各处手工拼 `ANALYSIS_PLAN / PLAN_PROGRESS / TASK_ATTEMPT`。
- Inspired by: Phase 1「子代理通过后台线程执行，并用 manifest + lane events 汇报状态」, Phase 2「4.5 Runner / WebSocket 对任务事件做了大量专用编排，边界不清晰」
- Effort: Medium
- Breaking change: No

## [P1] 让 task_state / task_write 改为调用 TodoService
- File(s): `src/nini/todo/index.py`, `src/nini/tools/task_state.py`, `src/nini/tools/task_write.py`
- What changes: 保持外部工具契约不变，但内部改为使用统一 `TodoService`，不再直接操作 `session.task_manager`。
- Inspired by: Phase 2「4.3 工具层抽象耦合，读写接口实际上只是写接口代理」
- Effort: Medium
- Breaking change: No

## [P1] 让多 Agent 派发接入统一任务账本
- File(s): `src/nini/agent/spawner.py`, `src/nini/tools/dispatch_agents.py`, `src/nini/agent/sub_session.py`
- What changes: 在派发前 claim 任务、执行时写 `in_progress`、结束时写 `done/failed/released`，主子会话共享同一 session 任务账本。
- Inspired by: Phase 1「团队注册表只做任务归组，不做重调度」, Phase 2「4.4 Agent 编排与任务系统没有统一的 claim / release / owner 语义」
- Effort: Large
- Breaking change: Yes

## [P2] 收敛 deep_task_state 与 ExecutionPlan 到 Task 投影视图
- File(s): `src/nini/api/websocket.py`, `src/nini/models/execution_plan.py`, `src/nini/agent/session.py`
- What changes: 保留 Recipe 与 Planner 的高层语义，但执行态统一投影到 `Task`；`deep_task_state` 退化为 recipe runtime context，不再承担通用 TODO 账本职责。
- Inspired by: Phase 2「4.1 任务模型分裂成三套状态源」
- Effort: Large
- Breaking change: Yes
