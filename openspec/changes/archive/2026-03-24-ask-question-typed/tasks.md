## 1. 后端协议扩展

- [x] 1.1 在 `src/nini/models/event_schemas.py` 的问题对象 schema 中增加可选字段 `question_type`（枚举，5 种值）和 `context`（字符串）

## 2. System Prompt 更新

- [x] 2.1 在 `src/nini/agent/prompts/builder.py` 的 `ask_user_question` 使用说明中补充 `question_type` 枚举说明：
  - `missing_info`：缺少必要信息（文件路径、参数等）
  - `ambiguous_requirement`：需求存在多种合理解释
  - `approach_choice`：存在多种有效实现方案需用户选择
  - `risk_confirmation`：即将执行破坏性/不可逆操作
  - `suggestion`：有推荐方案但需用户确认
- [x] 2.2 在 system prompt 中补充 `context` 字段的使用说明（说明提问背景时填写）

## 3. 前端样式扩展

- [x] 3.1 找到 `web/src/` 中的 `AskUserQuestionCard`（或等效组件），确认其接收问题对象的数据结构
- [x] 3.2 根据 `question_type` 增加条件样式：
  - `risk_confirmation` → 红色/警告色边框 + 警告图标
  - `approach_choice` / `ambiguous_requirement` → 蓝色强调选项按钮
  - 其余或无类型 → 默认样式（不改动）
- [x] 3.3 若问题对象包含 `context`，在问题文本上方渲染辅助说明文字
- [x] 3.4 验证：缺少 `question_type` / `context` 时组件正常渲染无报错

## 4. 记忆上传路径过滤

- [x] 4.1 在 `src/nini/memory/compression.py` 中找到生成记忆摘要的写入点
- [x] 4.2 实现 `_strip_upload_mentions(text: str) -> str`：正则过滤含 `upload`/`上传` 关键词的整句
- [x] 4.3 在摘要写入前调用该函数，不修改原始 `memory.jsonl` 内容

## 5. 测试与验收

- [x] 5.1 手动测试：LLM 主动调用 `ask_user_question` 并传入 `risk_confirmation`，确认前端显示红色警告样式
- [x] 5.2 手动测试：不传 `question_type` 的旧格式调用，确认前端正常降级显示
- [x] 5.3 为 `_strip_upload_mentions` 写单元测试：含上传关键词的句子被过滤，不含的句子不受影响
- [x] 5.4 运行 `pytest -q` 确认全量测试无回归
- [x] 5.5 运行 `black --check src tests` 格式检查通过
