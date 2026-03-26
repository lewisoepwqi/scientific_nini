## Context

现有 Skill 系统由 `markdown_scanner.py` 扫描 `.nini/skills/*/SKILL.md`，解析 YAML frontmatter 为 `MarkdownTool` 数据类，通过 `tool_adapter.py` 适配为 LLM 可调用的工具。执行时将 Skill 正文作为系统提示词注入，LLM 自主按提示词步骤执行。

C2 已定义 `RiskLevel`、`OutputLevel`、`TrustLevel` 枚举。C3 已为 Capability 标注阶段和风险属性。本 change 在 Skill 层建立结构化执行契约，使运行时可以精确控制步骤流程、信任边界和人工复核。

## Goals / Non-Goals

**Goals:**
- 定义 Skill 契约的完整数据模型
- 支持从 Markdown frontmatter 解析契约
- 实现步骤 DAG 执行框架（V1 限线性 DAG）
- 实现 review_gate 阻塞机制
- 发射结构化 observability 事件
- 完全向后兼容（无 contract 的旧 Skill 不受影响）

**Non-Goals:**
- 不实现并行分支 DAG
- 不实现前端 review_gate UI
- 不迁移现有 Skill 到契约模式

## Decisions

### D1: SkillContract 数据模型结构

**选择**：

```python
class SkillStep(BaseModel):
    id: str                                    # 步骤标识，如 "load_data"
    name: str                                  # 步骤显示名称
    description: str                           # 步骤说明
    tool_hint: str | None = None               # 推荐使用的工具
    depends_on: list[str] = []                 # 前置步骤 ID 列表
    trust_level: TrustLevel = TrustLevel.t1    # 步骤信任等级
    review_gate: bool = False                  # 是否需要人工复核
    retry_policy: str = "skip"                 # 失败策略：retry / skip / abort

class SkillContract(BaseModel):
    version: str = "1"                         # 契约版本
    trust_ceiling: TrustLevel = TrustLevel.t1  # 整体信任上限
    steps: list[SkillStep]                     # 步骤列表
    input_schema: dict[str, Any] = {}          # 输入参数 schema（JSON Schema 子集）
    output_schema: dict[str, Any] = {}         # 输出参数 schema
    evidence_required: bool = False            # 是否要求证据溯源
```

**理由**：Pydantic v2 模型便于序列化/反序列化、与 YAML frontmatter 互转。字段参考 vision charter 的 skill-contract-spec 和实际需求，V1 保持精简。

**替代方案**：使用 dataclass → 但项目其他模型均使用 Pydantic，保持一致性。

### D2: frontmatter 扩展方式

**选择**：在现有 YAML frontmatter 中新增顶级 `contract` 键，值为 SkillContract 的 YAML 表示。

示例：
```yaml
---
name: experiment-design-helper
description: ...
category: workflow
contract:
  version: "1"
  trust_ceiling: t1
  steps:
    - id: define_problem
      name: 问题定义
      description: 明确研究假设和变量
      trust_level: t1
    - id: choose_design
      name: 设计选择
      description: 选择实验设计类型
      depends_on: [define_problem]
      trust_level: t1
    - id: calculate_params
      name: 参数计算
      description: 样本量估算等
      depends_on: [choose_design]
      trust_level: t1
      review_gate: true
---
```

**理由**：在现有 frontmatter 结构内扩展，`markdown_scanner.py` 已有 YAML 解析逻辑，最小改动。无 `contract` 键的旧 Skill 自动跳过契约解析，完全兼容。

### D3: 契约运行时架构

**选择**：新建 `src/nini/skills/contract_runner.py`，包含 `ContractRunner` 类：

```
ContractRunner
├── __init__(contract: SkillContract, callback: EventCallback)
├── run(session, inputs) -> ContractResult
│   ├── 拓扑排序 steps
│   ├── 逐步执行
│   │   ├── 发射 step_start 事件
│   │   ├── 检查 review_gate → 发射 review_required 事件 → 等待确认
│   │   ├── 执行步骤（调用 tool_hint 或 LLM 推理）
│   │   ├── 发射 step_complete / step_failed 事件
│   │   └── 应用 retry_policy
│   └── 发射 contract_complete 事件
└── _topological_sort(steps) -> list[SkillStep]
```

**理由**：独立的 Runner 类解耦了契约执行逻辑与现有的 AgentRunner ReAct 循环。ContractRunner 通过 callback 发射事件，与现有事件系统一致。

**替代方案**：在 AgentRunner 中内嵌契约逻辑 → 会污染核心循环，增加耦合。

### D4: review_gate 机制

**选择**：V1 的 review_gate 通过 WebSocket 事件通知前端，并阻塞 ContractRunner 等待用户确认（通过 asyncio.Event）。若用户在超时时间内未确认，按 retry_policy 处理。

**理由**：最简实现。前端 UI 交互不在本 change 范围，但后端机制需就绪。测试中可通过 mock callback 模拟用户确认。

### D5: observability 事件设计

**选择**：新增 `SkillStepEventData`：

```python
class SkillStepEventData(BaseModel):
    skill_name: str
    skill_version: str = "1"
    step_id: str
    step_name: str
    status: str  # "started" | "completed" | "failed" | "skipped" | "review_required"
    trust_level: str | None = None
    output_level: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    error_message: str | None = None
    duration_ms: int | None = None
```

**理由**：参考 vision charter 的 observability 规范，每条事件包含 skill_name、step_id、status 等核心字段。通过现有 WSEvent 推送，事件类型为 `skill_step`。

### D6: 向后兼容策略

**选择**：`markdown_scanner.py` 在解析 frontmatter 时，若检测到 `contract` 键则实例化 `SkillContract` 并附加到 `MarkdownTool.metadata["contract"]`。`tool_adapter.py` 在适配 Skill 为工具时，检测到 contract 则使用 `ContractRunner` 执行，否则走现有提示词注入路径。

**理由**：最小侵入式改造，旧 Skill 代码路径完全不变。

## Risks / Trade-offs

- **[风险] ContractRunner 的 review_gate 阻塞可能导致超时** → 设置合理超时（默认 5 分钟），超时按 retry_policy 处理。
- **[风险] V1 仅支持线性 DAG，限制了复杂工作流** → 线性 DAG 覆盖 V1 所有场景（文献调研、实验设计、论文写作的步骤都是线性的）。并行分支留待后续迭代。
- **[风险] tool_adapter.py 的分支逻辑增加维护成本** → 通过明确的 if/else 和注释标记两条路径，避免混淆。
- **[回滚]** 删除新文件 + revert scanner/adapter/event_schemas 的扩展即可恢复。
