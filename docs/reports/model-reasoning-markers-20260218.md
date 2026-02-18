# 多供应商“思考内容”标记调研与适配说明（2026-02-18）

## 调研结论（官方口径）

### 1) 阿里百炼 / Qwen 系列
- OpenAI 兼容 Chat API 在思考模式下会返回 `reasoning_content` 字段，正式回复仍在 `content`。
- 通过 `enable_thinking` 控制是否开启思考模式。
- Qwen3 开源模型在部分推理模式下会把思考过程放在 `<think>...</think>` 标签中。

### 2) Moonshot / Kimi 系列
- 官方说明已支持 OpenAI SDK 的 `reasoning_content` 读取方式。
- 官方示例强调流式时 `reasoning_content` 可能先于 `content` 到达。
- 官方建议多轮对话时不要回传历史 `reasoning_content`。

### 3) 智谱 / GLM 系列
- 官方文档已给出 `reasoning_content` 输出字段。
- 提供 `thinking.clear_thinking` 等开关控制历史思考链处理。

### 4) MiniMax 系列
- 官方文档说明 `reasoning_split=false` 时，思考与正文在 `content`（`<think>...</think>`）中。
- `reasoning_split=true` 时，思考在 `reasoning_details`，正文在 `content`。
- 官方流式示例显示需要处理“累计片段”（每个 chunk 是前缀全量），并建议做增量裁剪。

### 5) DeepSeek 系列
- 官方 API 文档定义了 `reasoning_content`（含流式 `delta.reasoning_content`）。
- 官方建议常规多轮对话仅保留 `content` 进入上下文，不回传历史 `reasoning_content`。

## 行业最佳实践（本次实现采用）

1. 统一输出契约
- 内部统一为：`text`（正式回复）+ `reasoning`（思考内容）+ `raw_text`（供应商原文）。

2. 解析优先级
- 优先解析结构化字段（`reasoning_content` / `reasoning_details`）。
- 仅在无结构化字段时，回退到标签解析（如 `<think>...</think>` / `◁think▷...◁/think▷`）。

3. 流式健壮性
- 同时兼容“增量流”与“累计流”，自动做增量去重。
- 支持跨 chunk 标签切分，避免 `<think>` 被截断时污染正文。

4. 函数调用上下文安全
- 展示层使用拆分后的 `text`/`reasoning`。
- 工具调用轮次保留 `raw_text`，避免供应商要求的原始 assistant 消息丢失。

5. 历史上下文最小化
- 常规多轮默认不将历史思考内容重新注入模型上下文，降低 token 开销与行为漂移风险。

## 主要参考（官方）
- Qwen 官方（Qwen3 Thinking）：https://github.com/QwenLM/Qwen3
- 阿里云百炼 OpenAI 兼容文档（含 `enable_thinking` / `reasoning_content`）：https://help.aliyun.com/zh/model-studio/openai-file-interface
- Moonshot 官方公告（`reasoning_content` 与流式说明）：https://platform.moonshot.cn/blog/posts/kimi-thinking
- 智谱 GLM API（`reasoning_content` / thinking 控制）：https://docs.bigmodel.cn/api-reference/
- MiniMax OpenAPI 文档（`reasoning_split` / `reasoning_details` / `<think>`）：https://platform.minimaxi.com/document/ChatCompletion%20V2
- DeepSeek API 文档（`reasoning_content`）：https://api-docs.deepseek.com/zh-cn/guides/reasoning_model
- vLLM reasoning parser（多模型推理标签解析实践）：https://docs.vllm.ai/en/latest/features/reasoning_outputs.html
- SGLang reasoning parser（含 `qwen3`、`deepseek-r1`、`kimi`）：https://docs.sglang.ai/advanced_features/structured_outputs_for_reasoning_models.html
