## Why

Phase 1 建立了多 Agent 基础设施（Registry + SubSession + Spawner），但主 Agent 仍须手动调用 `SubAgentSpawner`，缺少将用户意图自动拆解并路由到合适 Specialist Agent 的能力，以及将多个 Agent 结果融合为统一输出的机制。本变更补齐这一"编排层"，让复杂科研请求（如"清洗数据 + 统计 + 作图"）真正实现自动并行分发与结果融合。

## What Changes

- **新增** `src/nini/agent/router.py`：`TaskRouter`，双轨制路由（关键词规则 <1ms + LLM purpose="planning" 兜底 ~500ms），输出 `RoutingDecision`
- **新增** `src/nini/agent/fusion.py`：`ResultFusionEngine`，支持 concatenate / summarize / consensus / hierarchical 四种策略，自动冲突检测（仅标注不阻断）
- **新增** `src/nini/tools/dispatch_agents.py`：`DispatchAgentsTool`，将 Router → Spawner → Fusion 串联为单一 LLM 可调用工具
- **修改** `src/nini/agent/runner.py`：在 tool_calls 解析后插入 Orchestrator 钩子，拦截 `dispatch_agents` 工具调用走多 Agent 路径，其余工具保持原有执行逻辑
- **修改** `src/nini/tools/registry.py`：在 `create_default_tool_registry()` 中注册 `DispatchAgentsTool`
- **新增** `web/src/components/WorkflowTopology.tsx`：纯 CSS 并行 Agent DAG 可视化，>=2 个 activeAgents 时展示
- **修改** `web/src/components/MessageBubble.tsx`：子 Agent 来源消息增加来源标签 `[Agent名称]`

## Capabilities

### New Capabilities

- `task-router`：双轨制任务路由，将自然语言意图映射到一组 Specialist Agent 及其任务描述
- `result-fusion-engine`：多 Agent 结果融合，支持 4 种策略和冲突标注
- `dispatch-agents-tool`：LLM 可调用的多 Agent 派发工具，串联 Router + Spawner + Fusion
- `orchestrator-mode`：runner.py Orchestrator 钩子，在不破坏现有 ReAct 逻辑的前提下支持多 Agent 分发
- `workflow-topology-ui`：前端并行 Agent 执行拓扑可视化组件

### Modified Capabilities

（无：现有 websocket-protocol 不新增事件类型，使用 Phase 1 已有的 agent_start/complete/error；runner.py 改动为内部实现，不改变外部接口规范）

## Impact

### 后端

- 新增：`src/nini/agent/router.py`、`src/nini/agent/fusion.py`、`src/nini/tools/dispatch_agents.py`
- 修改：`src/nini/agent/runner.py`（插入 Orchestrator 钩子，约 +50 行，不改现有代码路径）
- 修改：`src/nini/tools/registry.py`（注册新工具）

### 前端

- 新增：`web/src/components/WorkflowTopology.tsx`
- 修改：`web/src/components/MessageBubble.tsx`（增加来源标签渲染）

### 测试

- 新增：`tests/test_router.py`、`tests/test_fusion.py`、`tests/test_dispatch_agents.py`

### 依赖

- 复用 Phase 1：`AgentRegistry`、`SubAgentSpawner`（已实现）
- 无新增外部依赖
