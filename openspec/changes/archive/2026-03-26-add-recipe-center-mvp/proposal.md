## Why

当前 Nini 已具备较完整的工具、能力与工作区底盘，但用户仍主要通过自由对话触发复杂科研任务，首次使用成功率高度依赖提示词质量。为了落实 `docs/scienceclaw_benchmark_and_iteration_plan.md` 中“先产品入口，后深度优化”的策略，需要先把高频深任务收敛为可推荐、可执行、可回滚的 Recipe MVP，为后续证据链、导出与评测 change 提供稳定入口。

## What Changes

- 新增 `Recipe Center`，在首页提供首批 3 个高频科研任务模板与示例输入，作为通用会话入口的补充而不是替代。
- 新增 `deep task workflow` 最小执行契约，定义 Recipe 元数据、步骤 DAG、输入参数、默认输出与失败回退规则。
- 为 deep task 增加“项目工作区初始化 + 步骤进度展示”能力，使长流程任务具备最小可观察性。
- 扩展 WebSocket 事件与工作区行为，使前端能够接收 Recipe 启动、步骤进度、失败重试与工作区创建结果。
- 非目标：本 change 不包含 Citation Graph、Claim 校验、METHODS 自动写作、Word/PPT/LaTeX 导出与成本治理告警。

## Capabilities

### New Capabilities

- `recipe-center`: 提供首页 Recipe 入口、模板元数据契约、示例输入与默认推荐规则。
- `deep-task-workflow`: 提供 quick task / deep task 分类、Recipe 执行状态机、项目工作区引导与失败恢复约束。

### Modified Capabilities

- `workspace`: 补充 deep task 启动时的项目工作区创建、Recipe 相关文件归档与会话绑定行为。
- `websocket-protocol`: 补充 Recipe 启动、步骤进度、失败重试与工作区初始化反馈事件的协议要求。

## Impact

- 后端会影响 `src/nini/agent/`、`src/nini/api/`、`src/nini/models/` 与工作区管理相关模块。
- 前端会影响 `web/src/components/`、`web/src/store/`、首页入口与任务进度展示。
- 需要新增 Recipe 配置文件或 schema，但不引入新的外部服务依赖。
- 验证方式至少包括 `pytest -q`、`cd web && npm run build`，并补充 Recipe/进度事件相关测试。
