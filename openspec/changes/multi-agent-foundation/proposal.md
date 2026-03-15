## Why

Scientific Nini 当前是单 Agent 架构，复杂科研工作流（如"数据清洗 + 统计分析 + 可视化"）只能由一个 Agent 串行处理，无法将独立子任务并行分发给专业化的 Specialist Agent。本变更建立多 Agent 协作所需的基础设施三件套（注册中心、隔离上下文、动态派生器），是后续路由、并行执行和 Hypothesis-Driven 范式的前置依赖。

## What Changes

- **新增** `src/nini/agent/registry.py`：`AgentDefinition` 数据类 + `AgentRegistry` 注册中心，支持加载内置和自定义 Agent 定义
- **新增** `src/nini/agent/sub_session.py`：`SubSession`，继承 `Session` 并覆盖 `__post_init__` 跳过磁盘持久化，提供子 Agent 独立上下文
- **新增** `src/nini/agent/spawner.py`：`SubAgentSpawner`，支持单次派生、指数退避重试（最多 3 次）、批量并行（最多 4 个并发）
- **新增** `src/nini/agent/prompts/agents/*.yaml`：9 个内置 Specialist Agent 的提示词配置文件
- **修改** `src/nini/tools/registry.py`：`ToolRegistry` 增加 `create_subset(allowed_tool_names)` 方法，用于为子 Agent 构造受限工具视图
- **修改** `src/nini/agent/events.py`：新增 5 个 WebSocket 事件类型（`agent_start`、`agent_progress`、`agent_complete`、`agent_error`、`workflow_status`）
- **新增** `web/src/store/agent-slice.ts`：AgentSlice 状态（activeAgents、completedAgents）
- **新增** `web/src/store/agent-event-handler.ts`：处理新增多 Agent 事件
- **新增** `web/src/components/AgentExecutionPanel.tsx`：展示并行运行中的 Agent 列表及实时状态

## Capabilities

### New Capabilities

- `agent-registry`：Agent 声明模型（AgentDefinition）与注册中心（AgentRegistry），含 9 个内置 Specialist Agent 定义（文献检索、精读、数据清洗、统计分析、可视化、学术写作、研究规划、引用管理、审稿助手）
- `sub-session`：子 Agent 隔离执行上下文，继承主 Session 接口但跳过磁盘持久化；共享数据集为只读，产物通过 SubAgentResult 单向回写到父会话
- `sub-agent-spawner`：子 Agent 动态派生机制，支持受限工具注册表、指数退避重试、批量并行（max_concurrency=4）、超时强制终止
- `multi-agent-events`：多 Agent 协作 WebSocket 事件协议，定义 agent_start / agent_progress / agent_complete / agent_error / workflow_status 的 payload 结构与前端状态同步规则

### Modified Capabilities

（无：现有 spec 层级需求不变，`conversation` 和 `websocket-protocol` 仅追加事件类型，不修改既有要求）

## Impact

### 后端

- 新增：`src/nini/agent/registry.py`、`sub_session.py`、`spawner.py`
- 新增：`src/nini/agent/prompts/agents/`（9 个 .yaml 文件）
- 修改：`src/nini/tools/registry.py`（增加 `create_subset()` 方法）
- 修改：`src/nini/agent/events.py`（追加 5 个枚举值）

### 前端

- 新增：`web/src/store/agent-slice.ts`、`agent-event-handler.ts`
- 新增：`web/src/components/AgentExecutionPanel.tsx`
- 修改：`web/src/store/types.ts`（增加 AgentInfo、AgentSlice 类型）
- 修改：`web/src/store/event-handler.ts`（注册新事件处理器）

### 测试

- 新增：`tests/test_agent_registry.py`、`test_sub_session.py`、`test_tool_registry_subset.py`、`tests/test_spawner.py`

### 依赖

无新增外部依赖，复用现有 `asyncio`、`pydantic`、`PyYAML`（已有）技术栈。
