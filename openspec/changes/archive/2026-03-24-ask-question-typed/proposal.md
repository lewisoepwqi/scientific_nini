## Why

`ask_user_question` 是 nini 向用户发起交互提问的唯一机制，目前的问题对象只有 `text` 和 `options` 字段，没有类型区分。前端无法根据问题的性质渲染差异化 UI（例如风险确认应显示警告样式、方案选择应突出选项按钮），LLM 也缺乏结构化的语义约束导致使用该工具时表述不够精准。同时，长期记忆中存在会话级临时文件路径被持久化的问题，下次会话时 Agent 可能尝试访问已不存在的上传文件。

## What Changes

- 在 `ask_user_question` 的问题对象中增加两个可选字段：
  - `question_type`：枚举类型，5 种值（`missing_info` / `ambiguous_requirement` / `approach_choice` / `risk_confirmation` / `suggestion`）
  - `context`：字符串，可选背景说明
- 更新 system prompt 的 `ask_user_question` 使用说明，描述各 `question_type` 的适用场景
- 前端 `AskUserQuestionCard` 组件根据 `question_type` 渲染差异化样式
- 在 `memory/compression.py` 的记忆更新路径中，用正则过滤掉提及上传文件路径的句子，防止临时路径进入长期记忆

## Capabilities

### New Capabilities

- `ask-question-typed`：`ask_user_question` 问题类型化协议（`question_type` + `context` 字段）
- `memory-upload-sanitize`：记忆压缩时自动过滤上传文件路径提及

### Modified Capabilities

（无现有规格变更）

## Impact

- **修改文件**：
  - `src/nini/models/event_schemas.py`（问题对象增加字段）
  - `src/nini/agent/prompts/builder.py`（system prompt 补充使用说明）
  - `src/nini/memory/compression.py`（增加上传路径过滤）
  - `web/src/` 中的 `AskUserQuestionCard` 或等效前端组件
- **纯增量变更**：所有新字段均为可选，现有 4 种触发场景（意图澄清、LLM 主动调用、confirmation_fallback、高风险确认）不受影响
- **无 API 协议变更**：WebSocket 事件结构向后兼容，前端忽略未知字段降级展示
- **无新依赖**：正则过滤仅用标准库 `re`
