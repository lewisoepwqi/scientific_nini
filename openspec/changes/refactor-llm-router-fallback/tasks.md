## 1. 基线盘点（T0）

- [ ] 1.1 全仓 grep `should_fallback`，输出引用矩阵（生产代码 + 测试），存入本任务文件末尾的 `## 引用矩阵` 区
- [ ] 1.2 全仓 grep `_classify_llm_error`、`_LLMErrorDisposition`、`PURPOSE_ROUTE_FALLBACKS`，输出引用矩阵
- [ ] 1.3 全仓 grep `purpose == "title_generation"` 与 `TITLE_MODEL_MATCHERS`、`_get_title_client`、`_select_title_model_from_available`、`_should_use_builtin_fast_for_trial_title`，输出引用矩阵
- [ ] 1.4 全仓 grep `title_generator`、`generate_title`，输出调用方矩阵（重点确认 `web/`、`tests/`、`scripts/` 是否有引用）
- [ ] 1.5 跑基线：`pytest -q`、`python scripts/check_event_schema_consistency.py`、`mypy src/nini`、`black --check src tests`，记录绿/红状态与失败用例（如有）
- [ ] 1.6 列出与本次改动相关的现有测试文件，统计测试用例数；当前已知至少包含：`tests/test_phase5_model_resolver.py`、`tests/test_model_resolver_trial_policy.py`、`tests/test_title_generator.py`
- [ ] 1.7 关键事实核验：阅读 `_resolve_client_plan` BUILTIN 分支（`model_resolver.py:691-713`），确认 `builtin_mode_to_count` 在调用前就已确定（即 quota 计数语义为"提交即计数"，与后续是否降级无关）。若现状不符则在本任务中提 alert，T2 设计需相应调整

## 2. 配置级 fallback 表补全（T1，独立 PR：feat/llm-router-purpose-fallback-table）

- [ ] 2.1 在 `src/nini/agent/model_resolver.py:144` 的 `PURPOSE_ROUTE_FALLBACKS` 表新增条目：
  - [ ] 2.1.1 `"title_generation": "chat"`
  - [ ] 2.1.2 `"image_analysis": "chat"`
- [ ] 2.2 新增/补充测试（沿用现有 `tests/test_phase5_model_resolver.py` 文件追加，或新建 `tests/test_model_resolver_purpose_fallback.py`）：
  - [ ] 2.2.1 用例：未配置 `purpose_title_generation_*` 时，`_get_effective_purpose_route("title_generation")` 解析到 `chat` 路由
  - [ ] 2.2.2 用例：未配置 `purpose_image_analysis_*` 时同理降级到 `chat`
- [ ] 2.3 跑 `pytest tests/test_phase5_model_resolver.py tests/test_model_resolver_*.py -q`、`mypy src/nini`、`black --check src tests`
- [ ] 2.4 提交 PR；commit 信息：`feat(agent): 补全 PURPOSE_ROUTE_FALLBACKS 中 title_generation/image_analysis 配置级降级`
- [ ] 2.5 PR 描述明确说明：本任务是配置级 fallback 补漏，**不直接修复 BUILTIN key 失效的当下 bug**，bug 修复见 T2+T3

## 3. BUILTIN 调用降级到激活 provider（T2，独立 PR：feat/llm-router-builtin-active-fallback，修复当下 bug 关键之一）

- [ ] 3.1 阅读 `_resolve_client_plan` 全部分支（`model_resolver.py:679-770`），确认 BUILTIN 分支在 `clients = [builtin_client]` 之后是否还有逻辑会改写 `clients`
- [ ] 3.2 确认 T0 任务 1.7 的 quota 计数语义结论：`builtin_mode_to_count` 必须是"提交即计数"才能安全追加 fallback；若不是则需先调整或暂停本任务
- [ ] 3.3 修改 `_resolve_client_plan` BUILTIN 分支：在 `if not clients: raise ...` 之后、return 之前追加：
  ```python
  active = self._get_single_active_client()
  if active is not None and not any(c is active for c in clients):
      preferred_model = active.pick_model_for_purpose(purpose)  # 见 T6
      if preferred_model and preferred_model != active.get_model_name():
          built = self._build_client_for_provider(active.provider_id, model=preferred_model)
          if built and built.is_available():
              active = built
      clients.append(active)
  ```
  注：`pick_model_for_purpose` 是 T6 引入的接口；本任务可先用 `getattr(active, "pick_model_for_purpose", lambda _: None)(purpose)` 兼容写法，T6 合并后清理
- [ ] 3.4 同理处理 `_resolve_client_plan` 中 line 734 `else` 分支（无 route_provider 但走 BUILTIN-fast）：在 `clients = [builtin_client]` 后做相同追加
- [ ] 3.5 新增测试 `tests/test_model_resolver_builtin_fallback.py`：
  - [ ] 3.5.1 用例：BUILTIN 分支 + 存在激活 provider → `_resolve_client_plan` 返回的 clients 列表长度为 2，第二个为激活 client
  - [ ] 3.5.2 用例：BUILTIN 分支 + 无激活 provider（试用模式）→ clients 列表长度为 1
  - [ ] 3.5.3 用例：BUILTIN client 与激活 client 是同一对象 → 不重复追加
  - [ ] 3.5.4 用例：BUILTIN client 调用失败 + 激活 client 成功（与 T3 配合后才能完整验证；本任务先 mock `chat()` 内部跳过错误分类，断言激活 client 被调用）
- [ ] 3.6 跑 `pytest -q`、`mypy src/nini`、`black --check src tests`
- [ ] 3.7 提交 PR；commit 信息：`feat(agent): BUILTIN 调用失败时降级到用户激活 provider`

## 4. 错误分类单维化（T3，独立 PR：refactor/llm-error-disposition-rename，修复当下 bug 关键之一）

- [ ] 4.1 修改 `_LLMErrorDisposition` 数据类（`model_resolver.py:153-159`）：
  - [ ] 4.1.1 字段 `should_fallback: bool` 重命名为 `try_next_provider: bool`
  - [ ] 4.1.2 保留 `message`、`log_level` 字段不变
  - [ ] 4.1.3 **不引入** `retry_same_client` 等任何预留字段
- [ ] 4.2 重写 `_classify_llm_error`（`model_resolver.py:621-677`）按 spec 表填充新字段：
  - [ ] 4.2.1 AuthError / 401 / 403 → `try_next_provider=True`，message 保留"API Key 无效或已过期，请检查配置"
  - [ ] 4.2.2 400 → `try_next_provider=False`
  - [ ] 4.2.3 RateLimit / 429 → `try_next_provider=True`
  - [ ] 4.2.4 Timeout / ConnectError / 503 → `try_next_provider=True`
  - [ ] 4.2.5 其它 APIError 与未识别异常 → `try_next_provider=True`
- [ ] 4.3 修改 `chat()` 调用方（`model_resolver.py:902-944` 区域）：
  - [ ] 4.3.1 把 `if not disposition.should_fallback: raise` 替换为 `if not disposition.try_next_provider: raise`
  - [ ] 4.3.2 同步更新日志格式串中关于 fallback 的描述为"跨 provider 降级"
- [ ] 4.4 同步更新 `chat_complete` 内对 disposition 的使用（如有引用）
- [ ] 4.5 全仓 grep 确认 `should_fallback` 无残留命中（除 OpenSpec 历史 changes 与本 spec 文件）
- [ ] 4.6 更新现有测试断言（按 1.1 引用矩阵逐个修正字段名）
- [ ] 4.7 新增测试（追加到 `tests/test_phase5_model_resolver.py` 或新建 `tests/test_model_resolver_error_disposition.py`）：
  - [ ] 4.7.1 用例：401 错误下 `[A, B]` 候选，A 失败后断言 B 被尝试
  - [ ] 4.7.2 用例：400 错误下 `[A, B]` 候选，A 失败后断言 B 不被尝试，错误冒泡
  - [ ] 4.7.3 用例：429 错误下跨 provider 降级行为
  - [ ] 4.7.4 用例：单 provider + 401 + `optional=False` 仍按"API Key 无效"友好提示抛错
  - [ ] 4.7.5 用例（与 T2 配合的回归）：BUILTIN client + 激活 client 候选列表，BUILTIN 返回 401 → 激活 client 成功 → 整次调用返回成功
- [ ] 4.8 跑 `pytest -q`、`mypy src/nini`、`black --check src tests`
- [ ] 4.9 提交 PR；commit 信息：`refactor(agent): 错误分类单维化为 try_next_provider 字段`
- [ ] 4.10 **里程碑确认**：T2 + T3 合并后做一次手测（按 7.3）确认用户报的 bug 已消除；若未消除则诊断剩余原因，可能需要回到 design 阶段重审

## 5. chat_complete 增加 optional 参数（T4，独立 PR：feat/llm-chat-complete-optional）

- [ ] 5.1 修改 `model_resolver.chat_complete` 签名增加 `optional: bool = False`，返回类型改为 `LLMResponse | None`
- [ ] 5.2 在内部 try/except 包裹的最外层增加：当全链失败且 `optional=True` 时返回 `None` 并记 WARNING 日志
- [ ] 5.3 当 `optional=False`（默认）时维持原行为：抛出 `RuntimeError`，错误信息含 fallback chain 摘要
- [ ] 5.4 流式 `chat()` 接口签名与行为保持不变
- [ ] 5.5 新增测试 `tests/test_model_resolver_optional.py`：
  - [ ] 5.5.1 用例：`optional=True` + 全链失败 → 返回 None，无异常，日志含 WARNING
  - [ ] 5.5.2 用例：`optional=False` + 全链失败 → 抛 `RuntimeError`，错误信息含失败链摘要
  - [ ] 5.5.3 用例：`optional=True` + 第一家成功 → 正常返回 `LLMResponse`，无 WARNING
- [ ] 5.6 跑 `pytest -q`、`mypy src/nini`、`black --check src tests`
- [ ] 5.7 提交 PR；commit 信息：`feat(agent): chat_complete 增加 optional 参数支持非致命用途`

## 6. title_generator 大幅瘦身（T5，独立 PR：refactor/title-generator-slim，依赖 T1+T3+T4）

- [ ] 6.1 验证 T1、T3、T4 PR 已合并到 main 并跑过完整 CI
- [ ] 6.2 评估 `length_retry` 删除可行性：
  - [ ] 6.2.1 grep `data/debug/llm/` 已有 dump 文件，搜索 `length_retry` 或 `finish_reason.*length` 关键字，统计历史触发记录
  - [ ] 6.2.2 grep 近 30 天 `nini start` 日志（如有）中 `length_retry` 关键字
  - [ ] 6.2.3 若历史 0 次触发 → 直接删除；若 ≥1 次触发 → 保留为单一 prompt 内"短输出"约束（不再走多次 LLM 调用），并在 PR 描述说明保留理由
  - [ ] 6.2.4 不要构造新样本跑 100 次"统计"——这是不可执行指标
- [ ] 6.3 重写 `title_generator.generate_title`：
  - [ ] 6.3.1 删除 `strategies` 列表与 for 循环
  - [ ] 6.3.2 改为单次 `await model_resolver.chat_complete([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=_TITLE_MAX_TOKENS, purpose="title_generation", optional=True)`
  - [ ] 6.3.3 当返回 `None` 或 `response.text` 为空 → 调用 `_fallback_title(messages)`
  - [ ] 6.3.4 删除外层 `try ... except Exception` 块（含 4 月 29 日临时打的 patch）
  - [ ] 6.3.5 保留：`_collect_relevant_messages`、`_normalize_title`、`_clean_message`、`_strip_leading_filler`、`_is_generic_title`、`_score_fallback_candidate`、`_trim_title_length`、`_fallback_title`、`_preview_text`、`_build_title_prompt`
- [ ] 6.4 验证：`title_generator.py` 行数显著减少（删除策略循环 + try/except 后预计减少 ~30% 以上）
- [ ] 6.5 调用方 `src/nini/api/websocket.py:_auto_generate_title` 检查：
  - [ ] 6.5.1 现有 `try ... except Exception` 保留作为顶层异步任务通用防御
  - [ ] 6.5.2 不为 LLM 故障写专门处理；不需其它改动
- [ ] 6.6 更新现有 `tests/test_title_generator.py` 与新增用例：
  - [ ] 6.6.1 用例：LLM 返回有效标题 → `generate_title` 返回规范化标题
  - [ ] 6.6.2 用例：LLM 返回 None（mock chat_complete 返回 None）→ 走 `_fallback_title`
  - [ ] 6.6.3 用例：LLM 返回空文本 → 走 `_fallback_title`
  - [ ] 6.6.4 用例：消息为空 → 返回 None
  - [ ] 6.6.5 用例：`generate_title` 在所有上述场景下不抛 LLM 故障相关异常
- [ ] 6.7 跑 `pytest -q`、`mypy src/nini`、`black --check src tests`
- [ ] 6.8 提交 PR；commit 信息：`refactor(agent): 瘦身 title_generator 移除手写 LLM 重试与异常吞噬`

## 7. provider 接口下沉（T6，独立 PR：refactor/provider-pick-model-for-purpose，可与 T2-T5 并行开分支）

- [ ] 7.1 在 `src/nini/agent/providers/base.py` 的 `BaseLLMClient` 中新增方法：
  ```python
  def pick_model_for_purpose(self, purpose: str) -> str | None:
      """返回该用途偏好的模型名；None 表示沿用主模型。"""
      return None
  ```
- [ ] 7.2 在每个 provider 子类实现偏好（按 design 决策 4 + spec 列表）：
  - [ ] 7.2.1 `DeepSeekClient`: 偏好 `["deepseek-chat"]`
  - [ ] 7.2.2 `ZhipuClient`: 偏好 `["glm-4-flash", "glm-4-air", "glm-4"]`
  - [ ] 7.2.3 `DashScopeClient`: 偏好 `["qwen-turbo", "qwen-plus"]`
  - [ ] 7.2.4 `OllamaClient`: 不覆写（沿用默认 `return None`）
  - [ ] 7.2.5 `OpenAIClient`: 偏好 `["mini", "gpt-4.1", "gpt-4o"]`（沿用现有 matcher）
  - [ ] 7.2.6 `AnthropicClient`: 偏好 `["haiku", "sonnet"]`
  - [ ] 7.2.7 `MoonshotClient`: 偏好 `["8k", "32k", ("kimi", "chat")]`
  - [ ] 7.2.8 `MiniMaxClient`: 偏好 `["abab", "m2.1", "m2.5"]`
- [ ] 7.3 抽出公共匹配函数（建议放到 `providers/base.py`）：
  ```python
  def match_first_model(available: list[str], keyword_groups: list[tuple[str, ...]]) -> str | None
  ```
  各 provider 通过它实现 `pick_model_for_purpose`
- [ ] 7.4 修改 `model_resolver.py`：
  - [ ] 7.4.1 删除 `TITLE_MODEL_MATCHERS` 字典
  - [ ] 7.4.2 删除 `_select_title_model_from_available` 方法
  - [ ] 7.4.3 重写 `_get_title_client`：调用 `active_client.pick_model_for_purpose("title_generation")`，得到偏好 model 名后用 `_build_client_for_provider` 构造新 client
  - [ ] 7.4.4 评估 `_get_title_client` 是否还有存在必要——若 `_resolve_client_plan` 内 `if purpose == "title_generation"` 分支可改为通用"按 `pick_model_for_purpose` 切换 model"逻辑，则可整体删除
  - [ ] 7.4.5 保留 `_should_use_builtin_fast_for_trial_title`（属于 BUILTIN/试用商业逻辑，本次不动）
  - [ ] 7.4.6 清理 T2 中 `getattr(...)` 兼容写法，改为直接调用 `active.pick_model_for_purpose(purpose)`
- [ ] 7.5 验证：`model_resolver.py` 内 `purpose == "title_generation"` 字符串使用范围限定在路由解析查找用途（不出现在模型选择或专用客户端构造逻辑中）；具体次数不设硬阈值
- [ ] 7.6 新增测试：
  - [ ] 7.6.1 `tests/test_provider_pick_model_for_purpose.py`：每个 provider 一组用例，覆盖"偏好可用"、"偏好不可用回退 None"、"非 title_generation 用途返回 None"
  - [ ] 7.6.2 追加到 `tests/test_phase5_model_resolver.py` 或新建 `tests/test_model_resolver_title_routing.py`：mock provider 的 `pick_model_for_purpose`，断言 resolver 使用偏好模型构造请求
- [ ] 7.7 关联校验：偏好列表与 `openspec/specs/simplified-model-config/spec.md` 中"标题生成自动使用廉价模型"列表一致
- [ ] 7.8 跑 `pytest -q`、`mypy src/nini`、`black --check src tests`
- [ ] 7.9 提交 PR；commit 信息：`refactor(agent): 下沉标题模型偏好到 BaseLLMClient.pick_model_for_purpose`

## 8. 集成验收（T7）

- [ ] 8.1 全仓 grep 验证清理彻底：
  - [ ] 8.1.1 `should_fallback` 无残留（除 OpenSpec 历史 changes 与本 spec 内的引用）
  - [ ] 8.1.2 `TITLE_MODEL_MATCHERS` 无残留
  - [ ] 8.1.3 `_select_title_model_from_available` 无残留
  - [ ] 8.1.4 resolver 内 `title_generation` 字符串使用范围合理（仅出现在路由表/路由查找/降级链解析等场景）
- [ ] 8.2 跑完整流水线：
  - [ ] 8.2.1 `black --check src tests`
  - [ ] 8.2.2 `mypy src/nini`
  - [ ] 8.2.3 `python scripts/check_event_schema_consistency.py`
  - [ ] 8.2.4 `pytest -q`
  - [ ] 8.2.5 `cd web && npm test && npm run build`（应无影响，做防回归）
- [ ] 8.3 手测脚本（按 proposal 验证段落，**关键**：必须验证用户报的具体 bug 已修复）：
  - [ ] 8.3.1 起 `nini start`
  - [ ] 8.3.2 故意把 `NINI_BUILTIN_DASHSCOPE_API_KEY` 改坏，保持 `NINI_DASHSCOPE_API_KEY` 有效
  - [ ] 8.3.3 新建会话发一条消息，确认会话主链路正常
  - [ ] 8.3.4 确认会话标题正常生成（应来自 BUILTIN→激活 fallback，不应是规则兜底）
  - [ ] 8.3.5 检查日志：能看到 builtin 401 + 降级到 dashscope active client 成功的完整 fallback chain
  - [ ] 8.3.6 反向场景：`NINI_DASHSCOPE_API_KEY` 与 `NINI_BUILTIN_DASHSCOPE_API_KEY` 都改坏，确认走规则兜底（`_fallback_title`），标题非空
- [ ] 8.4 用 `openspec verify-change refactor-llm-router-fallback`（或 `/opsx:verify`）做最终一致性校验
- [ ] 8.5 在 PR 描述中附上：行数变化（before/after）、resolver 内 `title_generation` 出现次数变化、新增/修改测试数

## 引用矩阵（由任务 1.x 填充，禁止在 1.x 完成前提交其它任务）

<!-- 1.1-1.4 的输出在此 -->

```
should_fallback:
  src/nini/agent/model_resolver.py:??, ??
  tests/test_phase5_model_resolver.py:??, ??
  ...

_classify_llm_error / _LLMErrorDisposition / PURPOSE_ROUTE_FALLBACKS:
  ...

purpose == "title_generation" / TITLE_MODEL_MATCHERS / _get_title_client / _select_title_model_from_available / _should_use_builtin_fast_for_trial_title:
  ...

title_generator / generate_title:
  ...
```

## 基线状态（由任务 1.5/1.6/1.7 填充）

<!-- pytest / mypy / black / event-schema 的初始绿/红记录 -->

<!-- 现有相关测试用例数 -->

<!-- 1.7：BUILTIN quota 计数语义结论 -->
