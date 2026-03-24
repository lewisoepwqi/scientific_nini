## ADDED Requirements

### Requirement: 问题对象支持 question_type 字段
`ask_user_question` 的单个问题对象 SHALL 支持可选的 `question_type` 字段，枚举值为：`missing_info`、`ambiguous_requirement`、`approach_choice`、`risk_confirmation`、`suggestion`。该字段为纯可选，后端不填充默认值，前端对缺少或未知值一律以默认样式降级渲染，不报错。

#### Scenario: LLM 传入合法 question_type
- **WHEN** LLM 调用 `ask_user_question` 时问题对象包含合法的 `question_type` 值
- **THEN** 该值被透传到 WebSocket `ask_user_question` 事件的问题对象中
- **THEN** 前端根据该类型渲染对应样式

#### Scenario: 缺少 question_type 时降级处理
- **WHEN** 问题对象不包含 `question_type` 字段
- **THEN** 前端以默认样式渲染该问题，不报错、不丢弃问题

#### Scenario: LLM 传入未知 question_type 值
- **WHEN** 问题对象的 `question_type` 值不在枚举范围内
- **THEN** 前端以默认样式渲染，不报错

### Requirement: 问题对象支持 context 字段
`ask_user_question` 的单个问题对象 SHALL 支持可选的 `context` 字符串字段，用于提供背景说明。前端 SHALL 在问题文本上方或以辅助文字形式展示 `context` 内容（如存在）。

#### Scenario: 存在 context 字段时展示背景说明
- **WHEN** 问题对象包含非空的 `context` 字段
- **THEN** 前端在问题文本附近展示该背景说明文字

#### Scenario: 缺少 context 字段时不影响显示
- **WHEN** 问题对象不包含 `context` 字段
- **THEN** 前端正常显示问题，不留空白占位

### Requirement: 前端根据 question_type 渲染差异化样式
前端 `AskUserQuestionCard` 组件 SHALL 根据 `question_type` 应用不同的视觉样式：
- `risk_confirmation`：红色/警告色边框 + 警告图标
- `approach_choice` / `ambiguous_requirement`：蓝色强调选项按钮组
- `missing_info` / `suggestion` / 无类型：默认样式

#### Scenario: risk_confirmation 显示警告样式
- **WHEN** 问题的 `question_type` 为 `risk_confirmation`
- **THEN** 前端以红色/警告色边框渲染该问题卡片
- **THEN** 卡片展示警告图标

#### Scenario: approach_choice 强调选项
- **WHEN** 问题的 `question_type` 为 `approach_choice` 或 `ambiguous_requirement`
- **THEN** 前端以蓝色强调样式渲染选项按钮

### Requirement: System Prompt 包含 question_type 使用说明
`agent/prompts/builder.py` 生成的 system prompt 中关于 `ask_user_question` 的说明 SHALL 包含各 `question_type` 枚举值的名称及其适用场景描述。

#### Scenario: system prompt 包含所有枚举值的说明
- **WHEN** `builder.py` 构建系统提示文本
- **THEN** 输出文本中包含 `missing_info`、`ambiguous_requirement`、`approach_choice`、`risk_confirmation`、`suggestion` 这 5 个枚举值的名称
- **THEN** 每个枚举值附有至少一句适用场景描述
