## ADDED Requirements

### Requirement: Markdown 技能脚手架默认内容可执行
系统 MUST 在执行 `nini skills create --type markdown` 时生成可直接编辑的技能模板，避免输出泛化 TODO 占位内容。

#### Scenario: 生成模板时包含结构化章节
- **WHEN** 用户创建 Markdown 技能脚手架
- **THEN** 生成文件包含 `适用场景`、`步骤`、`注意事项` 三个章节
- **AND** 每个章节包含可执行的填写指引文本

#### Scenario: 生成模板时不包含 TODO 占位
- **WHEN** 用户查看新生成的 `SKILL.md`
- **THEN** 文件内容不包含 `TODO` 关键词
- **AND** frontmatter 中 `name`、`description`、`category` 与输入参数一致
