## Why

会话标题生成在 BUILTIN 标题专用 key 失效时报 401 → 标题为空。这是 `model_resolver` 当前架构在 3 个相互独立的设计缺陷叠加下暴露出的故障：

1. **BUILTIN 路径无运行时降级**：当 `_resolve_client_plan` 走 BUILTIN 分支（试用模式、或显式指定 BUILTIN 用途）时，候选 client 列表只有 `[builtin_client]` 一个元素。该 client 调用失败时没有"降级到用户激活 provider"的路径，即便用户已配好可用主 client。
2. **错误分类把"同 client 重试"和"跨 provider 降级"合并成单一 `should_fallback`**：鉴权错（401/403）被同时禁用两件事，但事实上 key 是 per-provider 的，跨家降级安全且必要。
3. **非致命用途的失败语义没有被路由器表达**：`title_generator` 必须自己写 try/except 防御性吞噬。同样的负担会复现在未来的 `image_analysis`、`summarization` 等任意"非致命增强用途"。

附带的架构债：标题这个业务概念深度污染了通用路由器（`if purpose == "title_generation"` 在 resolver 里有 12+ 处分支、`TITLE_MODEL_MATCHERS` / `_get_title_client` / `_select_title_model_from_available` 等多个标题专用函数），让每次类似改动都波及面巨大。

注：原审查阶段我曾把"补全 `PURPOSE_ROUTE_FALLBACKS` 表"当成核心修复，但代码追踪后确认该表是**配置级 fallback**（替代未配置 purpose 的 route 配置），**不是**调用级 fallback。当前 bug 的真因在 BUILTIN 单 client 路径，本次 change 已把"BUILTIN 调用降级"作为独立改动列入。

系统尚未正式对外，是清理这层架构债的最佳窗口。本次重构追求"治本而不外扩"：消灭已知的具体缺口与本次故障，不解耦 BUILTIN/试用 quota 商业逻辑（属于另一个 change 范围）。

## What Changes

- **新增** BUILTIN 调用降级：当 `_resolve_client_plan` 解析得到 `[builtin_client]` 单元素列表，且当前存在用户激活 provider 时，候选列表追加该激活 client；BUILTIN 调用失败时按错误分类规则降级到激活 client。**这是修复用户报告 bug 的关键改动。**
- **变更** LLM 错误分类从单一 `should_fallback` 改为单维 `try_next_provider`，修复 401/403 鉴权错误不能跨供应商降级的 bug（key 是 per-provider 的）。
- **新增** `chat_complete(..., optional: bool = False)` 参数：标题、图像分析等非致命用途调用时传 `optional=True`，全链失败返回 `None` 而非抛异常，把"失败可吞噬"语义集中在 resolver 层。
- **变更** `BaseLLMClient` 接口新增 `pick_model_for_purpose(purpose) -> str | None`，各 provider 自管轻量模型偏好；`model_resolver.TITLE_MODEL_MATCHERS` / `_select_title_model_from_available` 整体下沉，resolver 内 `if purpose == "title_generation"` 分支收敛到路由解析必要范围。
- **变更** `title_generator.generate_title` 删除手写 `strategies` 重试循环与异常吞噬代码，转为单次 `chat_complete(..., optional=True)` 调用 + 规则兜底（`_fallback_title`）。
- **新增** 补全 `PURPOSE_ROUTE_FALLBACKS` 表中 `title_generation → chat`、`image_analysis → chat` 条目。**注意**：这是配置级 fallback，仅当用户使用 `purpose_*_provider` 配置且未配 title 时生效；对当下 BUILTIN 路径无直接修复作用，但作为架构一致性补漏。
- **保留** `simplified-model-config` 现有"标题生成自动使用廉价模型"的可观察行为：偏好列表内容不变，仅实现位置从 resolver 移到 provider。

### 非目标（明确不在本次范围）

- 不解耦 `BUILTIN_PROVIDER_ID` / 试用 quota 体系（不动 `_should_use_builtin_fast_for_trial_title` / `is_builtin_exhausted` / `_build_builtin_quota_error` 等商业逻辑）。
- 不引入新的 provider，不改 provider 列表与默认优先级。
- 不重写流式 `chat()` 接口（`optional` 仅加在 `chat_complete` 上）。
- 不修改 UI 配置项与前端任何代码。

## Capabilities

### New Capabilities

- `llm-purpose-routing`: 用途级 LLM 路由与降级策略，覆盖 purpose 到 provider/model 的解析、配置级 fallback、调用级降级（含 BUILTIN→激活 provider）、错误分类与多级降级、非致命用途的失败吞噬契约。

### Modified Capabilities

无。`simplified-model-config` 中"标题生成自动使用廉价模型"等可观察行为保持不变，仅实现内部重构。

## Impact

### 受影响代码

- `src/nini/agent/model_resolver.py`（核心，重构 `_resolve_client_plan` BUILTIN 分支、错误分类、`chat_complete`、`_get_title_client`，预计净减若干行）
- `src/nini/agent/title_generator.py`（瘦身，移除策略重试与异常吞噬）
- `src/nini/agent/providers/base.py`（接口新增 `pick_model_for_purpose`）
- `src/nini/agent/providers/{openai,anthropic,deepseek,zhipu,dashscope,moonshot,minimax,ollama}_provider.py`（每个覆写偏好列表）
- `tests/test_phase5_model_resolver.py`、`tests/test_model_resolver_trial_policy.py`、`tests/test_title_generator.py`：现有断言需要随错误分类与 client 列表改动更新；新增 BUILTIN→active fallback、optional、provider 偏好等场景测试。

### 受影响 API 与行为

- `model_resolver.chat_complete` 新增可选参数 `optional: bool = False`，向后兼容；返回类型变为 `LLMResponse | None`。
- 流式 `chat()` 接口签名不变；其内部使用的错误分类字段名变化（`should_fallback` → `try_next_provider`）属于内部重构，对调用方不可见。
- 401/403 错误的处理语义改变：之前不跨供应商降级，之后跨供应商降级。**用户可见影响**：多供应商或 BUILTIN+激活 provider 配置下，单家 key 失效不再让会话整体不可用——这是修复，不是回归。
- BUILTIN 调用失败时不再立即抛错，而是先尝试激活 provider；激活 provider 也失败才抛错（或在 `optional=True` 时返回 None）。**用户可见影响**：BUILTIN quota 耗尽或 key 失效时，若用户配了主 provider，标题/会话仍能用主 provider 完成。

### 风险与回滚

- **主要风险 1**：`_classify_llm_error` 是中央错误路径，字段改名影响 `chat()` 与 `chat_complete()`。需通过 T0 引用矩阵确认无遗漏调用方。
- **主要风险 2**：BUILTIN→激活 fallback 可能影响 quota 计数语义（BUILTIN 失败也算用过一次 quota？）。需在 T2 任务中明确"调用前提交计数 vs 调用成功后计数"的现状并保持不变。
- **回滚方式**：每个任务独立 PR、独立可回滚（具体顺序见 design.md Migration Plan）。
- **数据风险**：无。本次重构不触及任何持久化结构（会话、配置、quota 计数表均不变）。

### 验证

- `pytest -q`、`python scripts/check_event_schema_consistency.py`、`mypy src/nini`、`black --check src tests` 全绿。
- 手动用例：故意把 `NINI_BUILTIN_DASHSCOPE_API_KEY` 改坏，新建会话发一条消息，确认（a）会话主链路正常，（b）标题通过 BUILTIN→激活 fallback 由用户主 client 生成，（c）日志能看到完整 fallback chain 与降级原因。
