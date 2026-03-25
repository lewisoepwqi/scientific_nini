## Why

前面的 change 已经把 deep task 的入口、证据和交付物串起来了，但如果缺少统一的可观测与回归门禁，发布后仍然难以定位失败、评估回归和控制成本。维护阶段需要一个独立 change，把 deep task 的 tracing、可靠性策略、基准回放和预算阈值收束为可执行的运维最小闭环。

## What Changes

- 新增 `deep-task-observability` 能力，定义 `task_id` 贯穿、关键耗时/错误指标和任务级预算阈值。
- 扩展 harness 运行时能力，为外部依赖失败提供重试、幂等与分级超时策略。
- 扩展 harness 评测能力，建立核心 Recipe 基准集与发布前回归门禁。
- 扩展 WebSocket 协议，使前端与运行诊断能关联到统一的任务标识和尝试标识。
- 非目标：本 change 不包含独立运维后台、第三方遥测平台集成、跨环境集中式日志系统与新的业务功能。

## Capabilities

### New Capabilities

- `deep-task-observability`: 定义 deep task 的端到端标识、指标采集、预算阈值与告警约束。

### Modified Capabilities

- `agent-harness-runtime`: 扩展重试、幂等执行与超时分级策略。
- `agent-harness-evaluation`: 扩展核心 Recipe 基准集、回放评测与发布门禁阈值。
- `websocket-protocol`: 扩展任务标识、尝试标识与预算告警相关事件字段。

## Impact

- 后端会影响 Agent 运行时、工具调用编排、事件生成、trace 记录与预算统计。
- 前端会影响任务进度与诊断信息的关联展示。
- 不要求引入新的外部可观测平台，优先复用本地 trace、日志与现有 harness 能力。
- 验证方式至少包括 `pytest -q`、核心 Recipe 回放评测，以及 `cd web && npm run build`。
