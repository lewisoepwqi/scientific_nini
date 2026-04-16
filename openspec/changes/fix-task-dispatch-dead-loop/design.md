## Context

当前死循环问题不是单一工具调用失败，而是任务状态机、`dispatch_agents` 调度契约、Orchestrator 拦截路径、harness 恢复器和提示词约束之间的系统性语义错位。

现状中存在三个被混用的概念：

- 用户可见的计划任务：由 `task_state` / `task_write` 管理，承载标题、状态、工具提示与前后顺序。
- 当前执行任务：主 Agent 当前正在推进的步骤，由 `current_in_progress()` 隐式决定。
- specialist 子派发单元：通过 `dispatch_agents` 发起的并行辅助工作。

当前实现默认复用同一个 `task_id` 来承载上述三种语义，导致以下问题：

- 任务 1 一旦被标记为 `in_progress`，就会从 `group_into_waves()` 的 `pending` 集合中移除；
- `dispatch_agents` 只允许派发“当前 pending wave 中的任务”，因此再用 `task_id=1` 派发时必然触发 `TASK_NOT_IN_CURRENT_WAVE`；
- 模型在错误恢复时没有被强制切回“当前 Agent 直接执行”路径，而是继续把“使用 `code_session` / `run_code`”错误翻译为 `dispatch_agents(...)`；
- harness 只会计数并阻断，没有把错误路径转换成结构化的替代执行策略。

这个问题横跨 `src/nini/agent/task_manager.py`、`src/nini/tools/task_write.py`、`src/nini/tools/dispatch_agents.py`、`src/nini/agent/runner.py`、`src/nini/harness/runner.py`、`src/nini/agent/prompts/builder.py` 和 `src/nini/agent/components/context_builder.py`，属于明确的跨模块架构问题，适合先设计后实施。

## Goals / Non-Goals

**Goals:**

- 明确区分“计划任务”“当前执行任务”“子派发单元”的数据语义，消除单一 `task_id` 的歧义复用。
- 让 `dispatch_agents` 能区分“pending wave 派发”和“当前任务内部子派发”，并对错误上下文返回结构化恢复建议。
- 让 Orchestrator 与 harness 在识别调度误用后，能够限制错误路径并切换到可执行的直接工具路径，而不是仅做重试计数。
- 为任务初始化增加顺序/依赖规范化，避免串行流程被误初始化为同一个并行 wave。
- 在运行时上下文、trace snapshot、`pending_actions` 和日志中补充调度上下文诊断字段，便于复盘与回归测试。
- 在不引入新依赖的前提下完成上述改造，并建立可稳定复现此类问题的测试基线。

**Non-Goals:**

- 不重写整套 Agent ReAct 主循环，也不替换现有 ToolRegistry 或 SubAgentSpawner 基础设施。
- 不重新引入已在 `multi-agent-dag` / `dag-executor` 中移除的独立 DAG 执行引擎。
- 不在本次变更中扩展新的 specialist agent 能力，也不调整前端交互布局。
- 不追求一次性消除所有工具误用；本次只优先解决“任务状态与子派发语义错位”引发的稳定死循环。

## Decisions

### Decision 1：拆分三层执行语义，而不是继续复用主任务 `task_id`

**选择：**

在设计上明确区分：

- `PlanTask`：用户可见的主线任务，继续由 `TaskManager` 管理；
- `CurrentExecutionContext`：当前主 Agent 执行上下文，记录当前任务、推荐工具和调度限制；
- `DispatchSubtask`：由 `dispatch_agents` 发起的临时子派发单元，可引用 `parent_task_id`，但不要求等同于 `PlanTask.id`。

`dispatch_agents` 正式采用 `parent_task_id` 表达“当前任务内部子派发”语义，避免继续把主任务 `task_id` 当成待派发 wave 项使用。

**原因：**

当前死循环的根因就是“同一个 `task_id` 同时被当成 `in_progress` 主任务和 `pending wave` 派发项”。只在校验层做豁免会留下更多模糊语义，后续仍会反复遇到边界问题。

**备选方案：**

- 方案 A：保留现有模型，只在 `TASK_NOT_IN_CURRENT_WAVE` 时特殊放过 `in_progress task`。  
  未采用，因为这会让 `dispatch_agents` 同时接受“计划任务派发”和“当前任务内部派发”两种语义，但参数结构没有显式区分，继续加大歧义。

- 方案 B：回退到完全禁止 `dispatch_agents` 在任务执行场景中出现。  
  未采用，因为这会削弱多 agent 基础设施，并不能覆盖“当前任务内部的受控子派发”需求。

### Decision 2：保留 `pending wave` 语义，但新增显式的 dispatch context API

**选择：**

`TaskManager.group_into_waves()` 保持“只从 `pending` 任务计算可启动波次”的语义不变，用于计划推进；同时新增独立的 dispatch context 解析能力，统一提供：

- 当前 `in_progress` 主任务
- 当前 `pending wave`
- 当前是否允许直接执行、内部子派发或 pending wave 派发

`dispatch_agents` 不再直接依赖“当前 wave 是否包含 task_id”作为唯一判断条件，而是先读取 dispatch context，再走对应模式的校验分支。

**原因：**

`pending wave` 本身没有错，问题在于它被错误地拿来判断“当前执行中的任务是否还能派发”。保留其原始职责，新增更高层的 dispatch context，能最小化破坏并增强可解释性。

**备选方案：**

- 方案 A：让 `group_into_waves()` 同时包含 `in_progress` 任务。  
  未采用，因为这会污染原有“待开始任务分组”语义，并导致 `pending_count()`、前端进度头部、任务推进提示一起失真。

### Decision 3：任务初始化时做依赖规范化，而不是完全信任模型输出

**选择：**

在 `task_write init` 阶段增加计划质量校验与受限依赖规范化：

- 当任务满足内建且高置信的线性流水线判定规则时，自动补为链式依赖；
- 当仅检测到疑似顺序风险但无法高置信判定时，不自动改写任务图，只返回结构化 warning；
- 对显式并行安全的任务保留并行；
- 将规范化结果或 warning 通过 `normalized_dependencies`、`normalization_warnings` 或等价 metadata 回传给 session 与 trace。

这里的“高置信判定规则”必须来自显式、可枚举的内建模板或白名单组合，例如固定工具链顺序、受限任务模式或其他可单元测试覆盖的规则；不得把任意自然语言启发式直接视为可自动改写任务图的充分条件。

**原因：**

本次会话中任务 2/3/4 被错误视为当前 wave，并不是因为调度器主动乱算，而是因为初始化时任务依赖本来就丢失了。这个输入质量问题如果不在入口收敛，后续任何调度器都要为错误计划兜底；但规范化必须可解释、可预测，不能把 planner 的模糊输出静默改写成新的强约束。

**备选方案：**

- 方案 A：完全不改 init，只在运行时靠恢复器兜底。  
  未采用，因为这会让“坏任务图”长期存在，增加 trace 噪声与恢复难度。

- 方案 B：对所有无依赖多步骤任务一律补成串行链。  
  未采用，因为这会误伤本来独立的并行任务，把本次修复扩大成 planner 语义重写。

### Decision 4：把 `dispatch_agents` 错误从通用拒绝升级为结构化恢复合同

**选择：**

为 `dispatch_agents` 引入更细的错误模型，至少区分：

- 非法 agent 或误把工具名当 agent_id
- 当前任务应直接执行而非 pending wave 派发
- 当前任务允许内部子派发但参数未切换到 `parent_task_id`
- 任务间读写冲突导致必须串行

错误返回必须包含：

- `error_code`
- 当前 dispatch mode
- `current_in_progress_task_id`
- `current_pending_wave_task_ids`
- `recovery_action`
- `recommended_tools` 或 `recommended_dispatch_shape`

**原因：**

现有 `TASK_NOT_IN_CURRENT_WAVE` 只告诉模型“你错了”，没有告诉模型“下一步该怎么做”，恢复器和提示词也无法基于这个错误做可执行纠偏。

**备选方案：**

- 方案 A：只修改错误消息文案。  
  未采用，因为 harness 目前主要基于结构化字段和签名计数，单纯改文案不足以驱动纠偏。

### Decision 5：恢复器从“计数阻断”升级为“约束收紧 + 路径切换”

**选择：**

在 runner 和 harness 中配合新增基于 `error_code` 的恢复策略，但只由 runner 持有 turn 级调度护栏。对于本次问题相关的错误：

- `INVALID_AGENT_IDS`：在当前 turn 内禁止再次使用未注册 agent_id；
- `TASK_NOT_IN_CURRENT_WAVE` / 新的 dispatch context mismatch：在当前 turn 内收紧 `dispatch_agents` 的暴露或限制其可用形态，并将下一轮引导切回 `dataset_catalog` / `run_code` / `code_session`；
- 只有在恢复器已经切换路径后仍无推进时，才最终进入 `tool_loop`。

实现上不新增外部依赖，只在 session 运行时状态中增加由 runner 维护的 turn-scoped guard；harness 负责消费结构化错误、生成恢复建议、更新 `pending_actions` 和做 blocked 判定，但不再维护第二套 guard 状态。

**原因：**

当前 harness 在检测到同一路径失败后，只会提示“重规划”，但不会改变可选工具路径，导致模型有机会继续重复同一个错误动作。需要把“改变工具路径”的执行职责落在 runner，避免 runner/harness 双方各自维护一套局部拦截状态。

**备选方案：**

- 方案 A：把阈值从 2 次改成更大。  
  未采用，因为这只会延后阻断，不会改善恢复质量。

### Decision 6：把调度约束从普通提示词提升为高优先级运行时约束

**选择：**

在提示词系统中把 `dispatch_agents` 使用约束拆成独立的高优先级策略组件，并在 runtime context 中动态注入：

- 当前任务是否 `in_progress`
- 当前任务是否允许再次作为 `task_id` 派发
- 当前推荐执行工具
- 当 `dispatch_agents` 失败后本轮禁止的错误形态

同时在提示词中加入明确反例：

- 错误示例：`dispatch_agents(task_id=1, task=\"使用code_session查看前20行\")`
- 正确示例：`run_code(dataset_name=\"...\", code=\"print(df.head(20))\")`

**原因：**

现有约束虽然存在，但与动态运行时状态脱节，且在 `standard` prompt profile 下容易被截断或埋没在长文本中。

**备选方案：**

- 方案 A：只在错误后写入 reasoning 文本，不改系统提示结构。  
  未采用，因为这仍是软提醒，不足以稳定压制错误路径。

### Decision 7：统一记录调度上下文到 snapshot / pending actions / trace

**选择：**

为 runtime snapshot、trace event 和 `pending_actions` 统一增加调度诊断字段，例如：

- `dispatch_mode`
- `current_in_progress_task_id`
- `current_pending_wave_task_ids`
- `parent_task_id`
- `recovery_action`
- `tool_misuse_category`

对旧的 `dispatch_agents` 失败项做归并，避免同一逻辑错误在压缩后以多条未解决动作持续污染后续轮次。

**原因：**

当前分析必须同时翻 `session.db`、trace 和 `meta.json` 才能看清问题，说明观测粒度不够统一，也不利于后续做 trace 回放测试。

## Risks / Trade-offs

- [风险] 调整任务初始化依赖规范化后，可能改变现有任务板显示顺序或 pending 计数。  
  → Mitigation：保持主任务顺序不变，只补 `depends_on` 元数据；为前端相关测试增加快照断言。

- [风险] 为 `dispatch_agents` 引入 `parent_task_id` / 新模式后，旧调用路径可能出现兼容性分支。  
  → Mitigation：保留旧 `tasks=[{task_id,...}]` 形态作为兼容输入；`agents=[...]` 仅在无任务板上下文或上下文不影响派发语义时继续允许，在存在歧义的任务上下文中返回结构化迁移提示，而不做隐式绑定。

- [风险] 恢复器在当前 turn 收紧工具暴露，可能误伤少数本应允许的高级调度路径。  
  → Mitigation：使用基于 `error_code` 的定向限制，而不是全局禁用 `dispatch_agents`；为合法并行场景补集成测试。

- [风险] 提示词与 runtime context 的约束变多，可能增加 prompt 长度。  
  → Mitigation：将调度约束整理为高优先级短块，并利用结构化 runtime context 代替冗长自然语言说明。

- [风险] `pending_actions` 归并规则调整后，历史 trace 统计口径会发生变化。  
  → Mitigation：仅新增字段与归并策略，不删除已有 failure tag；更新对应诊断测试与文档说明。

## Migration Plan

1. 先重构任务初始化与 dispatch context 计算逻辑，确保不改变现有外部 API 的基本调用方式。
2. 再升级 `dispatch_agents` 的模式识别、错误模型和结构化恢复字段，同时补齐单元测试，并固化 `parent_task_id` 作为正式参数名。
3. 接着在 runner / harness 中接入基于 `error_code` 的恢复策略，其中 runner 维护 turn-scoped guard，harness 只维护恢复摘要与阻塞判定。
4. 最后调整提示词、runtime context 注入和 trace / snapshot 观测字段，并补真实 trace 回放测试。

发布策略：

- 该变更以内聚后端运行时改造为主，不要求额外依赖或数据库迁移；
- 可以一次性上线，但建议先在测试环境用已知死循环 trace 做回放验证；
- 如需回滚，可先回退恢复器与 `dispatch_agents` 结构化字段改动，再回退任务依赖规范化逻辑，保证运行主链可恢复到旧行为。

## Open Questions

- 任务初始化的依赖规范化后续是否需要接入更明确的 Recipe / skill contract，以减少对启发式规则的依赖？
- `dispatch_agents` 的错误收紧是否需要同时影响前端展示层，例如在计划头部显式显示“当前已禁用派发，需直接执行工具”？
