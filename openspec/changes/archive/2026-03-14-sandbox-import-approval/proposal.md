## Why

当前 `run_code` 的 Python 沙盒对非白名单包导入采用直接拒绝策略：模型只能收到“沙箱策略拦截”错误，用户无法参与判断该扩展包是否值得为当前任务临时授权。这使得 `sympy`、`plotnine` 等低风险科研扩展包在明确业务需要时也无法使用，影响分析链路的可用性与用户控制感。

现在推进这项变更，是因为仓库已经具备 `ask_user_question`、会话持久化和工具重试等基础设施，可以在不放宽整体安全边界的前提下，为低风险扩展包补上结构化审批闭环。

## What Changes

- 为 Python 沙盒新增“可审查导入”分层：对白名单外但可审查的低风险扩展包，不再直接硬拒绝，而是转入用户审批流程。
- 为 `run_code` 增加结构化审批反馈能力，使工具结果能够明确表达“需要用户确认后再继续”。
- 复用现有 `ask_user_question` 事件流，为用户提供一次性、会话级、永久级三种授权决策。
- 增加会话内与跨会话的审批记录持久化能力，避免重复确认，同时保持默认拒绝。
- 保持网络、系统、动态执行类高风险模块继续硬拒绝；本变更不引入自动安装依赖，也不放宽 R 沙盒策略。

## Capabilities

### New Capabilities
- `sandbox-import-approval`: 为 Python 沙盒中的低风险扩展包导入提供用户参与式审批、授权范围管理与审计闭环。

### Modified Capabilities
- `tool-foundation`: `run_code` 工具结果契约新增“需要审批后重试”的受控分支，以便 Agent 在工具执行主循环中暂停并恢复。
- `websocket-protocol`: WebSocket 交互链路需要明确支持由沙盒审批触发的 `ask_user_question`/回答/重试事件序列。

## Impact

- 受影响代码：
  - `src/nini/sandbox/policy.py`
  - `src/nini/sandbox/executor.py`
  - `src/nini/tools/code_runtime.py`
  - `src/nini/agent/runner.py`
  - `src/nini/agent/session.py`
  - `src/nini/api/websocket.py`
- 受影响规范：
  - 新增 `openspec/specs/sandbox-import-approval/spec.md`
  - 修改 `openspec/specs/tool-foundation/spec.md`
  - 修改 `openspec/specs/websocket-protocol/spec.md`
- 受影响测试：
  - 新增沙盒审批相关单测
  - 补充 `run_code` 与 WebSocket 事件流回归测试
- 依赖与运行影响：
  - 不新增外部服务依赖
  - 继续复用现有 `ask_user_question` 与会话元数据持久化机制
