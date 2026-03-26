## ADDED Requirements

### Requirement: experiment-design-helper Skill 文件
系统 SHALL 在 `.nini/skills/experiment-design-helper/SKILL.md` 提供实验设计引导 Skill，包含有效的 YAML frontmatter（name、description、category、allowed-tools、contract）和工作流正文。

#### Scenario: Skill 可被 markdown_scanner 发现
- **WHEN** 运行 Skill 扫描
- **THEN** experiment-design-helper 出现在已注册 Skill 列表中

#### Scenario: Skill contract 可解析
- **WHEN** 解析 experiment-design-helper 的 frontmatter
- **THEN** metadata["contract"] 为有效的 SkillContract 实例，包含 4 个步骤

### Requirement: 四步工作流覆盖
Skill 的 contract SHALL 包含四个步骤：问题定义（define_problem）、设计选择（choose_design）、参数计算（calculate_params）、方案生成（generate_plan），按线性依赖排列。

#### Scenario: 步骤顺序正确
- **WHEN** 解析 contract 的 steps
- **THEN** 拓扑排序结果为 define_problem → choose_design → calculate_params → generate_plan

#### Scenario: 方案生成步骤有 review_gate
- **WHEN** 读取 generate_plan 步骤
- **THEN** review_gate 为 True

### Requirement: trust_ceiling 为 T1
Skill 的 contract trust_ceiling SHALL 为 T1（草稿级），所有步骤的输出等级不超过 O2。

#### Scenario: 信任上限限制
- **WHEN** 解析 contract 的 trust_ceiling
- **THEN** 值为 t1

### Requirement: sample_size 工具
系统 SHALL 提供 `sample_size` 工具，支持两组均值比较、多组比较、比例差异三种设计类型的样本量计算。

#### Scenario: 两组 t 检验样本量计算
- **WHEN** 调用 sample_size(design_type="two_sample_ttest", effect_size=0.5, alpha=0.05, power=0.8)
- **THEN** 返回每组所需样本量（约 64）

#### Scenario: ANOVA 样本量计算
- **WHEN** 调用 sample_size(design_type="anova", effect_size=0.25, alpha=0.05, power=0.8, groups=3)
- **THEN** 返回每组所需样本量

#### Scenario: 参数缺失时返回错误
- **WHEN** 调用 sample_size 未提供 effect_size
- **THEN** 返回 ToolResult 包含参数缺失错误信息

### Requirement: 工具注册
`sample_size` 工具 SHALL 在 `tools/registry.py` 的 `create_default_tool_registry()` 中注册。

#### Scenario: 工具可通过 registry 调用
- **WHEN** 从 ToolRegistry 中查询 "sample_size"
- **THEN** 返回对应的 Tool 实例

### Requirement: 伦理提示
当 Skill 检测到实验涉及人体试验或动物实验相关关键词时，SHALL 在方案中包含伦理审查提示。

#### Scenario: 人体试验触发伦理提示
- **WHEN** 用户输入包含「临床试验」「人体」「患者」等关键词
- **THEN** 生成的方案包含「需通过 IRB/伦理审查委员会审批」提示

### Requirement: 输出标注
Skill 的所有输出 SHALL 标注为 O2 草稿级，并在方案末尾包含「本方案为草稿级（O2），需专业人员审核后方可实施」声明。

#### Scenario: 输出包含等级标注
- **WHEN** Skill 生成实验方案
- **THEN** 方案包含 O2 等级标注和审核声明
