## Why

现有 Markdown Skills（`.nini/skills/*/SKILL.md`）采用提示词驱动模式：YAML frontmatter 声明元数据（name、category、allowed-tools），正文用自然语言描述工作流步骤。这种模式缺乏结构化执行契约——没有 steps DAG、input/output schema、trust_ceiling、review_gate 和 observability 事件。随着 V1 扩展到新研究阶段，需要一套统一的 Skill 执行契约，让运行时可以：

1. 解析并验证 Skill 的步骤依赖关系
2. 在高风险步骤前插入人工复核门（review_gate）
3. 标注每个步骤的信任等级和输出等级
4. 发出结构化的 observability 事件（供 C12 面板消费）
5. 处理步骤失败的降级和回退

本 change 定义 Skill 执行契约的数据模型和运行时框架，是 C6-C8 新阶段能力实现的基础。

## What Changes

- **定义 Skill 执行契约模型**：在 `src/nini/models/` 中新增 `skill_contract.py`，定义 `SkillContract`（契约根）、`SkillStep`（步骤）、`StepDependency`（依赖关系）、`ReviewGate`（人工复核门）等 Pydantic 模型。
- **扩展 Markdown Skill frontmatter**：在现有 YAML frontmatter 中新增可选的 `contract` 段，声明 steps、trust_ceiling、review_gates 等结构化字段。保持向后兼容——无 contract 段的旧 Skill 继续以现有模式运行。
- **实现 Skill 契约解析器**：扩展 `markdown_scanner.py`，解析 frontmatter 中的 contract 段并实例化为 `SkillContract` 模型。
- **实现 Skill 步骤执行运行时**：在 `src/nini/skills/` 中新增 `contract_runner.py`，提供按 steps DAG 顺序执行步骤、review_gate 检查、observability 事件发射的框架。
- **定义 observability 事件 schema**：在 `event_schemas.py` 中新增 `SkillStepEventData`，包含 skill_name、step_id、status、trust_level、output_level 等字段。

## Non-Goals

- 不为现有 4 个 Markdown Skills 添加 contract（它们继续以现有模式运行）。
- 不实现 review_gate 的前端 UI 交互（仅定义事件和后端逻辑）。
- 不实现 steps DAG 的可视化。
- 不实现完整的错误恢复策略（V1 仅支持步骤级 retry 和 skip）。

## Capabilities

### New Capabilities

- `skill-contract-model`: Skill 执行契约数据模型——涵盖 SkillContract、SkillStep、ReviewGate 等 Pydantic 模型定义
- `skill-contract-runtime`: Skill 契约运行时——涵盖契约解析、步骤 DAG 执行、review_gate 检查、observability 事件发射

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`src/nini/models/skill_contract.py`（新建）、`src/nini/skills/contract_runner.py`（新建）、`src/nini/tools/markdown_scanner.py`（扩展解析）、`src/nini/models/event_schemas.py`（新增事件）
- **影响范围**：Skill 系统的执行方式（新 Skill 可选择使用契约模式，旧 Skill 不受影响）
- **API / 依赖**：WebSocket 事件新增 skill_step 类型，无新增外部依赖
- **风险**：核心风险是契约运行时的复杂度——需控制 V1 范围，仅实现线性 DAG（无并行分支），review_gate 仅阻塞等待用户确认
- **回滚**：删除新建文件 + revert markdown_scanner.py 和 event_schemas.py 的扩展即可恢复
- **验证方式**：单元测试验证契约模型序列化/反序列化、DAG 拓扑排序、review_gate 判定逻辑、事件发射；集成测试验证带 contract 的 Skill 端到端执行
