# skill-contract-model Specification

## Purpose
定义 Skill 契约的数据模型层，包括 SkillStep、SkillContract 和 SkillStepEventData 等核心 Pydantic 模型，以及依赖关系验证和信任等级约束规则。

## Requirements

### Requirement: SkillStep 模型定义
系统 SHALL 定义 `SkillStep` Pydantic 模型，包含以下字段：id（步骤标识）、name（显示名称）、description（说明）、tool_hint（推荐工具，可选）、depends_on（前置步骤 ID 列表）、trust_level（信任等级）、review_gate（是否需人工复核）、retry_policy（失败策略）。

#### Scenario: 模型可实例化
- **WHEN** 创建 `SkillStep(id="load_data", name="加载数据", description="加载用户数据集")`
- **THEN** 实例创建成功，默认值：depends_on=[], trust_level=t1, review_gate=False, retry_policy="skip"

#### Scenario: 模型可序列化
- **WHEN** 将 SkillStep 实例序列化为 dict
- **THEN** 输出包含所有字段及其值

### Requirement: SkillContract 模型定义
系统 SHALL 定义 `SkillContract` Pydantic 模型，包含：version（契约版本）、trust_ceiling（整体信任上限）、steps（步骤列表）、input_schema（输入 schema）、output_schema（输出 schema）、evidence_required（是否要求证据溯源）。

#### Scenario: 模型可实例化
- **WHEN** 创建包含两个 steps 的 SkillContract
- **THEN** 实例创建成功，默认值：version="1", trust_ceiling=t1, evidence_required=False

#### Scenario: 从 YAML dict 解析
- **WHEN** 将 YAML frontmatter 中的 contract 段解析为 dict 并传入 `SkillContract.model_validate()`
- **THEN** 得到有效的 SkillContract 实例

### Requirement: 步骤依赖关系验证
`SkillContract` SHALL 验证 steps 中的 depends_on 引用，所有被引用的步骤 ID MUST 存在于 steps 列表中。

#### Scenario: 合法依赖通过验证
- **WHEN** step B 的 depends_on 包含 step A 的 id，且 step A 存在于 steps 列表中
- **THEN** 模型验证通过

#### Scenario: 非法依赖拒绝创建
- **WHEN** step B 的 depends_on 包含不存在的步骤 ID
- **THEN** 模型验证抛出 ValidationError

### Requirement: 循环依赖检测
`SkillContract` SHALL 检测步骤间的循环依赖，存在循环时 MUST 拒绝创建。

#### Scenario: 循环依赖被拒绝
- **WHEN** step A depends_on step B，step B depends_on step A
- **THEN** 模型验证抛出 ValidationError，错误信息包含「循环依赖」

### Requirement: SkillStepEventData 事件模型
系统 SHALL 定义 `SkillStepEventData` Pydantic 模型，包含：skill_name、skill_version、step_id、step_name、status、trust_level、output_level、input_summary、output_summary、error_message、duration_ms。

#### Scenario: 事件可创建
- **WHEN** 创建 `SkillStepEventData(skill_name="exp-design", step_id="define_problem", step_name="问题定义", status="started")`
- **THEN** 实例创建成功

#### Scenario: 事件可序列化为 JSON
- **WHEN** 将 SkillStepEventData 实例序列化为 JSON
- **THEN** JSON 包含 skill_name、step_id、status 等字段

### Requirement: trust_ceiling 约束
SkillContract 的 trust_ceiling SHALL 约束所有 steps 的 trust_level，任何 step 的 trust_level 不得超过 contract 的 trust_ceiling。

#### Scenario: 步骤信任等级不超过上限
- **WHEN** contract trust_ceiling 为 t1，某 step trust_level 为 t2
- **THEN** 模型验证抛出 ValidationError
