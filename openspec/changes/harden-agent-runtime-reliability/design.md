## Context

当前 `nini` 的 Agent 可靠性问题主要集中在运行时状态表达方式，而不是单个工具能力缺失。根据已有分析，真实失效链路主要包括：

- `create_script` 创建后未继续执行，模型把 `success=true` 误读为“已完成”。
- `task_state` 和 completion recovery 仍大量依赖文本提示，弱模型容易忽略或误解。
- 工具失败、承诺产物未落地、用户待确认动作等关键信息分散在消息历史中，压缩后容易丢失。
- 当前缺少统一的调试摘要和运行面快照，问题排查仍依赖人工翻阅消息流与 trace。

这次变更是一个跨 `agent/`、`harness/`、`tools/`、`memory/` 和 CLI 的横切改动，适合先通过设计文档明确边界与技术决策，再推进后续 specs 和 tasks。

## Goals / Non-Goals

**Goals:**

- 用统一的结构化运行时状态替代零散的文本提醒与隐式历史线索。
- 将高频失效链路收敛为“系统自动链接”或“系统显式标记待处理状态”。
- 将 completion check 升级为基于结构化 evidence 的完成校验。
- 为每轮运行生成可持久化摘要快照，并提供后续 CLI 诊断入口的基础数据源。
- 在不引入新依赖的前提下，复用现有 session、trace、settings、CLI 基础设施完成增强。

**Non-Goals:**

- 不进行全量 `runner.py` 拆分。
- 不将整个 `Session` 改造成不可变模型。
- 不以 token-based 路由替代现有语义驱动工具选择。
- 不重写前端 WebSocket 事件协议，只在现有事件体系下增加可观测信息。

## Decisions

### 决策 1：引入统一 `pending_actions` 账本，而不是继续叠加零散字段

**决策：**
在会话运行时新增统一的 `pending_actions` 结构，作为未完成动作、失败恢复线索和待确认状态的唯一账本。首期覆盖以下类型：

- `script_not_run`
- `tool_failure_unresolved`
- `artifact_promised_not_materialized`
- `user_confirmation_pending`
- `task_noop_blocked`

账本将挂载在会话级运行时状态中，并参与：

- runtime context 注入
- completion evidence 构建
- snapshot 持久化
- 后续 CLI 调试输出

**为什么这样做：**

- 现有问题文档中的 `pending_script_ids`、`tool_failures`、completion recovery 等建议本质上都在描述“待处理动作”，应该统一抽象。
- 统一账本可减少后续新增状态字段时的语义分裂和维护成本。
- 相比单纯扩充压缩摘要内容，结构化账本更稳定，也更适合后续校验与诊断。

**备选方案：**

- 方案 A：只增加 `pending_script_ids` 和 `current_turn_tool_failures` 两个字段。
  结论：短期快，但会形成新的碎片化状态源，不利于扩展。
- 方案 B：完全依赖消息历史与 compression 摘要恢复。
  结论：已被真实案例证明不稳定，不采用。

### 决策 2：对 `create_script -> run_script` 采用“默认自动链接 + 未完成入账”

**决策：**
`script-session` 路径中，`create_script` 默认开启自动执行链路；只有显式要求不自动执行或自动执行失败时，才把该脚本登记到 `pending_actions`。

首阶段不引入通用 toolchain 框架，只把该高频路径以最小改动方式落地。后续若效果稳定，再推广到其他高频链路。

**为什么这样做：**

- `create_script` 漏执行是已验证的高频失效点，且根因明确。
- 直接自动链接的收益远高于继续优化 warning 文本。
- 先做单链路自动化，比一次性引入通用 toolchain 抽象风险更低。

**备选方案：**

- 方案 A：仅保留文本警告，要求模型继续调用 `run_script`。
  结论：已被问题文档判定为软约束失败，不采用。
- 方案 B：一次性引入通用 `Toolchain` 框架。
  结论：中长期可考虑，但对当前维护阶段过重，先不做。

### 决策 3：Completion Check 升级为“evidence -> check items”的两段式结构

**决策：**
将 completion verification 改为两段式：

1. 先从运行状态和消息事件中构建结构化 `CompletionEvidence`
2. 再由 evidence 映射成 completion check items 和 recovery prompt

首期 evidence 至少包含：

- unresolved tool failure
- promised artifact 是否落地产物
- 是否仍存在 `pending_actions`
- 任务完成比例
- 是否属于 transitional output

**为什么这样做：**

- 这可以统一承接当前分散在关键词、正则、消息替换和恢复提示里的逻辑。
- 结构化 evidence 更适合测试，也更适合后续 snapshot 与 CLI 展示。
- recovery prompt 可以基于 evidence 类型定制，而不是统一文本。

**备选方案：**

- 方案 A：继续扩展关键词和正则。
  结论：必要性低且边际收益差，不采用。
- 方案 B：仅在 harness 中增加更多 if/else 分支。
  结论：会继续加重 `runner.py` 的局部复杂度，不采用。

### 决策 4：新增 `HarnessSessionSnapshot`，但不做全量 immutable session

**决策：**
引入每轮运行后的不可变摘要快照 `HarnessSessionSnapshot`，作为调试、回放和 CLI 诊断的数据源，但不改变现有 `Session` 的可变运行模型。

快照只保存摘要字段和引用信息，不复制 DataFrame 或大体量产物：

- `session_id`
- `turn_id`
- `stop_reason`
- `pending_actions`
- `task_progress`
- `tool_failures`
- `selected_tools`
- `compressed_rounds`
- `token_usage`
- `trace_ref`

**为什么这样做：**

- 这吸收了不可变快照思维的优点，但避免全量 session 不可变改造的高成本。
- 快照更适合 CLI 与问题复盘，不应与实时会话对象混用。
- 可以为未来的 `debug summary`、`debug snapshot`、`debug load-session` 提供统一底座。

**备选方案：**

- 方案 A：不做快照，只依赖 trace 与消息流。
  结论：排障成本过高，不采用。
- 方案 B：直接把整个 Session 改为不可变。
  结论：侵入过大，不适合当前阶段。

### 决策 5：工具暴露策略前置，但按阶段渐进落地

**决策：**
新增 `ToolExposurePolicy` 能力，在每轮开始前根据任务阶段、风险等级和授权状态裁剪当前可见工具面。首期只覆盖最容易误选的几个阶段：

- `profile`
- `analysis`
- `export`

策略只负责“减少不该出现的工具”，不负责替代模型的完整语义判断。

**为什么这样做：**

- 当前问题中一部分误调用并不是工具能力不足，而是暴露面过宽。
- 相比执行后再阻断，前置过滤更符合“减少模型决策点”的方向。
- 渐进引入比一开始就做全场景策略更稳。

**备选方案：**

- 方案 A：保持当前工具全暴露，只加强 guardrail。
  结论：仍然会让模型在过宽工具面里误选，不足以解决问题。
- 方案 B：直接用简单关键词路由决定全部工具。
  结论：不适合科研分析语义复杂度，不采用。

### 决策 6：CLI 诊断分为“运行快照”和“surface 清单”两条线

**决策：**
CLI 诊断能力分成两类，而不是试图用一个命令覆盖所有问题：

- 运行快照类：`debug summary` / `debug snapshot` / `debug load-session`
- 工具面类：`doctor --surface`

前者解决“这一轮发生了什么”，后者解决“这一轮为什么暴露了这些工具”。

**为什么这样做：**

- 运行时问题与暴露面问题的排障视角不同。
- 这能分别复用 `HarnessSessionSnapshot` 与 tool registry / skills snapshot / policy filter。

**备选方案：**

- 方案 A：只做运行快照，不做 surface 诊断。
  结论：难以回答暴露面层的问题，不完整。
- 方案 B：只扩展 `doctor`，不做运行快照。
  结论：无法覆盖真实会话排障，不完整。

## Risks / Trade-offs

- [状态源重叠] `pending_actions`、task manager、tool failure trace 之间可能形成多源状态  
  → Mitigation：明确 `pending_actions` 只承载“待处理动作”，不重复存储完整任务或完整 trace。

- [自动执行副作用] `create_script` 默认自动执行可能影响少量需要先审查脚本内容的路径  
  → Mitigation：保留显式关闭自动执行的开关，并把关闭后的状态写入账本。

- [上下文膨胀] 新增 `pending_actions`、snapshot 信息可能增加 runtime context 体积  
  → Mitigation：runtime context 只注入精简摘要，完整内容进入 snapshot/CLI，不直接进入 prompt。

- [兼容性风险] completion verifier 逻辑升级后，部分旧测试或旧恢复行为可能变化  
  → Mitigation：采用 feature flag 或兼容分支逐步切换，并新增针对真实失效案例的回归测试。

- [工具面收缩过度] `ToolExposurePolicy` 如果策略过于激进，可能影响完成率  
  → Mitigation：首期只在 `profile/export` 等低歧义阶段启用，保留灰度与回退开关。

- [实现范围失控] snapshot、CLI、policy、completion evidence 都是横切改动，容易把本次 change 做成隐性大重构  
  → Mitigation：后续 tasks 必须分 iteration 拆解，先做 P0 行为可靠性，再做 P1 诊断能力。

## Migration Plan

1. 先在现有运行时链路中引入 `pending_actions` 数据结构与最小写入点，不替换既有 task manager 或 trace。
2. 在脚本会话中为 `create_script` 增加默认自动执行逻辑，并通过兼容开关保留显式关闭自动执行的旧路径。
3. 在 harness 中增加 `CompletionEvidence` 和新的 completion verifier，但允许通过 feature flag 或兼容分支保留旧校验逻辑作为回退路径。
4. 在快照与 CLI 诊断能力上线前，先只生成快照和内部读取接口；待输出格式稳定后再暴露正式 CLI 子命令。
5. `ToolExposurePolicy` 首期仅在低歧义阶段启用，并保留回退为“全暴露 + 现有 guardrail”的兼容路径。
6. 若任何一项增强导致完成率下降或恢复链路异常，可按模块回滚到旧的 completion check、旧的脚本执行路径或旧的工具暴露策略，而不需要回滚整轮改动。

## Open Questions

- `pending_actions` 应挂载在 `Session` 主对象上，还是挂载在 harness 级运行状态对象中并通过会话持久化引用？
- `HarnessSessionSnapshot` 的存储位置应复用现有 trace/session 目录，还是采用单独的快照存储文件布局？
- `debug load-session` 是否应直接展示最近快照，还是恢复为“快照 + trace 摘要”的组合视图？
- `ToolExposurePolicy` 的阶段判定应优先复用现有 phase/intent 结果，还是引入新的轻量阶段映射层？
- 对 `artifact_promised_not_materialized` 这类待处理动作，最终是以“重新执行”还是“文本说明影响”视为完成，需要在实现前固定判定规则。
