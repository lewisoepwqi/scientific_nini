## Why

C1 在提示词层面引入了输出等级（O1-O4）和风险提示的概念描述，但运行时代码中尚无对应的结构化定义。Agent 目前无法在代码层面标注输出等级、判定风险级别或触发强制人工复核门。本 change 在代码中实现风险分级（低/中/高/极高）和输出等级（O1-O4）的枚举与标注机制，为后续所有能力扩展提供统一的风险-输出边界框架。

## What Changes

- **新增风险等级与输出等级枚举**：在数据模型层定义 `RiskLevel`（低/中/高/极高）和 `OutputLevel`（O1/O2/O3/O4）枚举类型及其元数据（名称、定义、用户预期）。
- **新增输出标注机制**：Agent 输出事件中携带 `output_level` 字段，标注当前输出的等级。
- **新增风险-输出关联规则**：定义 trust_ceiling 映射（T1→O1/O2, T2→O3, T3→O4），确保输出等级不超过能力信任度上限。
- **新增强制人工复核触发条件**：当输出涉及高风险或极高风险场景时，系统标注"需人工复核"并通过事件通知前端。
- **新增禁止性规则检查点**：在 Agent 输出流程中加入禁止性行为检查的扩展点（如不得把草稿级伪装为已验证结论）。

## Non-Goals

- 不修改提示词文件（identity.md、strategy.md 等提示词层面的风险描述已在 C1 完成）。
- 不实现前端 UI 对输出等级/风险标注的展示（属于后续 change）。
- 不实现完整的 review_gate 交互流程（属于 C4 Skill 执行契约的范围）。
- 不对现有 Tool 逐一标注风险等级（属于 C3 的范围）。

## Capabilities

### New Capabilities

- `risk-grading`: 风险分级框架——涵盖 RiskLevel 枚举、风险等级判定逻辑、强制人工复核触发条件、禁止性规则检查点
- `output-levels`: 输出等级标注——涵盖 OutputLevel 枚举、输出标注机制、trust-ceiling 映射、等级标注事件

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`src/nini/models/`（新增枚举与模型）、`src/nini/agent/runner.py`（输出标注注入点）、`src/nini/agent/`（风险判定工具函数）
- **影响范围**：Agent 运行时输出流程，所有输出事件新增 `output_level` 字段
- **API / 依赖**：WebSocket 事件 payload 新增可选字段（向后兼容），无新增外部依赖
- **风险**：输出标注为增量字段，前端未消费前不影响现有行为；风险判定逻辑初期为框架性实现，后续 Change 逐步丰富
- **回滚**：删除新增模型文件 + revert runner.py 的标注注入即可恢复
- **验证方式**：单元测试验证枚举定义、trust-ceiling 映射正确性、标注事件字段存在性
