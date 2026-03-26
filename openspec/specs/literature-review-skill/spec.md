# Literature Review Skill Spec

## Purpose

定义 `literature-review` Markdown Skill 的行为规范，覆盖四步文献调研流程、证据溯源要求、离线降级路径以及输出等级约束，用于保证文献调研能力可发现、可验证且可审计。

## Requirements

### Requirement: literature-review Skill 文件
系统 SHALL 在 `.nini/skills/literature-review/SKILL.md` 提供文献调研引导 Skill，包含有效的 YAML frontmatter 和 contract 段。

#### Scenario: Skill 可被发现
- **WHEN** 运行 Skill 扫描
- **THEN** literature-review 出现在已注册 Skill 列表中

#### Scenario: contract 包含四步
- **WHEN** 解析 contract
- **THEN** 包含 search_papers、filter_papers、synthesize、generate_output 四个步骤

### Requirement: 证据溯源
Skill 的 contract SHALL 设置 evidence_required=true，生成的综合分析中每个关键结论 MUST 标注来源文献。

#### Scenario: 输出包含来源标注
- **WHEN** Skill 完成综合步骤
- **THEN** 输出中的每个关键结论附有文献引用（作者、年份、标题）

#### Scenario: 无来源的断言被标记
- **WHEN** LLM 生成无来源支撑的结论
- **THEN** 该结论被标注为「缺少文献支撑，需进一步检索验证」

### Requirement: 离线降级
当 NetworkPlugin 不可用时，search_papers 步骤 SHALL 自动切换为手动模式，引导用户上传 PDF 或提供文献列表。

#### Scenario: 离线时提示用户
- **WHEN** NetworkPlugin.is_available() 返回 False
- **THEN** Skill 输出明确提示「当前为离线模式，无法在线检索文献」，引导用户手动提供文献

#### Scenario: 用户提供文献后继续
- **WHEN** 用户上传 PDF 或提供引用列表
- **THEN** 后续步骤（筛选、综合、输出）基于用户提供的文献正常执行

### Requirement: 输出等级标注
Skill 的 trust_ceiling SHALL 为 T1，所有输出标注为 O2 草稿级。

#### Scenario: 综述输出包含等级标注
- **WHEN** Skill 生成文献综述
- **THEN** 输出包含「本综述为草稿级（O2），需人工审核后方可引用」声明
