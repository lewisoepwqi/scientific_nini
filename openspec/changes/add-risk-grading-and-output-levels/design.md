## Context

Nini 的 vision charter v2.0（`docs/nini-vision-charter.md` 第四章）定义了四级风险等级（低/中/高/极高）、四级输出等级（O1-O4）、trust-ceiling 映射（T1→O1/O2, T2→O3, T3→O4）和强制人工复核场景。C1 已在提示词 strategy.md 中引入了这些概念的使用规范。本 change 在代码层面实现结构化定义，使运行时可以标注、查询和校验这些等级。

现有代码中，`src/nini/models/` 已有丰富的枚举和 Pydantic 模型（如 `PlanStatus`、`ResourceType`），事件系统已有完整的 EventData 体系（`event_schemas.py`），WebSocket 事件通过 `WSEvent` 推送到前端。本 change 遵循这些既有模式。

## Goals / Non-Goals

**Goals:**
- 定义 `RiskLevel` 和 `OutputLevel` 枚举及其元数据
- 定义 trust-ceiling 映射规则
- 定义强制人工复核触发条件列表
- 在 Agent 输出事件中提供 output_level 标注能力
- 提供风险等级判定的工具函数（框架性，供后续 Change 丰富）

**Non-Goals:**
- 不实现前端 UI 展示
- 不实现 review_gate 交互流程（C4）
- 不为每个现有 Tool 标注风险等级（C3）
- 不修改提示词文件

## Decisions

### D1: 枚举与元数据的存放位置

**选择**：在 `src/nini/models/` 下新建 `risk.py`，存放 `RiskLevel`、`OutputLevel`、`TrustLevel` 枚举及相关常量。

**理由**：遵循现有模式——`models/` 已有 `execution_plan.py`（PlanStatus 枚举）、`session_resources.py`（ResourceType 枚举）。风险/输出等级是跨模块使用的基础模型，放在 models 层最合适。

**替代方案**：放在 `agent/` 下 → 但这些枚举不仅 Agent 使用，后续 Skill 执行契约也会引用，放 models 更通用。

### D2: 枚举实现方式

**选择**：使用 `(str, Enum)` 模式，值为英文小写标识符（`low`、`medium`、`high`、`critical`），元数据（中文名称、定义、示例）通过类方法或模块级字典提供。

**理由**：`str, Enum` 模式与项目现有枚举一致（`PlanStatus`、`ResourceType`），可直接序列化为 JSON 字符串。元数据通过字典映射，避免枚举类过于臃肿。

### D3: trust-ceiling 映射实现

**选择**：在 `risk.py` 中定义模块级常量 `TRUST_CEILING_MAP: dict[TrustLevel, list[OutputLevel]]`，表示每个信任等级允许的最高输出等级。

**理由**：映射关系是纲领性规则（T1→O1/O2, T2→O3, T3→O4），以常量形式定义即可，无需数据库存储。提供 `validate_output_level(trust: TrustLevel, output: OutputLevel) -> bool` 工具函数供运行时校验。

### D4: 输出标注注入方式

**选择**：在 `TextEventData` 和 `DoneEventData` 中新增可选字段 `output_level: OutputLevel | None = None`，Agent runner 在生成最终回复时根据上下文标注。

**理由**：增量字段（Optional），前端不消费时完全向后兼容。选择在事件 payload 中标注而非独立事件，减少事件流复杂度。`DoneEventData` 标注的是整轮回复的综合等级，`TextEventData` 的标注为可选（分片级标注，初期不启用）。

**替代方案**：新增独立的 `OutputLevelEventData` 事件类型 → 增加前端适配成本，且语义上输出等级是回复的属性而非独立事件。

### D5: 强制人工复核触发条件

**选择**：在 `risk.py` 中定义 `MANDATORY_REVIEW_SCENARIOS: list[str]` 常量，列出纲领中规定的 7 个强制复核场景。提供 `requires_human_review(risk_level: RiskLevel, scenario_tags: list[str]) -> bool` 工具函数。

**理由**：V1 阶段以声明式列表为主，风险判定逻辑较简单（高/极高风险 or 命中复核场景列表）。后续 Change 可增加基于上下文的动态判定。

### D6: 禁止性规则检查

**选择**：在 `risk.py` 中定义 `PROHIBITED_BEHAVIORS: list[str]` 常量，列出纲领第 4.4 节的 8 条禁止性规则。本 change 仅定义常量，不实现运行时拦截——拦截逻辑属于 C4（Skill 执行契约）中 review_gate 的范畴。

**理由**：禁止性规则的运行时检测需要语义理解（如「把草稿级伪装为已验证结论」），不适合简单的规则引擎。V1 先定义清单，供提示词和后续 Skill 契约引用。

## Risks / Trade-offs

- **[风险] 输出等级标注依赖 Agent 自主判断** → V1 阶段通过提示词引导 Agent 标注，准确性有限。后续可通过 Skill 契约中的 `trust_ceiling` 字段实现确定性标注。
- **[风险] DoneEventData 新增字段可能被旧版前端忽略** → Optional 字段，JSON 序列化后旧前端自动忽略未知字段，无破坏性。
- **[回滚]** 删除 `risk.py` + revert event_schemas.py 的字段新增即可恢复。
