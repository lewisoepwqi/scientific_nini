## Why

当前 `nini` 在真实分析会话中的主要失效点，已经不再是单个工具能力不足，而是运行时大量关键行为仍依赖模型“读懂消息后主动遵守”。这会在弱模型、长上下文压缩、脚本恢复路径和完成校验阶段反复触发空转、漏执行、误完成和失败信息丢失，因此需要把关键执行状态、恢复线索和调试入口从文本提示升级为结构化运行时能力。

## What Changes

- 为 harness 运行时新增统一的 `pending_actions` 状态账本，用于显式跟踪未执行脚本、未处理工具失败、未落地产物和待确认动作。
- 调整脚本会话行为，使 `create_script` 默认走自动执行链路；未自动完成时必须把待处理状态写入运行时账本，而不是仅返回文本警告。
- 将 completion check 从关键词/提示词驱动，升级为基于结构化证据的校验逻辑，统一覆盖未处理失败、未完成任务、承诺产物未生成和仅描述下一步未执行等场景。
- 为 harness 增加每轮摘要快照与调试入口，支持后续实现 `debug summary/load-session/snapshot` 一类的诊断能力。
- 为工具暴露面增加前置策略控制，允许按阶段、风险和授权状态收缩当前轮可见工具面，减少不必要的工具误选。
- 补充压缩与恢复契约，确保 `pending_actions`、任务进度和关键失败线索不会在上下文压缩后丢失。
- 扩展 CLI 诊断能力，为 `doctor --surface` 或等价入口提供工具面/技能面/过滤后暴露面的可观测输出。
- 非目标：本次 change 不进行全量 `runner.py` 大拆分、不引入全局 immutable session 改造、不以 token-based 路由替代现有语义驱动工具选择。

## Capabilities

### New Capabilities
- `runtime-debug-snapshot`: 定义每轮 harness 执行的结构化摘要快照及其调试/回放入口。
- `tool-exposure-policy`: 定义按任务阶段、风险和授权状态前置过滤可见工具面的策略能力。

### Modified Capabilities
- `agent-harness-runtime`: 扩展 harness 运行时的状态注入、结构化完成校验、失败恢复线索和超时后待处理状态管理。
- `script-session`: 调整脚本创建后的默认执行行为，并要求未完成脚本状态可被显式追踪与恢复。
- `compression-segments`: 扩展压缩后的状态保留契约，确保关键运行时状态可跨压缩恢复。
- `cli-diagnostics`: 扩展 CLI 诊断输出，支持运行面与工具面可观测信息，而不只覆盖单一依赖检查。

## Impact

- 受影响代码主要位于 `src/nini/agent/`、`src/nini/harness/`、`src/nini/tools/`、`src/nini/memory/` 和 CLI 入口相关模块。
- 受影响运行面包括 WebSocket 会话执行、脚本会话恢复、completion check、上下文压缩恢复和工具暴露策略。
- 需要新增或更新对应测试，重点覆盖脚本自动执行、pending action 持久化、压缩后状态恢复、completion evidence 校验和 CLI 诊断输出。
- 不计划新增外部依赖，优先复用现有会话持久化、trace、settings 和 CLI 基础设施。
- 风险在于运行时状态对象与现有 session/task manager 语义重叠，若设计不当可能引入双重状态源；回滚策略应允许先通过 feature flag 或兼容字段保留旧路径。
