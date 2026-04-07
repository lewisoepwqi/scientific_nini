## Context

Nini 的模型路由已有"purpose"维度（`agent/resolver.py` 中不同 purpose 映射不同模型），但子 Agent 的模型选择没有利用这一机制——所有子 Agent 都通过 `SubSession` 继承父 Agent 的 model resolver，无差别使用同一模型。

`AgentDefinition` 当前字段：`agent_id`、`name`、`description`、`system_prompt`、`allowed_tools`、`max_turns`。需新增 `model_preference`。

## Goals / Non-Goals

**Goals:**
- 每个 Specialist Agent 可声明模型偏好，`spawner` 据此选择对应模型
- 不引入新的模型解析器，复用现有 `ModelResolver` 的 `purpose` 映射
- lazy_prompt 作为实验性功能，feature flag 控制，不影响默认行为

**Non-Goals:**
- 不实现运行时动态模型成本优化
- 不引入第三方框架
- lazy_prompt 不纳入本 change 的验收范围（仅搭框架，不设验收测试）

## Decisions

### 决策 1：`model_preference` 映射到 `purpose`

现有 `ModelResolver.chat(messages, tools, purpose=...)` 接受 `purpose` 参数决定模型选择。`model_preference` 字段的值映射如下：

| `model_preference` 值 | 对应 `purpose` |
|-----------------------|---------------|
| `"haiku"` | `"fast"` |
| `"sonnet"` | `"analysis"` |
| `"opus"` | `"deep_reasoning"` |
| `null`（默认） | 继承父 Agent purpose（`"analysis"`） |

不新增 purpose 类型，避免修改 ModelResolver 的核心路由逻辑。

### 决策 2：9 个 Specialist Agent 的模型分配

| Agent | `model_preference` | 理由 |
|-------|--------------------|------|
| `data_cleaner` | `"haiku"` | 规则性操作，无复杂推断 |
| `literature_searcher` | `"haiku"` | 关键词检索，输出格式固定 |
| `visualizer` | `"haiku"` | 图表参数计算，模式固定 |
| `statistician` | `"sonnet"` | 统计推断需要推理深度 |
| `report_writer` | `"sonnet"` | 长文本生成需要质量保证 |
| `data_analyst` | `"sonnet"` | 综合分析，复杂度中等偏高 |
| `hypothesis_tester` | `"sonnet"` | 假设推断需要逻辑严谨性 |
| `research_planner` | `null` | 研究规划最敏感，继承父模型 |
| `peer_reviewer` | `null` | 评审质量要求最高，继承父模型 |

### 决策 3：lazy_prompt 实现方式

`AgentDefinition.system_prompt` 改为 lazy 属性：YAML 中新增 `prompt_file: str` 字段（可选），指向独立的 prompt 文件路径。`agent_lazy_prompt_enabled=True` 时，`registry.get_agent(id)` 返回的 `AgentDefinition.system_prompt` 在首次访问时才从文件加载（`@functools.cached_property`）。

当前阶段不强制 Agent 迁移到 prompt_file 格式，两种格式（内联 system_prompt + 外部 prompt_file）并存。

## Risks / Trade-offs

- **`model_preference="haiku"` 降低子 Agent 质量**：分配 haiku 的 Agent 若遇到复杂边界情况可能输出质量下降 → 缓解：`model_preference` 是建议值，可通过 YAML 覆盖；上线后监控子 Agent 成功率
- **lazy_prompt 首次访问延迟**：文件 I/O 在首次路由时发生 → 由于使用 `cached_property`，每个 agent_id 只发生一次；生产环境可通过预热解决
- **purpose 映射与 ModelResolver 内部逻辑耦合**：若 resolver 修改 purpose 映射，子 Agent 模型选择会静默变化 → 在 resolver 的 purpose 映射旁加注释说明此依赖

## Migration Plan

**前提**：无强制前置 change，但建议在 C1-C3 稳定后实施，避免调试时多个变量同时变化。

1. 修改 `AgentDefinition`：新增 `model_preference: str | None = None`（向后兼容，现有 YAML 无需更改）
2. 修改 `spawner.py:_execute_agent()`：读取 `agent_def.model_preference`，传入对应 `purpose` 构造子 Agent 的 resolver
3. 更新 9 个 Agent YAML（按决策 2 的表格填写 `model_preference`）
4. 新增 `agent_lazy_prompt_enabled` 配置项和 `AgentDefinition.prompt_file` 支持（默认 false，不影响现有行为）
5. 更新测试，验证 model_preference 路由
