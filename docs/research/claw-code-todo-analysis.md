# claw-code TODO / Task Management Analysis

## Phase 1 Findings

### [C1] 线程安全的内存任务注册表
- Pattern: `TaskRegistry` 用 `Arc<Mutex<...>> + HashMap` 维护任务全集，任务对象同时保存提示词、结构化任务包、消息流、输出与团队归属；状态枚举只有 `created/running/completed/failed/stopped`，未内建优先级或依赖。
- Location: `rust/crates/runtime/src/task_registry.rs`
- Evidence:
```rust
pub struct Task {
    pub task_id: String,
    pub prompt: String,
    pub description: Option<String>,
    pub task_packet: Option<TaskPacket>,
    pub status: TaskStatus,
    pub messages: Vec<TaskMessage>,
    pub output: String,
    pub team_id: Option<String>,
}
```
- Why it's good: 模型很薄，但把执行期真正需要追踪的字段集中到了一个记录里，查询和调度都只依赖一个中心对象。它没有过早引入优先级/依赖这类调度特性，因此当前实现简单、可预测。

### [C2] 结构化任务包先校验再入库
- Pattern: `TaskPacket` 把任务目标、作用域、仓库策略、验收测试、提交策略、汇报契约、升级策略做成强类型输入，`create_from_packet()` 先校验再创建任务。
- Location: `rust/crates/runtime/src/task_packet.rs`, `rust/crates/runtime/src/task_registry.rs`
- Evidence:
```rust
pub struct TaskPacket {
    pub objective: String,
    pub scope: String,
    pub repo: String,
    pub branch_policy: String,
    pub acceptance_tests: Vec<String>,
    pub commit_policy: String,
    pub reporting_contract: String,
    pub escalation_policy: String,
}
```
- Why it's good: 这相当于把“任务单”显式化，减少了代理收到模糊 prompt 后各自理解不一致的问题。校验逻辑也让运行时更早失败，错误面更清晰。

### [C3] 任务生命周期通过工具层直接映射到注册表
- Pattern: `TaskCreate/TaskGet/TaskList/TaskStop/TaskUpdate/TaskOutput` 都只是薄薄一层，把工具调用直接路由到全局 `TaskRegistry`；支持创建、读取、列出、追加消息、停止、读取输出。
- Location: `rust/crates/tools/src/lib.rs`
- Evidence:
```rust
fn run_task_create(input: TaskCreateInput) -> Result<String, String> {
    let registry = global_task_registry();
    let task = registry.create(&input.prompt, input.description.as_deref());
    to_pretty_json(json!({
        "task_id": task.task_id,
        "status": task.status,
        "prompt": task.prompt
    }))
}
```
- Why it's good: 工具层没有再发明第二套状态机，避免了 API 视图和运行时真相分裂。调用路径短，调试时也容易从工具入口直接追到状态变更点。

### [C4] 团队注册表只做任务归组，不做重调度
- Pattern: `TeamRegistry` 保存 `team_id/name/task_ids/status`，`TeamCreate` 收到一组任务后只做归组，并把 `team_id` 回填到对应任务；没有任务队列、依赖图或 worker pool。
- Location: `rust/crates/runtime/src/team_cron_registry.rs`, `rust/crates/tools/src/lib.rs`
- Evidence:
```rust
let task_ids: Vec<String> = input.tasks.iter()
    .filter_map(|t| t.get("task_id").and_then(|v| v.as_str()).map(str::to_owned))
    .collect();
let team = global_team_registry().create(&input.name, task_ids);
for task_id in &team.task_ids {
    let _ = global_task_registry().assign_team(task_id, &team.team_id);
}
```
- Why it's good: 它把“分组”与“执行”解耦了，团队对象只承担归属关系，不承担复杂调度职责。这个边界很清楚，后面如果要替换成真正 dispatcher，迁移成本较低。

### [C5] 子代理通过后台线程执行，并用 manifest + lane events 汇报状态
- Pattern: `Agent` 工具为每个子代理生成输出文件和 manifest 文件，随后以命名线程后台运行；完成或失败时统一写回 `status/current_blocker/derived_state/lane_events`。
- Location: `rust/crates/tools/src/lib.rs`, `rust/crates/runtime/src/lane_events.rs`
- Evidence:
```rust
let manifest = AgentOutput {
    status: String::from("running"),
    lane_events: vec![LaneEvent::started(iso8601_now())],
    current_blocker: None,
    derived_state: String::from("working"),
    error: None,
    ...
};
```
- Why it's good: 代理执行和状态可视化分离得很干净，主流程不必阻塞等待子代理结束。`lane_events` 既能表达成功，也能表达阻塞与失败，适合后续接 UI 或通知系统。

### [C6] TODO 采用简单 JSON 文件持久化，并带验证完成提示
- Pattern: `TodoWrite` 把 `content/activeForm/status` 数组写入 `.clawd-todos.json`（或环境变量指定路径）；若全部完成则清空持久化文件，并在缺少验证项时给出 `verification_nudge_needed`。
- Location: `rust/crates/tools/src/lib.rs`, `rust/.clawd-todos.json`
- Evidence:
```rust
let store_path = todo_store_path()?;
let all_done = input.todos.iter()
    .all(|todo| matches!(todo.status, TodoStatus::Completed));
let persisted = if all_done { Vec::new() } else { input.todos.clone() };
std::fs::write(&store_path, serde_json::to_string_pretty(&persisted)?)
    .map_err(|error| error.to_string())?;
```
- Why it's good: 这套 TODO 持久化故意保持极简，跨会话恢复成本低，也方便 CLI 和 TUI 直接消费。额外的“验证提醒”把流程约束嵌进工具里，是很便宜但有效的行为引导。

## nini Current State

### [N1] TODO 主状态挂在 `Session.task_manager`，不是独立存储
- Pattern: `nini` 的任务清单直接保存在 `Session.task_manager` 中；没有单独的任务表、任务仓库或跨会话共享 store。
- Location: `src/nini/agent/session.py`, `src/nini/agent/task_manager.py`
- Evidence:
```python
@dataclass
class Session:
    ...
    task_manager: TaskManager = field(init=False, repr=False)

def __post_init__(self) -> None:
    ...
    self.task_manager = TaskManager()
```
- Why it matters: 状态访问很直接，但任务模型与会话生命周期硬绑定，天然更偏“单会话计划板”而不是可复用的任务子系统。

### [N2] 任务模型支持依赖字段，但状态机仍是本地 dataclass
- Pattern: `TaskItem` 提供 `id/title/status/tool_hint/action_id/depends_on`，状态集为 `pending/in_progress/completed/failed/skipped`；依赖关系只存在于内存对象中。
- Location: `src/nini/agent/task_manager.py`
- Evidence:
```python
TaskStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]

@dataclass(frozen=True)
class TaskItem:
    id: int
    title: str
    status: TaskStatus = "pending"
    tool_hint: str | None = None
    action_id: str | None = None
    depends_on: list[int] = field(default_factory=list)
```
- Why it matters: 这比 `claw-code` 的基础任务记录更接近工作流建模，但当前没有配套 dispatcher 去真正消费这些依赖。

### [N3] 暴露面是 `task_write/task_state`，并非完整 CRUD
- Pattern: 当前工具接口只有 `init/update/get/current`，写操作由 `task_state` 代理到 `task_write`；没有 delete、cancel、claim、release、assign 之类操作。
- Location: `src/nini/tools/task_state.py`, `src/nini/tools/task_write.py`
- Evidence:
```python
"enum": ["init", "update", "get", "current"]

if operation in {"init", "update"}:
    return await self._delegate.execute(session, mode=operation, tasks=tasks)
if operation == "get":
    ...
if operation == "current":
    ...
```
- Why it matters: 这更像“让 LLM 驱动当前计划”的交互工具，不是面向编排器、Agent worker 和恢复流程的通用任务 API。

### [N4] 初始化与调度耦合，更新还会自动完成前序任务
- Pattern: `task_write(init)` 会隐式把第一个任务推进到 `in_progress`；`update_tasks()` 发现新任务进入 `in_progress` 时，会把之前的进行中任务自动改成 `completed`。
- Location: `src/nini/tools/task_write.py`, `src/nini/agent/task_manager.py`
- Evidence:
```python
if first_task:
    auto_start = new_manager.update_tasks([{"id": first_task.id, "status": "in_progress"}])
    new_manager = auto_start.manager
...
elif task.status == "in_progress" and new_in_progress_ids:
    new_tasks.append(TaskItem(id=task.id, title=task.title, status="completed", ...))
```
- Why it matters: 创建、推进、完成三种职责揉在了一起，虽然能减少 LLM 调用次数，但会让后续引入“任务认领 / 失败回退 / 重试”时难以拆分。

### [N5] 持久化不是专门的任务存储，而是消息回放恢复
- Pattern: 会话恢复时先加载持久化消息，再通过 `_reconstruct_task_manager_from_messages()` 回放历史中的 `task_write/task_state` 调用重建任务状态；`task_manager` 自身并不直接落盘。
- Location: `src/nini/agent/session.py`
- Evidence:
```python
if self.load_persisted_messages and not self.messages:
    self.messages.extend(self.conversation_memory.load_messages(resolve_refs=True))
if self.messages:
    self._reconstruct_task_manager_from_messages()
```
- Why it matters: 这条恢复链路依赖消息历史完整、参数名一致且不被压缩/污染，容错面比显式任务存储更脆弱。

### [N6] 恢复逻辑与真实工具参数已经出现漂移
- Pattern: `task_state` 的真实更新参数名是 `tasks`，但恢复逻辑读取的是 `updates`，这意味着部分历史更新可能根本无法正确回放。
- Location: `src/nini/agent/session.py`, `src/nini/tools/task_state.py`
- Evidence:
```python
elif operation == "update":
    updates = args.get("updates", [])
    if updates and rebuilt.initialized:
        result = rebuilt.update_tasks(updates)
```
- Why it matters: 这不是理论风险，而是实际的一致性缺陷，说明“消息即状态”的方案已经开始漂移。

### [N7] Agent 与 TODO 的交互被硬编码在主 runner 中
- Pattern: `runner.py` 对 `task_write/task_state` 做特殊分支处理，成功后立刻把 `task_manager` 转成 `ANALYSIS_PLAN/PLAN_STEP_UPDATE/PLAN_PROGRESS` WebSocket 事件。
- Location: `src/nini/agent/runner.py`, `src/nini/models/event_schemas.py`
- Evidence:
```python
if func_name in ("task_write", "task_state"):
    result = await self._execute_tool(session, func_name, func_args)
    ...
    if tw_mode == "init":
        plan_dict = session.task_manager.to_analysis_plan_dict()
        yield _new_analysis_plan_event(plan_dict)
```
- Why it matters: TODO 系统不是一个独立模块，而是 runner 的特殊分支。任何新状态或新生命周期都得同时改工具、runner、事件与前端消费。

### [N8] 子 Agent 不共享父任务板，多代理调度与 TODO 系统是分离的
- Pattern: `dispatch_agents` 走 `spawn_batch()` 并行派发，但 `SubSession` 会新建一个空的 `TaskManager`；子 Agent 既不会 claim 父任务，也不会把结果写回任务生命周期。
- Location: `src/nini/tools/dispatch_agents.py`, `src/nini/agent/spawner.py`, `src/nini/agent/sub_session.py`
- Evidence:
```python
sub_results = await self._spawner.spawn_batch(task_pairs, session, parent_turn_id=turn_id)
```
```python
def __post_init__(self) -> None:
    ...
    self.task_manager = TaskManager()
```
- Why it matters: `nini` 现在有“多 Agent 执行”和“任务清单”两套机制，但二者没有真正合流，因此无法形成多代理共享任务账本。

### [N9] `depends_on` 与前端状态映射都存在实现裂缝
- Pattern: `TaskManager` 提供 `group_into_waves()` 和 `depends_on`，但更新任务时没有把 `depends_on` 带回去；同时后端步骤状态是 `pending/completed`，前端展示状态是 `not_started/done`，必须额外归一化。
- Location: `src/nini/agent/task_manager.py`, `web/src/types/analysis.ts`, `web/src/store/normalizers.ts`
- Evidence:
```python
new_tasks.append(
    TaskItem(
        id=task.id,
        title=str(upd.get("title", task.title)),
        status=new_status,
        tool_hint=upd.get("tool_hint", task.tool_hint),
        action_id=task.action_id,
    )
)
```
```ts
case "pending":
case "not_started":
  return "not_started";
case "completed":
case "done":
  return "done";
```
- Why it matters: 一方面依赖关系会在状态变更后丢失，另一方面前后端还要靠额外映射兜底，说明模型边界没有稳定下来。

### [N10] `pending_actions` 已经形成第二套“待办账本”
- Pattern: 会话还维护了独立的 `pending_actions` 列表，用来记录脚本未执行、用户确认待回复、工具失败未解决等阻塞项，并且这一套是直接持久化到 session meta 的。
- Location: `src/nini/agent/session.py`, `src/nini/harness/runner.py`, `src/nini/tools/code_session.py`
- Evidence:
```python
pending_actions: list[dict[str, Any]] = field(default_factory=list)
...
session.upsert_pending_action(
    action_type="script_not_run",
    key=script_id,
    status="pending",
    summary=summary,
    source_tool="code_session",
)
```
- Why it matters: 当前仓库实际上已经同时存在“任务计划板”和“待处理动作账本”两套状态系统，这会增加心智负担，也容易造成重复表达或状态不一致。

### Gap Analysis

| Capability | claw-code | nini (current) | Gap |
|---|---|---|---|
| Task model | `[C1]` 轻量任务记录，字段集中，状态 `created/running/completed/failed/stopped` | `[N2]` 会话内 `TaskItem`，额外有 `depends_on/tool_hint/action_id` | `nini` 模型更丰富，但没有配套独立模块与稳定生命周期 |
| Agent assignment | `[C4]` `team_id` 可回填到任务；`[C5]` 子代理有 manifest/lane events | `[N8]` `dispatch_agents` 与 `TaskManager` 脱钩，子会话重置任务板 | `nini` 缺少 claim/assign/release 机制，多代理无法共享同一任务账本 |
| Status tracking | `[C3]` 工具直接读写同一注册表；`[C5]` 代理状态走 lane events | `[N4]` 任务推进带自动完成副作用；`[N7]` runner 特判后再转事件 | `nini` 状态推进耦合在工具和 runner 中，副作用较多，不利于扩展 |
| Persistence | `[C1]` 任务仅内存；`[C6]` TODO 单独写 JSON 文件 | `[N5]` 任务靠消息回放恢复；`[N10]` pending_actions 单独持久化 | `nini` 没有显式任务存储，且任务与 pending_actions 分裂成两套持久化路径 |
| Lifecycle API | `[C3]` create/get/list/update/stop/output | `[N3]` init/update/get/current | `nini` 缺少取消、失败、释放、输出、指派等运行时操作 |
| Dependency support | `[C1][C2]` 无原生优先级/依赖 | `[N2][N9]` 有 `depends_on`，但只停留在模型/展示层 | `nini` 的依赖支持未接入真实调度，而且更新时会丢字段 |
| UI contract | `[C5][C6]` manifest 文件与 TODO 文件各自稳定 | `[N7][N9]` runner 事件 + 前端归一化 + `raw_status` 补丁 | `nini` 前后端状态命名不统一，增加了消费复杂度 |

### Pain Points

1. 缺少多代理认领语义：`dispatch_agents` 并行执行子任务，但任务板没有 `assigned_to/claimed_at/released_at`，无法表达谁在做什么，对应 `[N8]`。
2. 持久化路径脆弱：任务恢复依赖消息回放，且更新字段名已经漂移，对应 `[N5][N6]`。
3. 抽象边界不清：任务工具、runner 特判、WebSocket 事件、前端归一化都在各自处理状态，对应 `[N3][N4][N7][N9]`。
4. 两套待办系统并存：`task_manager` 负责计划步骤，`pending_actions` 负责阻塞动作，但两者没有统一模型，对应 `[N10]`。
5. 生命周期不完整：没有 first-class 的 `assigned/failed/cancelled/released`，也没有审计事件流，对应 `[N3][N4]`。
6. 依赖关系实现不闭环：模型有 `depends_on`，测试有 `group_into_waves()`，但实际多代理执行并不消费这些信息，而且更新时会丢失依赖字段，对应 `[N2][N9]`。

## nini Current State

### 1. TODO 状态存储在哪里，结构是什么

`nini` 当前没有独立的 TaskStore。会话内任务主要存在 `Session.task_manager`，模型是 `TaskItem(id/title/status/tool_hint/action_id/depends_on)`，只在 Python 内存对象里维护。

- Location: `src/nini/agent/task_manager.py`
- Evidence:
```python
@dataclass(frozen=True)
class TaskItem:
    id: int
    title: str
    status: TaskStatus = "pending"
    tool_hint: str | None = None
    action_id: str | None = None
    depends_on: list[int] = field(default_factory=list)
```

会话恢复时，`task_manager` 不是直接持久化，而是从历史消息里的 `task_write/task_state` 工具调用“重放”出来；与此同时，`deep_task_state` 和 `pending_actions` 又单独写入 `meta.json + SQLite`。

- Location: `src/nini/agent/session.py`
- Evidence:
```python
if self.messages:
    self._reconstruct_task_manager_from_messages()
...
raw_deep_task_state = meta.get("deep_task_state")
raw_pending_actions = meta.get("pending_actions")
...
self._save_session_meta_fields(session_id, {"pending_actions": normalized})
```

除此之外，`nini` 还有第三套任务表示：`ExecutionPlan`。它描述 phase/action 计划，但不和 `task_manager` 共用数据结构。

- Location: `src/nini/models/execution_plan.py`
- Evidence:
```python
class ExecutionPlan(BaseModel):
    user_intent: str
    phases: list[PlanPhase]
    status: PlanStatus = Field(default=PlanStatus.PENDING)
    current_phase_index: int = Field(default=0)
```

### 2. 当前支持哪些操作（CRUD）

面向 LLM 暴露的是 `task_state` 与 `task_write`。支持的核心操作只有：
- `init`：初始化完整任务列表
- `update`：按任务 ID 更新状态
- `get`：读取全部任务
- `current`：读取当前 `in_progress` 任务

没有真正的 `delete/cancel/release/assign/list by owner`。

- Location: `src/nini/tools/task_state.py`, `src/nini/tools/task_write.py`
- Evidence:
```python
"enum": ["init", "update", "get", "current"]
...
return await self._delegate.execute(session, mode=operation, tasks=tasks)
```

`update` 的状态推进是局部状态机：把新任务设为 `in_progress` 时，前一个 `in_progress` 自动转为 `completed`。这是串行推进假设，不是通用调度器。

- Location: `src/nini/agent/task_manager.py`
- Evidence:
```python
if upd.get("status") == "in_progress":
    new_in_progress_ids.add(tid)
...
elif task.status == "in_progress" and new_in_progress_ids:
    TaskItem(id=task.id, title=task.title, status="completed", ...)
```

### 3. Agent 如何与 TODO 系统交互

主 Agent 在 `runner.py` 中对 `task_write/task_state` 做了硬编码分支。工具执行成功后，Runner 直接把 `task_manager` 转成 `ANALYSIS_PLAN / PLAN_PROGRESS / PLAN_STEP_UPDATE` 事件，并用当前 `in_progress` 任务去给普通工具调用补 `action_id`。

- Location: `src/nini/agent/runner.py`
- Evidence:
```python
if session.task_manager.has_tasks():
    plan_dict = session.task_manager.to_analysis_plan_dict()
    yield eb.build_analysis_plan_event(...)
...
if func_name in ("task_write", "task_state"):
    result = await self._execute_tool(session, func_name, func_args)
```

多 Agent 路径没有共享任务账本。`SubSession` 会新建一个独立 `TaskManager`，`SubAgentSpawner` 只是把父会话数据集与事件回调传进去，没有任务 claim/release。

- Location: `src/nini/agent/sub_session.py`, `src/nini/agent/spawner.py`
- Evidence:
```python
class SubSession(Session):
    persist_runtime_state: bool = False
    def __post_init__(self) -> None:
        self.task_manager = TaskManager()
...
sub_session = SubSession(
    parent_session_id=parent_session.id,
    datasets=parent_session.datasets,
    event_callback=self._make_subagent_event_callback(...),
)
```

另外，深度任务（Recipe 工作流）完全绕开 `TaskManager`，走 `deep_task_state` + WebSocket 事件路径，把步骤再映射成一套 `analysis_plan` 数据。

- Location: `src/nini/api/websocket.py`
- Evidence:
```python
session.deep_task_state.update(
    {"task_id": task_id, "status": workflow_status, ...}
)
await _send_event(ws, EventType.ANALYSIS_PLAN.value, data={"steps": steps, ...})
await _send_event(ws, EventType.PLAN_PROGRESS.value, data={...})
```

### 4. 具体痛点

#### 4.1 任务模型分裂成三套状态源
- 现状：`TaskManager`、`deep_task_state`、`ExecutionPlan` 分别维护任务/步骤/阶段。
- Location: `src/nini/agent/task_manager.py`, `src/nini/api/websocket.py`, `src/nini/models/execution_plan.py`
- Evidence:
```python
tasks: list[TaskItem] = field(default_factory=list)
...
session.deep_task_state.update({...})
...
class ExecutionPlan(BaseModel):
    phases: list[PlanPhase]
```
- 影响：同一个“任务”概念在不同链路里被重复建模，后续一旦要加 owner、deadline、priority，就必须三处同步演化。

#### 4.2 恢复逻辑依赖消息重放，而且当前实现有字段不匹配缺陷
- 现状：`_reconstruct_task_manager_from_messages()` 在 `update` 分支读取 `updates`，但 `task_state/task_write` 真正传的是 `tasks`。
- Location: `src/nini/agent/session.py`, `src/nini/tools/task_state.py`
- Evidence:
```python
elif operation == "update":
    updates = args.get("updates", [])
    if updates and rebuilt.initialized:
        result = rebuilt.update_tasks(updates)
...
return await self._delegate.execute(session, mode=operation, tasks=tasks)
```
- 影响：会话恢复后，任务大概率只能恢复到 init 状态，更新历史可能丢失；这说明 TODO 状态并不是一等持久化数据。

#### 4.3 工具层抽象耦合，读写接口实际上只是写接口代理
- 现状：`TaskStateTool` 号称统一接口，但写路径完全委托给 `TaskWriteTool`；`TaskWriteTool` 同时负责任务状态机、LLM 行为引导、消息文案生成。
- Location: `src/nini/tools/task_state.py`, `src/nini/tools/task_write.py`
- Evidence:
```python
class TaskStateTool(Tool):
    def __init__(self) -> None:
        self._delegate = TaskWriteTool()
...
message = (
    f"任务{current_in_progress.id}「{current_in_progress.title}」已标记为进行中。"
    f"请立即调用对应工具执行该任务..."
)
```
- 影响：状态管理和“提示词驯化”绑在一起，后续若要增加 API、队列、审计日志或非 LLM 调用方，复用会很差。

#### 4.4 Agent 编排与任务系统没有统一的 claim / release / owner 语义
- 现状：主 Agent 只能把当前 `in_progress` 任务映射成 `action_id`；子 Agent 创建自己的 `TaskManager`，不会登记到父会话任务上。
- Location: `src/nini/agent/runner.py`, `src/nini/agent/sub_session.py`
- Evidence:
```python
in_progress_task = session.task_manager.current_in_progress()
if in_progress_task:
    matched_action_id = in_progress_task.action_id
...
self.task_manager = TaskManager()
```
- 影响：多代理协作只能“并行跑”，不能“认领同一任务账本中的任务”；失败重试、转派、释放占用都没有统一落点。

#### 4.5 Runner / WebSocket 对任务事件做了大量专用编排，边界不清晰
- 现状：任务更新后要由 `runner.py` 手工发计划事件，由 `websocket.py` 手工发 deep task 事件。
- Location: `src/nini/agent/runner.py`, `src/nini/api/websocket.py`
- Evidence:
```python
yield _new_analysis_plan_event(plan_dict)
yield _new_plan_progress_event(...)
...
await _send_event(ws, EventType.ANALYSIS_PLAN.value, data={"steps": steps, ...})
await _send_event(ws, EventType.PLAN_PROGRESS.value, data={...})
```
- 影响：事件发射分散在多个调用栈中，未来要接审计日志、指标、hooks 时，很难保证所有状态转移都被统一观察到。

### Gap Analysis

| Capability | claw-code | nini (current) | Gap |
|---|---|---|---|
| Task model | 单一 `Task` 记录，字段含 `task_id/prompt/status/messages/output/team_id/task_packet` | `TaskItem` 只覆盖会话步骤；另有 `deep_task_state` 与 `ExecutionPlan` 并行存在 | 任务模型分裂，缺少统一主记录 |
| Agent assignment | `TeamCreate` 把 `team_id` 回填到任务；`Agent` 有独立 manifest/lane events | 子 Agent 使用独立 `SubSession`，不 claim 父任务 | 没有任务 owner / claim / release 机制 |
| Status tracking | `created/running/completed/failed/stopped` + `lane_events` | `pending/in_progress/completed/failed/skipped`；deep task 另有 `queued/running/retrying/...` | 状态语义不统一，缺少统一生命周期 |
| Persistence | 任务注册表内存态；TODO 列表直接落 `.clawd-todos.json` | `task_manager` 主要靠消息重放恢复；`deep_task_state/pending_actions` 落 `meta.json + SQLite` | 没有一等任务存储层，恢复链路脆弱 |
| CRUD / control | create/get/list/update/stop/output | init/update/get/current | 缺少 delete、cancel、release、assign、output/audit |
| Dependency support | `TaskPacket` 约束执行契约，但无一等依赖图 | `TaskItem.depends_on` 支持 wave 分组，但未进入多代理调度 | 有字段，无真正调度闭环 |
| Multi-agent reporting | manifest 文件 + `lane_events` 表达 started/blocked/failed/finished | 事件主要靠 `AgentRunner` / `WebSocket` 临时拼装 | 缺少统一 task event / audit log 总线 |
