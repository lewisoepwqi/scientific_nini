## 1. 运行时状态基础

- [x] 1.1 在 `src/nini/agent/session.py` 中引入统一的 `pending_actions` 运行时状态结构，并定义最小字段集（类型、唯一键、状态、说明、来源工具、时间戳）。
- [x] 1.2 实现 `pending_actions` 的增删改辅助方法，并明确其与 task manager、tool failure trace 的职责边界。
- [x] 1.3 在 `src/nini/agent/components/context_builder.py` 和 `src/nini/agent/prompt_policy.py` 中增加 `pending_actions` 运行时上下文块及其预算优先级。
- [x] 1.4 为 `pending_actions` 的会话持久化与恢复补充后端测试，验证跨轮次和恢复场景下状态不丢失。

## 2. 脚本会话与完成校验

- [x] 2.1 在 `src/nini/tools/` 的脚本会话实现中增加 `create_script` 默认自动执行链路，并保留显式关闭自动执行的兼容开关。
- [x] 2.2 在脚本自动执行失败、显式不自动执行和后续执行成功三种路径中，接入 `pending_actions` 的登记与清理逻辑。
- [x] 2.3 在 `src/nini/harness/runner.py` 中引入 `CompletionEvidence` 或等价结构，将未解决失败、承诺产物、待处理动作、任务完成比例和 transitional output 纳入统一校验。
- [x] 2.4 将 `artifact_promised_not_materialized`、`user_confirmation_pending` 和 `task_noop_blocked` 接入 `pending_actions` 与 recovery prompt 构建链路。
- [x] 2.5 将超时失败接入 `pending_actions`，并按 `purpose` 区分超时策略与恢复路径。
- [x] 2.6 为脚本自动执行、completion evidence、timeout 恢复和待处理动作分类补充回归测试，覆盖已知 `create_script` 漏执行与 completion recovery 失效案例。

## 3. 快照诊断与工具暴露策略

- [x] 3.1 新增 `HarnessSessionSnapshot` 摘要对象及持久化逻辑，记录 `session_id`、`turn_id`、`stop_reason`、`pending_actions`、`task_progress`、`tool_failures`、`selected_tools`、`token_usage` 和 `trace_ref`。
- [x] 3.2 增加基于快照的 CLI 诊断入口，至少覆盖 `debug summary`、`debug snapshot`、`debug load-session` 或等价命令，并复用现有 CLI 基础设施。
- [x] 3.3 扩展 `nini doctor` 或等价 CLI，提供 surface 诊断输出，展示当前 tools、skills、过滤后工具面和高风险工具摘要。
- [x] 3.4 引入 `ToolExposurePolicy` 的最小实现，先覆盖 `profile`、`analysis`、`export` 三类阶段的工具面裁剪与授权前置收缩。
- [x] 3.5 为快照查询、surface 诊断和工具暴露策略补充 CLI 与后端测试；如涉及 CLI 路径，检查 `tests/test_phase7_cli.py` 是否需要补充。

## 4. 压缩恢复、文档与整体验证

- [x] 4.1 在 `src/nini/memory/compression.py` 及相关上下文链路中，确保压缩后仍保留 `pending_actions`、任务进度和关键失败线索的可恢复引用。
- [x] 4.2 补充压缩与恢复契约测试，验证关键运行时状态不会在压缩后退化为未知或待执行状态。
- [x] 4.3 更新相关设计/开发文档，说明 `pending_actions`、快照诊断和工具暴露策略的行为边界与非目标。
- [x] 4.4 运行 `pytest -q` 完成后端回归验证；如 CLI 有改动，同时验证 CLI 测试；如前端诊断入口有改动，再执行 `cd web && npm run build`。
