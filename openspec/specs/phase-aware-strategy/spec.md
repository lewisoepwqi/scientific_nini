# Spec: phase-aware-strategy

## Purpose

定义 Nini 的阶段感知策略规范，包括通用输出等级标注、风险提示触发规则、降级行为规范，以及文献调研、实验设计、论文写作阶段的专项策略。

## Requirements

### Requirement: 通用策略——输出等级标注
strategy.md SHALL 定义输出等级标注规范（如 O1 建议级 / O2 草稿级 / O3 可审阅级 / O4 可导出级），适用于所有阶段的输出。

#### Scenario: 输出等级定义存在
- **WHEN** 读取 `data/prompt_components/strategy.md` 的通用策略部分
- **THEN** 包含输出等级标注规范，至少定义四个等级及其含义

#### Scenario: Agent 在非数据分析场景标注输出等级
- **WHEN** 用户请求文献综述或论文写作任务
- **THEN** Agent 的输出附带对应的等级标注（如「本综述为 O1 建议级，需人工审核后方可引用」）

### Requirement: 通用策略——风险提示触发规则
strategy.md SHALL 定义风险提示的触发条件，当 Agent 检测到超出当前能力成熟度或涉及高风险判断时，MUST 主动发出提示。

#### Scenario: 能力边界触发风险提示
- **WHEN** 用户请求的任务属于新阶段（文献调研、实验设计、论文写作）且涉及需要专业判断的操作
- **THEN** Agent 主动提示当前阶段能力为框架级引导，建议用户验证关键结论

### Requirement: 通用策略——降级行为规范
strategy.md SHALL 定义当所需工具或外部服务不可用时的降级行为规范，Agent MUST 明确告知用户降级事实而非静默降级。

#### Scenario: 工具不可用时的降级提示
- **WHEN** Agent 需要调用不存在的工具或不可用的外部服务
- **THEN** Agent 明确告知用户「当前无法执行 X，原因是 Y，建议替代方案 Z」，不静默忽略

### Requirement: 文献调研阶段策略
strategy.md SHALL 在现有内容之后追加文献调研阶段策略，包含检索 → 筛选 → 综合 → 输出的基本流程、证据溯源要求和离线降级提示。

#### Scenario: 文献调研策略内容完整
- **WHEN** 读取 `data/prompt_components/strategy.md`
- **THEN** 包含文献调研阶段策略，涵盖检索、筛选、综合、输出四个步骤

#### Scenario: 文献调研的离线降级
- **WHEN** 用户请求文献检索但网络插件不可用
- **THEN** Agent 明确提示「当前为离线模式，无法在线检索文献」，并建议用户手动提供文献或上传 PDF

#### Scenario: 文献调研的证据溯源
- **WHEN** Agent 提供文献相关的综合分析
- **THEN** 每个关键结论 SHALL 标注来源文献，不生成无来源的断言

### Requirement: 实验设计阶段策略
strategy.md SHALL 追加实验设计阶段策略，包含问题定义 → 设计选择 → 参数计算 → 方案生成的基本流程、伦理提示和人工复核提醒。

#### Scenario: 实验设计策略内容完整
- **WHEN** 读取 `data/prompt_components/strategy.md`
- **THEN** 包含实验设计阶段策略，涵盖问题定义、设计选择、参数计算、方案生成四个步骤

#### Scenario: 伦理提示触发
- **WHEN** 用户的实验设计涉及人体试验、动物实验或敏感数据
- **THEN** Agent 主动提示需通过伦理审查委员会（IRB/IACUC）审批

#### Scenario: 实验方案标注为草稿
- **WHEN** Agent 生成实验设计方案
- **THEN** 方案明确标注为「草稿级（O2），需专业人员审核」

### Requirement: 论文写作阶段策略
strategy.md SHALL 追加论文写作阶段策略，包含结构规划 → 分节撰写 → 修订 → 格式化的基本流程、引用规范和草稿级标注。

#### Scenario: 论文写作策略内容完整
- **WHEN** 读取 `data/prompt_components/strategy.md`
- **THEN** 包含论文写作阶段策略，涵盖结构规划、分节撰写、修订、格式化四个步骤

#### Scenario: 引用规范要求
- **WHEN** Agent 在论文写作过程中引用数据或文献
- **THEN** Agent 使用规范的引用格式，并提示用户确认引用准确性

#### Scenario: 写作输出标注等级
- **WHEN** Agent 生成论文段落或章节
- **THEN** 输出标注为「草稿级（O2）」，明确告知需作者审阅和修改

### Requirement: 现有数据分析策略完全保留
strategy.md 的现有内容（7 步标准分析流程、任务规划规范、沙箱说明、可视化决策树、绘图规范、报告生成决策）SHALL NOT 被修改或删除。新阶段策略 MUST 以追加方式添加在现有内容之后。

#### Scenario: 现有内容未被修改
- **WHEN** 对比升级前后的 `data/prompt_components/strategy.md`
- **THEN** 从第 1 行到现有内容结束的所有文字完全一致，无任何增删改

#### Scenario: 新增内容位置正确
- **WHEN** 读取升级后的 `data/prompt_components/strategy.md`
- **THEN** 新阶段策略出现在现有内容（报告生成决策部分）之后，以明确的分隔标记开头

### Requirement: 阶段策略条件触发
新阶段策略 SHALL 包含条件触发说明，明确标注「当用户任务属于 X 阶段时，参考以下策略」，避免 Agent 在数据分析场景中误用新阶段策略。

#### Scenario: 条件触发说明存在
- **WHEN** 读取策略文件中的每个新阶段策略段落
- **THEN** 段落开头包含明确的触发条件描述

#### Scenario: 数据分析场景不触发新策略
- **WHEN** 用户提交纯数据分析任务
- **THEN** Agent 遵循现有 7 步流程，不引用或混用文献调研/实验设计/论文写作策略
