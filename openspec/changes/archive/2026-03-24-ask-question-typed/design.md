## Context

`ask_user_question` 在 nini 中是一个"伪工具"（pseudo-tool）：它不注册到 `ToolRegistry`，没有暴露给 LLM 的 JSON Schema，而是通过 system prompt 描述告知 LLM 如何使用，并由 `runner.py` 在工具调用循环中特殊处理（`if func_name == "ask_user_question"`）。它承担了 4 个触发场景：意图预分析澄清、LLM 主动调用、confirmation_fallback、高风险操作确认。

当前问题对象结构：
```json
{ "id": "q1", "text": "请选择图表格式", "options": ["交互式", "静态图片"] }
```

对比 deer-flow 的 `ask_clarification` 工具，其 `clarification_type` 枚举和 `context` 字段使前端能够差异化渲染，LLM 也能更精准地描述提问意图。

长期记忆问题：`memory/compression.py` 在压缩会话历史时，会将用户上传文件的路径（如 `data/sessions/{id}/workspace/xxx.csv`）摘要进长期记忆，下次会话时 Agent 看到该路径后可能尝试访问——但该文件可能已不存在（用户重新上传了不同文件，或会话数据已清理）。

## Goals / Non-Goals

**Goals:**
- 为 `ask_user_question` 协议增加 `question_type` 和 `context` 可选字段
- 更新 system prompt 使 LLM 在主动调用时能正确传入类型
- 前端根据类型渲染差异化 UI
- 防止上传文件路径污染长期记忆

**Non-Goals:**
- 不将 `ask_user_question` 改为正式注册的 Tool（伪工具机制暂时维持，改动过大）
- 不强制要求所有已有的 4 种触发场景传入 `question_type`（向后兼容，字段可选）
- 不引入新的问答 UI 组件（在现有 `AskUserQuestionCard` 基础上扩展样式）

## Decisions

### 决策 1：`question_type` 作为可选字段，不做强制校验
4 种触发场景中，意图预分析澄清和 confirmation_fallback 是系统自动触发的，修改它们的调用点成本较高。将字段设为可选，仅更新 system prompt 引导 LLM 主动调用时填写，其他场景按需逐步补充。前端缺少类型时降级为默认样式。

### 决策 2：枚举值与 deer-flow 对齐
使用与 deer-flow `clarification_tool.py` 相同的 5 个枚举值：`missing_info`、`ambiguous_requirement`、`approach_choice`、`risk_confirmation`、`suggestion`。保持语义一致，便于日后文档和对比理解。

### 决策 3：上传路径过滤用正则，不用路径解析
过滤逻辑针对的是"提及文件上传"的句子，不是对路径字符串做精确匹配（路径格式可能多样）。用正则匹配包含 `upload`/`上传` 关键词的句子并整句移除，与 deer-flow 的 `_strip_upload_mentions_from_memory` 思路一致。

### 决策 4：前端差异化渲染只改样式，不改交互逻辑
`risk_confirmation` → 红色边框 + 警告图标；`approach_choice`/`ambiguous_requirement` → 蓝色强调选项按钮；其余类型 → 默认样式。选项的选择和提交逻辑不变。

## Risks / Trade-offs

- **[风险] LLM 不遵循 question_type 枚举** → 缓解：前端对未知 type 值降级为默认样式，不报错
- **[风险] 正则误过滤** → 缓解：仅过滤含 upload/上传 的整句，保守设计；过滤仅影响记忆摘要，不影响原始会话历史
- **[权衡] 两个独立功能打包进同一 change** → 两者都是"可选字段 + 无破坏性"的小改动，单独建 change 过于碎片；如果上传过滤实现复杂可拆出，但预计不超过 20 行

## Migration Plan

- 所有字段为可选，全量兼容。前端 + 后端可独立部署，无需同步上线。
- 回滚：移除前端样式分支和 system prompt 新增内容，恢复为无类型模式。

## Open Questions

（无）
