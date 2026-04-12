## Why

Anthropic 工程团队的实测数据表明：Lead 用强模型（Opus）+ Worker 用轻量模型（Sonnet/Haiku）的混合策略，比单一模型方案性能高 90.2%，且上下文隔离后 token 用量减少 67%。当前 Nini 的所有 Specialist Agent 使用与主 Agent 相同的模型，无论任务是数据清洗（重复性高、模式固定）还是统计建模（推断复杂、需要推理深度），都消耗同等成本。与此同时，当前 9 个 Specialist Agent 的完整系统提示始终驻留在主 Agent 上下文中（以 skills snapshot 形式），随着 Agent 数量增加，上下文负担持续增长。

## What Changes

- **`AgentDefinition` 新增 `model_preference` 字段**（可选，默认继承父 Agent 模型）：允许每个 Specialist Agent 声明首选模型等级（`"haiku"` / `"sonnet"` / `"opus"` / `null`）；`SubAgentSpawner` 在实例化子 Agent 的 `AgentRunner` 时，根据 `model_preference` 选择对应模型
- **内置 Specialist Agent YAML 更新**：为 9 个 Agent 根据任务复杂度分配合理的 `model_preference`（数据清洗、文献检索用 `haiku`；统计分析、报告撰写用 `sonnet`；研究规划、方法论评审不设限，继承父 Agent 模型）
<!-- lazy_prompt（渐进式上下文披露）已移出本 change，留给独立的后续迭代决策 -->

## Capabilities

### Modified Capabilities
- `agent-registry`：`AgentDefinition` 新增 `model_preference: str | None` 字段
- `sub-agent-spawner`：`_execute_agent()` 根据 `AgentDefinition.model_preference` 为子 Agent 选择模型

## Impact

- **受影响代码**：
  - `src/nini/agent/registry.py`（`AgentDefinition` 数据类 + lazy_prompt 加载）
  - `src/nini/agent/spawner.py`（`_execute_agent()`：model_preference → ModelResolver 选择）
  - `src/nini/agents/*.yaml`（9 个 Agent 定义文件新增 `model_preference` 字段）
  - `src/nini/config.py`（`agent_lazy_prompt_enabled` 配置项）
- **受影响测试**：
  - `tests/test_spawner.py`（新增 model_preference 路由测试）
  - `tests/test_phase1_agent_registry.py`（新增 model_preference 字段解析测试）
- **非目标**：不实现动态模型成本优化（运行时根据预算选模型）；不将 lazy_prompt 模式设为默认行为；不改变主 Agent 的模型选择逻辑
- **依赖前提**：无前置 change 依赖（可独立实施，但建议在 C1-C3 稳定后再开展）
