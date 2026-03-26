## ADDED Requirements

### Requirement: 契约解析器
`markdown_scanner.py` SHALL 在解析 Skill frontmatter 时，检测 `contract` 键并实例化为 `SkillContract` 模型，附加到 `MarkdownTool.metadata["contract"]`。

#### Scenario: 有 contract 的 Skill 解析成功
- **WHEN** 扫描包含 `contract` 段的 SKILL.md
- **THEN** 返回的 MarkdownTool 的 metadata["contract"] 为有效的 SkillContract 实例

#### Scenario: 无 contract 的旧 Skill 不受影响
- **WHEN** 扫描不包含 `contract` 段的 SKILL.md
- **THEN** 返回的 MarkdownTool 的 metadata 中不包含 "contract" 键，其他字段与升级前一致

#### Scenario: contract 格式错误时优雅降级
- **WHEN** Skill frontmatter 的 contract 段格式不合法
- **THEN** 记录警告日志，MarkdownTool 正常创建但 metadata 中不包含 "contract" 键

### Requirement: ContractRunner 步骤执行
系统 SHALL 提供 `ContractRunner` 类，按 steps DAG 的拓扑排序逐步执行步骤。

#### Scenario: 线性 DAG 按顺序执行
- **WHEN** contract 包含 A → B → C 的线性依赖
- **THEN** ContractRunner 按 A, B, C 顺序执行

#### Scenario: 步骤执行发射 start 事件
- **WHEN** ContractRunner 开始执行某步骤
- **THEN** 通过 callback 发射 skill_step 事件，status 为 "started"

#### Scenario: 步骤执行发射 complete 事件
- **WHEN** ContractRunner 成功完成某步骤
- **THEN** 通过 callback 发射 skill_step 事件，status 为 "completed"，包含 duration_ms

### Requirement: review_gate 阻塞机制
当步骤的 review_gate 为 True 时，ContractRunner SHALL 暂停执行并发射 review_required 事件，等待用户确认后继续。

#### Scenario: review_gate 发射事件
- **WHEN** 执行到 review_gate=True 的步骤
- **THEN** 发射 skill_step 事件，status 为 "review_required"

#### Scenario: 用户确认后继续
- **WHEN** 用户通过 WebSocket 确认 review_gate
- **THEN** ContractRunner 继续执行该步骤

#### Scenario: 超时按 retry_policy 处理
- **WHEN** review_gate 等待超时（默认 5 分钟）
- **THEN** 按步骤的 retry_policy 处理（skip 则跳过该步骤，abort 则终止整个契约）

### Requirement: 步骤失败处理
ContractRunner SHALL 根据步骤的 retry_policy 处理执行失败。

#### Scenario: skip 策略跳过失败步骤
- **WHEN** 步骤执行失败且 retry_policy 为 "skip"
- **THEN** 该步骤标记为 skipped，依赖该步骤的后续步骤也被 skipped，其余步骤继续执行

#### Scenario: abort 策略终止执行
- **WHEN** 步骤执行失败且 retry_policy 为 "abort"
- **THEN** 整个契约执行终止，发射 contract_failed 事件

#### Scenario: retry 策略重试一次
- **WHEN** 步骤执行失败且 retry_policy 为 "retry"
- **THEN** 重试一次，若仍失败则按 skip 处理

### Requirement: 契约执行结果
ContractRunner.run() SHALL 返回 `ContractResult`，包含整体状态（completed/failed/partial）、每个步骤的执行结果、总耗时。

#### Scenario: 全部成功
- **WHEN** 所有步骤成功完成
- **THEN** ContractResult 状态为 "completed"

#### Scenario: 部分成功
- **WHEN** 部分步骤被 skip
- **THEN** ContractResult 状态为 "partial"，包含 skipped 步骤列表

### Requirement: 工具适配器路由
`tool_adapter.py` SHALL 在适配 Skill 为工具时，检测 metadata 中是否包含 contract：有则使用 ContractRunner 执行，无则走现有提示词注入路径。

#### Scenario: 有 contract 的 Skill 使用 ContractRunner
- **WHEN** 执行包含 contract 的 Skill
- **THEN** 执行路径经过 ContractRunner

#### Scenario: 无 contract 的旧 Skill 走现有路径
- **WHEN** 执行不包含 contract 的旧 Skill
- **THEN** 执行路径与升级前完全一致
