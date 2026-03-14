## Context

当前 Nini 已有较完整的单 Agent 运行链路：`FastAPI/WebSocket` 负责会话入口与事件推送，`AgentRunner` 负责 ReAct 主循环，前端通过 Zustand store 消费 `reasoning`、`tool_call`、`task_attempt`、`plan_progress` 等事件。项目也已经具备部分稳定性基础，例如工具重试、计划状态、上下文预算控制、运行时不可信上下文分层，以及针对 reasoning、fallback、conversation observability 的测试。

问题在于，这些能力仍然主要以内联逻辑分散在 `runner.py`、`websocket.py`、事件模型与前端 store 中，缺少一个显式的 harness 层来统一处理以下跨切面问题：

- Agent 何时可以“真的完成”，以及完成前必须做哪些验证。
- 当模型陷入重复失败、过早收尾、只描述下一步不执行时，如何触发统一恢复策略。
- 如何把一次运行的关键轨迹以本地可回放方式记录下来，用于维护期调优而不是仅靠线上日志排障。
- 如何把阶段化推理预算、验证状态和阻塞状态表达成明确的系统行为，而不是散落在 prompt 或个别事件中。

这个变更覆盖后端运行编排、WebSocket 事件契约、前端运行状态展示，以及维护者侧的本地 trace/eval 能力，因此属于典型的跨模块架构变更，适合先出设计文档再进入 specs 和实现。

相关约束：

- 保持当前单进程架构，不引入外部 tracing/eval 平台作为前提。
- 不推翻现有 `AgentRunner`，而是在其外围增加明确的 harness 编排层。
- 不改变 prompt trust boundary；新增运行上下文仍属于 runtime context，而不是 system prompt。
- 变更必须与现有 `reasoning`、`task_attempt`、`ask_user_question`、`workspace_update`、重试机制兼容。

## Goals / Non-Goals

**Goals:**
- 在 `AgentRunner` 外建立显式 harness 运行层，统一管理上下文注入、完成前验证、坏循环恢复和推理预算调度。
- 引入本地 trace 存储与回放评测能力，让稳定性问题可以被分类、聚合和复现。
- 扩展事件协议和前端状态，使验证、恢复、阻塞从“内部逻辑”变成可观察的用户界面状态。
- 为后续实现提供明确模块边界，避免继续把跨切面逻辑堆进 `runner.py`。

**Non-Goals:**
- 不在本次设计中引入多 Agent 委派、外部 LangSmith/Langfuse 之类托管平台，或持续学习系统。
- 不重新设计统计分析能力、知识检索策略或领域工作流模板。
- 不要求第一阶段自动修复所有失败；优先保证失败被正确识别、阻断、解释和记录。
- 不把 OpenSpec 产物中的设计约束直接映射为运行时 prompt 文案。

## Decisions

### 1. 新增 `HarnessRunner` 包装层，而不是继续扩张 `AgentRunner`

实现上新增一个独立运行编排层，例如 `HarnessRunner` 或同类组件，对外仍暴露与现有运行链路兼容的事件流接口；内部由它调用 `AgentRunner.run()`，并在运行前后和关键分支上插入 guard、verification、trace 记录与恢复逻辑。

选择原因：
- `AgentRunner` 当前已经承载了上下文构建、LLM 调用、工具执行、reasoning 追踪和若干恢复逻辑，继续扩张会进一步降低可维护性。
- 包装层更适合承载“运行策略”，而 `AgentRunner` 保持“执行循环”职责更清晰。
- WebSocket 入口未来可以直接切换为依赖 harness，而 CLI/测试回放也能复用同一运行编排。

备选方案：
- 直接把 harness 逻辑继续写进 `AgentRunner`：短期改动少，但会继续加重中心类，拒绝。
- 完全拆成 Planner/Executor 双 Agent：收益更大，但超出维护期第一阶段范围，拒绝。

### 2. 用中间件式运行阶段钩子统一处理跨切面逻辑

harness 层内部采用固定生命周期钩子，而不是把每种规则写成一串条件分支。建议至少定义这些阶段：

- `before_run`: 组装确定性运行上下文摘要。
- `before_model_call`: 注入阶段性预算与恢复提示。
- `after_model_output`: 判断是否出现过早完成、过渡性文本、计划漂移。
- `before_emit_done`: 执行 completion checklist。
- `after_tool_result`: 更新循环检测、trace、恢复上下文。
- `after_run`: 落盘 trace 与结果摘要。

选择原因：
- 这些逻辑天然横跨模型调用、工具调用与事件发送，适合中间件式治理。
- 当前项目已经存在事件驱动与 callback 风格，接入钩子成本低。
- 中间件比单个“万能 guard 类”更容易做单测和增量扩展。

备选方案：
- 用一个大 `HarnessPolicy` 对象在每个分支手工调用：可实现，但可读性和扩展性较差。

### 3. Completion Verification 采用“结构化清单 + 阻断继续执行”而不是仅靠 prompt 提醒

新增 Completion Verifier，在模型尝试结束、发送 `done` 前，依据当前会话状态和任务轨迹执行结构化校验。输出不是单纯布尔值，而是一组 checklist items 与缺口说明。

第一版默认检查：
- 是否回到用户原始问题作答。
- 是否完成必要的数据/方法前提说明，或明确声明跳过原因。
- 是否生成承诺的产物或说明未生成原因。
- 是否存在失败但被忽略的工具结果。
- 是否仅描述“下一步要做什么”但没有实际完成。

行为约束：
- 若校验未通过，不允许立即结束。
- harness 改为注入“继续执行当前任务”的恢复消息，并记录 `completion_check` 事件。
- 连续多次未通过后进入 `blocked` 或 `reconsider_plan`，而不是无限重复提示。

选择原因：
- 对科研分析场景，最大问题不是模型不知道答案，而是“过早自信结束”。
- 仅靠 system prompt 提醒很容易被忽略，结构化校验才能形成稳定边界。

备选方案：
- 只在 prompt 中强调“请验证后结束”：实现简单，但无法保证执行，拒绝。
- 完全依赖后端硬编码业务规则：会过度绑定到某些分析流程，因此采用“通用 checklist + 少量场景规则”的折中方案。

### 4. 坏循环检测改为“分析行为级”而不是文件编辑级

对于 Nini，doom loop 的表现不是改同一文件，而是重复调用同类分析工具、重复失败、反复输出类似解释、长时间停留在同一步计划。因此循环检测采用以下信号：

- 同一 `tool + dataset/resource + 近似参数` 连续失败。
- 同一步计划出现过多 `retrying` 而无新增 artifact 或状态推进。
- 连续出现过渡性文本且未伴随有效工具调用。
- 在互斥统计方法间来回切换但没有新证据。
- 连续多轮推理文本相似但未新增结论、产物或计划推进。

恢复动作按等级执行：
- 先发 `reasoning/recovery` 提示当前循环类型。
- 再触发一次缩减上下文的重规划。
- 仍无效则进入 `blocked`，把恢复交回用户或更高层策略。

选择原因：
- 这与项目现有 `task_attempt`、`reasoning`、`plan_progress` 数据模型天然契合。
- 若沿用 coding agent 的 file-edit heuristic，会与科研分析场景失配。

备选方案：
- 不做显式检测，只依赖模型自我修复：维护期效果不稳定，拒绝。

### 5. Trace/Eval 采用“SQLite 索引 + 本地 JSON 明细”的双层存储

本地 trace 系统分两层：

- 明细层：每次运行保存结构化 JSON/JSONL，记录事件序列、模型调用、工具调用、校验结果、恢复路径、最终状态。
- 索引层：SQLite 保存运行摘要、失败标签、耗时、token 与成本聚合，支持筛选与统计。

选择原因：
- JSON 便于调试、回放和导出样例。
- SQLite 便于按 change、模型、失败类型、日期做聚合分析。
- 该方案保持本地优先，不依赖外部平台也不妨碍未来接入额外 sink。

备选方案：
- 全部只写 JSON：查询和聚合成本高。
- 全部只写数据库：调试单次运行和导出回放不方便。
- 直接接入外部 tracing 平台：超出当前约束，拒绝。

### 6. 推理预算按运行阶段切换，而不是整轮固定

在 harness 层根据当前阶段切换 reasoning budget：

- `planning / replan / final verification`: 高
- `routine execution / tool follow-up`: 中
- `simple explanatory follow-up`: 低或沿用默认

实现方式优先保持对现有 `ModelResolver` 的最小侵入：harness 在每次模型调用前计算预算提示或调用参数，而不是改写整个模型路由层。

选择原因：
- 当前项目已经有计划模型、reasoning 事件和复杂度差异明显的步骤，按阶段切换最自然。
- 对多步任务，真正需要高推理开销的是规划和校验，而不是每次工具后续文本。

备选方案：
- 整轮统一最高预算：成本高，且容易拉长超时风险。
- 完全交给模型自适应：未来可考虑，但当前需要更可控的运行边界。

### 7. 协议扩展采用新增事件类型，而不是复用现有字段硬塞语义

为 harness 新增明确事件：

- `run_context`: 当前轮运行关键上下文摘要。
- `completion_check`: 校验项、通过状态、缺失动作。
- `blocked`: 阻塞原因、是否可恢复、建议动作。

原因：
- 这些状态与普通 `reasoning` 或 `error` 不同，属于系统运行语义。
- 独立事件让前端和测试更容易按类型消费，避免把状态硬塞进 `metadata` 导致契约模糊。

备选方案：
- 复用 `reasoning` 展示验证与阻塞：对用户可读，但协议层可验证性差。
- 只在 `error` 中表达 blocked：会误导客户端把“需要澄清/重新规划”当成失败终止。

## Risks / Trade-offs

- [新增 HarnessRunner 后运行链路更深] → 通过保持事件流接口不变、先在 WebSocket 入口单点接入来控制迁移面。
- [Completion checklist 过严可能导致模型多跑几轮] → 第一阶段只拦截高价值错误结束场景，并为重复失败设置 blocked 上限。
- [坏循环检测阈值不当会误报] → 先采用保守阈值，并把触发原因记录进 trace 以便迭代调优。
- [新增事件会增加前后端契约成本] → 把协议变化集中在显式事件类型上，并为旧客户端保留兼容路径。
- [本地 trace 存储增长较快] → 在索引层保留摘要，在明细层增加保留策略或按会话/日期清理。
- [预算分阶段切换会让行为更复杂] → 把预算决策集中到 harness 一处，避免散落在业务代码中。

## Migration Plan

1. 先引入 trace 数据模型和 completion/blocked 事件结构，不改变现有主运行入口。
2. 新增 HarnessRunner，并让 WebSocket 入口改为通过 HarnessRunner 驱动 Agent 运行。
3. 接入 Completion Verifier 与循环检测，先输出事件与 trace，不立即启用强阻断。
4. 验证事件和 trace 稳定后，再开启“未通过校验不可直接 done”的阻断策略。
5. 最后接入阶段化推理预算和前端状态展示。

回滚策略：
- 若 harness 包装层引发回归，可先退回由 WebSocket 直接调用 `AgentRunner`，保留 trace 模型与新增事件定义。
- 若 completion 阻断影响正常任务完成率，可先将 verifier 降级为观测模式，只记录不阻断。

## Open Questions

- completion checklist 中哪些条目应为通用规则，哪些应允许 capability 级定制。
- 本地 trace 的回放入口是否直接走 CLI，还是同时提供只读 API 给调试页面。
- 前端是否需要独立的“运行诊断”面板，还是先在现有分析计划/推理区域增量承载这些状态。
