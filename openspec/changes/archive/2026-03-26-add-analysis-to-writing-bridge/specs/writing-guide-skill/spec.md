## ADDED Requirements

### Requirement: writing-guide Skill 文件
系统 SHALL 在 `.nini/skills/writing-guide/SKILL.md` 提供论文写作引导 Skill，包含 contract 段。

#### Scenario: Skill 可被发现
- **WHEN** 运行 Skill 扫描
- **THEN** writing-guide 出现在已注册 Skill 列表中

#### Scenario: contract 包含四步
- **WHEN** 解析 contract
- **THEN** 包含 collect_materials、plan_structure、write_sections、review_revise 四个步骤

### Requirement: 素材收集步骤
collect_materials 步骤 SHALL 调用 collect_artifacts 工具，自动收集当前会话的分析产物。

#### Scenario: 有分析结果时收集成功
- **WHEN** 会话中已完成数据分析（有统计结果和图表）
- **THEN** 素材包包含统计结果摘要、图表列表、方法记录

#### Scenario: 无分析结果时输出空素材包
- **WHEN** 会话中没有分析产物
- **THEN** 素材包为空，后续步骤切换为纯引导模式

### Requirement: 分节撰写引导
write_sections 步骤 SHALL 逐章节引导用户撰写，嵌入来自素材包的统计结果和图表引用。

#### Scenario: 统计结果嵌入
- **WHEN** 素材包包含 t 检验结果
- **THEN** 写作引导中在适当章节（Results）预填统计描述模板

#### Scenario: 图表引用嵌入
- **WHEN** 素材包包含图表
- **THEN** 写作引导中包含「见图 X」引用占位符

### Requirement: 输出等级标注
Skill 的 trust_ceiling SHALL 为 T1，所有输出标注为 O2 草稿级。

#### Scenario: 写作输出包含等级标注
- **WHEN** Skill 生成论文章节
- **THEN** 输出包含 O2 等级标注和「需作者审阅和修改」声明
