## ADDED Requirements

### Requirement: 配置级用途路由 fallback

系统 SHALL 维护一张 `dict[str, str]` 形式的配置级用途 fallback 映射 `PURPOSE_ROUTE_FALLBACKS`，键为待解析 purpose、值为替代 purpose。当某 purpose **未配置任何 `purpose_*_provider` / `purpose_*_model` / `purpose_*_base_url`** 时，`_get_effective_purpose_route(purpose)` SHALL 按映射查找替代 purpose 的路由配置。映射至少 SHALL 覆盖：

- `analysis → chat`
- `planning → chat`
- `verification → chat`
- `fast → chat`
- `deep_reasoning → planning`
- **`title_generation → chat`**（本次新增）
- **`image_analysis → chat`**（本次新增）

本 fallback 仅作用于"配置查找"层，与运行时调用失败无关。任何添加、修改或删除条目的变更 MUST 同步更新本 spec 与相关单测。

#### Scenario: title_generation 未配置时沿用 chat 配置

- **WHEN** 用户未配置 `purpose_title_generation_*` 任何字段
- **AND** 配置了 `purpose_chat_provider="deepseek"`
- **THEN** `_get_effective_purpose_route("title_generation")` 返回 deepseek 的路由配置

#### Scenario: image_analysis 未配置时沿用 chat 配置

- **WHEN** 用户未配置 `purpose_image_analysis_*` 任何字段
- **AND** 配置了 `purpose_chat_provider="zhipu"`
- **THEN** `_get_effective_purpose_route("image_analysis")` 返回 zhipu 的路由配置

---

### Requirement: BUILTIN 调用失败降级到激活 provider

当 `_resolve_client_plan(purpose)` 解析得到的候选 client 列表来自 BUILTIN 分支（即 `route_provider == BUILTIN_PROVIDER_ID` 或落入 BUILTIN-fast 默认路径）且当前存在用户激活 provider 时，候选列表 SHALL 在 BUILTIN client 之后追加该激活 provider 的 client，使得 BUILTIN 调用失败时按照"错误分类"规则可降级到激活 provider。

激活 provider client 在追加前 SHOULD 通过其 `pick_model_for_purpose(purpose)` 决定使用哪个模型；该接口返回 `None` 时使用主模型。

本降级 MUST NOT 改变 BUILTIN quota 计数语义：`builtin_mode_to_count` 在调用前已确定，与是否触发后续降级无关。

#### Scenario: BUILTIN 单 client 失败时降级到激活 provider

- **WHEN** 用户配置了激活 provider（如 dashscope 主 key）
- **AND** 标题路由经 BUILTIN 分支得到 builtin_client（使用 `qwen3-coder-plus` + builtin key）
- **AND** builtin_client 调用返回 401（builtin key 失效）
- **THEN** resolver 按候选列表顺序尝试激活 dashscope client
- **AND** 若激活 client 成功，整次调用返回其结果

#### Scenario: 无激活 provider 时不追加

- **WHEN** 当前无激活 provider（试用模式）
- **AND** 标题路由解析得到 BUILTIN 单 client
- **THEN** 候选列表保持单元素，不做追加
- **AND** BUILTIN 失败按 `optional` 决定是抛错还是返回 None

#### Scenario: 激活 client 与 BUILTIN client 引用同一对象时不重复追加

- **WHEN** BUILTIN 分支返回的 client 恰好是激活 client 本身
- **THEN** 候选列表不重复追加，保持单元素

---

### Requirement: 错误分类按"是否跨 provider 降级"单维表达

系统 SHALL 将 LLM 调用错误的处理用单一维度 `try_next_provider: bool` 表达：是否在失败后尝试候选列表中下一个 provider 的 client。每种已识别错误类型的取值 MUST 符合下表：

| 错误类型 | try_next_provider |
|---|---|
| AuthError / HTTP 401 / HTTP 403 | true |
| HTTP 400（请求参数无效） | false |
| RateLimit / HTTP 429 | true |
| Timeout | true |
| ConnectError | true |
| HTTP 503 | true |
| 其它 APIError 与未识别异常 | true |

`message`、`log_level` 字段保留不变。本次 SHALL NOT 引入"同 client 重试"维度（如 `retry_same_client`）作为预留位；待限流退避或同 client 重试策略真正落地时再加。

#### Scenario: 401 鉴权错跨 provider 降级

- **WHEN** 候选 client 列表为 `[A, B]`，A 调用返回 HTTP 401
- **THEN** resolver 立即尝试 B
- **AND** 若 B 成功，整次调用返回 B 的结果

#### Scenario: 400 请求错误不跨 provider 降级

- **WHEN** 候选 client 列表为 `[A, B]`，A 调用返回 HTTP 400
- **THEN** resolver MUST NOT 尝试 B
- **AND** 整次调用直接抛出错误（或在 `optional=True` 时返回 None）

#### Scenario: 单 client 配置下鉴权错的兜底

- **WHEN** 候选列表只有单个 client，调用返回 401
- **AND** 调用方传入 `optional=False`（默认）
- **THEN** resolver 抛出包含"API Key 无效或已过期，请检查配置"的错误，与本变更前的用户提示保持一致

---

### Requirement: 非致命用途的可选失败语义

`model_resolver.chat_complete()` 方法 SHALL 提供 `optional: bool = False` 参数。当 `optional=True` 且全部候选 client（含 BUILTIN→激活降级链）均失败时，方法 SHALL 返回 `None` 而非抛出异常。

`optional=True` 的语义边界：

- 仅作用于"全链最终失败"这一个时机；
- 中间任何一个 client 失败仍按错误分类逐家降级，并记 warning 日志；
- `chat_complete` 之外的接口（如流式 `chat()`）不受影响，签名与行为保持原样。

#### Scenario: optional 调用全失败返回 None

- **WHEN** 标题生成调用 `chat_complete(..., optional=True)`，候选链所有 client 全部失败
- **THEN** 方法返回 `None`
- **AND** 不抛出异常
- **AND** 在日志中记录 `WARNING` 级别条目，包含失败的 provider/model/原因

#### Scenario: 默认调用全失败抛异常

- **WHEN** 调用 `chat_complete(...)`（未传 `optional` 或传 `optional=False`），候选链全失败
- **THEN** 方法抛出 `RuntimeError`，错误信息包含 fallback chain 摘要
- **AND** 行为与本变更前一致

---

### Requirement: 模型选择由 provider 自管

系统 SHALL 通过 `BaseLLMClient.pick_model_for_purpose(purpose: str) -> str | None` 接口让每个 provider 自主决定特定用途下使用哪个模型。默认实现返回 `None`，表示沿用主模型。

各 provider 子类 SHOULD 在确有偏好时覆写该方法。`title_generation` 用途下的偏好顺序 MUST 与 `simplified-model-config` 规格中"标题生成自动使用廉价模型"列表保持一致：

- `deepseek`: `["deepseek-chat"]`
- `zhipu`: `["glm-4-flash", "glm-4-air", "glm-4"]`
- `dashscope`: `["qwen-turbo", "qwen-plus"]`
- `ollama`: 不覆写（`return None`，使用主模型）
- 其它非简化配置范围内的 provider（OpenAI / Anthropic / Moonshot / MiniMax）: 沿用现有 `TITLE_MODEL_MATCHERS` 中的关键词偏好，搬入对应类即可

`model_resolver` 模块内 SHALL 不再保留 `TITLE_MODEL_MATCHERS` 字典与 `_select_title_model_from_available` 函数；`if purpose == "title_generation"` 的特殊分支 SHOULD 收敛到路由解析必要范围（不再用于模型选择）。

#### Scenario: provider 提供了偏好则使用偏好模型

- **WHEN** 触发 `purpose="title_generation"` 调用，激活 provider 为 dashscope
- **AND** dashscope 当前可用模型列表包含 `qwen-turbo`
- **THEN** resolver 通过 `dashscope_client.pick_model_for_purpose("title_generation")` 得到 `"qwen-turbo"`
- **AND** 实际请求使用 `qwen-turbo` 而非主模型

#### Scenario: provider 未覆写则使用主模型

- **WHEN** 触发 `purpose="title_generation"` 调用，激活 provider 为 ollama
- **THEN** `ollama_client.pick_model_for_purpose("title_generation")` 返回 `None`
- **AND** 实际请求使用用户在 UI 中选择的主模型

#### Scenario: 偏好模型在可用列表中缺失则使用主模型

- **WHEN** 触发 `purpose="title_generation"` 调用，provider 偏好列表中的模型均不在当前可用列表
- **THEN** `pick_model_for_purpose` 返回 `None`
- **AND** 实际请求使用主模型

---

### Requirement: 标题生成器只承担 prompt 与规则兜底

`title_generator.generate_title` 函数 SHALL 仅负责：

1. 从会话消息提取相关内容并构造 prompt；
2. 调用 `chat_complete(..., purpose="title_generation", optional=True)` 一次（不在函数内部做多策略 LLM 重试）；
3. 当 LLM 调用返回 `None` 或文本为空时，调用 `_fallback_title` 基于用户消息规则化生成标题；
4. 对 LLM 与规则兜底的输出做长度/前缀/格式规范化。

`generate_title` MUST NOT 包含：

- 显式的 `try ... except Exception` 用于吞噬 LLM 调用异常（由 `optional=True` 接管）；
- 多种 prompt 策略的 LLM 重试循环（如原 `length_retry` 的多次 LLM 调用）。

调用方 `_auto_generate_title` 等顶层 wrapper 可保留通用的 `try ... except Exception` 作为防御性兜底（防异步任务静默死亡），但不应再为 LLM 故障写专门处理。

#### Scenario: LLM 成功生成标题

- **WHEN** `chat_complete` 返回有效文本
- **THEN** `generate_title` 规范化后返回该标题
- **AND** 不调用 `_fallback_title`

#### Scenario: LLM 全链失败时走规则兜底

- **WHEN** `chat_complete(optional=True)` 返回 `None`
- **THEN** `generate_title` 调用 `_fallback_title(messages)` 并返回结果
- **AND** 在日志中记录降级路径

#### Scenario: LLM 返回空文本时走规则兜底

- **WHEN** `chat_complete` 返回 `LLMResponse` 但 `text` 为空字符串
- **THEN** `generate_title` 同样调用 `_fallback_title` 并返回结果

#### Scenario: generate_title 不直接抛 LLM 故障异常

- **WHEN** LLM 全链失败
- **THEN** `generate_title` 返回字符串或 None，**不抛**与 LLM 故障相关的异常
