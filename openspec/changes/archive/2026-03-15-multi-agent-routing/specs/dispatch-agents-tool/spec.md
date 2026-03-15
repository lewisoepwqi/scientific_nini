## ADDED Requirements

### Requirement: DispatchAgentsTool 工具接口
系统 SHALL 提供 `DispatchAgentsTool`，继承 `src/nini/tools/base.py:Skill`，名称为 `"dispatch_agents"`；参数：`tasks: list[str]`（必填，需要并行处理的任务描述列表）、`context: str`（可选，背景信息）；`execute(session, tasks, context="")` SHALL 依次调用 TaskRouter → SubAgentSpawner → ResultFusionEngine，返回 `SkillResult(content=fusion_result.content)`。

#### Scenario: dispatch_agents 正常执行
- **WHEN** 以合法 `tasks` 列表调用 `execute()`
- **THEN** 返回 `SkillResult` 的 `content` SHALL 包含融合后的结果文本
- **AND** 父会话 `session.artifacts` SHALL 包含子 Agent 的产物

#### Scenario: tasks 为空时返回空结果
- **WHEN** 调用 `execute(session, tasks=[])`
- **THEN** 返回 `SkillResult(content="")` 或包含提示信息
- **AND** SHALL 不抛出异常

---

### Requirement: DispatchAgentsTool 注册到 ToolRegistry
`DispatchAgentsTool` SHALL 在 `create_default_tool_registry()` 中注册，工具名 `"dispatch_agents"` SHALL 不包含在 `LLM_EXPOSED_BASE_TOOL_NAMES` 中（避免子 Agent 递归派发）。

#### Scenario: dispatch_agents 可通过 ToolRegistry 获取
- **WHEN** 调用 `registry.get("dispatch_agents")`
- **THEN** SHALL 返回 `DispatchAgentsTool` 实例

#### Scenario: dispatch_agents 不在子 Agent 的受限工具集
- **WHEN** 调用 `registry.create_subset(LLM_EXPOSED_BASE_TOOL_NAMES)`
- **THEN** 返回的子集 SHALL 不包含 `"dispatch_agents"`

---

### Requirement: DispatchAgentsTool 依赖注入
`DispatchAgentsTool` 需要 `AgentRegistry`、`SubAgentSpawner`、`ResultFusionEngine` 实例；这些依赖 SHALL 通过构造函数注入，`create_default_tool_registry()` 在创建时传入已初始化的实例。

#### Scenario: 依赖未注入时返回明确错误
- **WHEN** `DispatchAgentsTool` 的任意依赖为 `None`
- **AND** 调用 `execute()`
- **THEN** 返回 `SkillResult(success=False, content="dispatch_agents 未正确初始化")` 或等效错误信息
- **AND** SHALL 不抛出未捕获异常
