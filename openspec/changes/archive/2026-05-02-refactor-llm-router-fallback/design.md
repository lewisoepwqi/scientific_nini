## Context

`src/nini/agent/model_resolver.py` 是单进程内所有 LLM 调用的中央调度器，承担三件事：
1. 按 `purpose`（chat / title_generation / image_analysis / planning ...）解析候选 client 列表；
2. 顺序调用候选 client，按规则在失败时降级；
3. 把"轻量场景用便宜模型"等业务策略硬编码在内部。

### 本次 bug 触发链

用户 `.env` 同时配置了 `NINI_DASHSCOPE_API_KEY`（用户主激活 dashscope）与 `NINI_BUILTIN_DASHSCOPE_API_KEY` + `NINI_BUILTIN_TITLE_MODEL=qwen3-coder-plus`（BUILTIN 标题专用）。BUILTIN 那把 key 过期。

在标题生成调用链：
1. `_resolve_client_plan("title_generation")` 进入 line 734 `else` 分支（用户没配 `purpose_title_generation_provider`，用户主 dashscope 不是通过 `purpose_*` 配置的）；
2. `_should_use_builtin_fast_for_trial_title` 触发 BUILTIN 路径，得到 `clients = [builtin_client]` **单元素列表**；
3. `chat()` 调用 `builtin_client` → DashScope 返回 401；
4. `_classify_llm_error` 对 401 返回 `should_fallback=False`；
5. `chat()` 中 `if not disposition.should_fallback: raise` → 抛 `RuntimeError`；
6. `title_generator.generate_title` 的 `except Exception` 仅记日志返回 `None`；
7. 标题为空。

### 三处真因

1. **BUILTIN 单 client 列表无降级**：`_resolve_client_plan` 在 BUILTIN 分支里 `clients = [builtin_client]` 后没有把激活 provider 的 client 加入候选。这是直接因。
2. **`should_fallback` 把"同 client 重试"和"跨 provider 降级"合并**：即使 BUILTIN 路径有了激活 client 作为下一候选，鉴权错的 `should_fallback=False` 也会让 `chat()` 立即终止而不试下一家。这是与 (1) 配套的因。
3. **"非致命用途"语义无表达**：`title_generator` 必须自己写 try/except 防御，让"失败可吞噬"散落在调用方。这是架构债。

### 附带架构债

- `if purpose == "title_generation"` 在 resolver 里出现 12+ 处分支；
- `TITLE_MODEL_MATCHERS` / `_select_title_model_from_available` / `_get_title_client` 把模型选择逻辑塞进通用调度器；
- `PURPOSE_ROUTE_FALLBACKS` 表里漏了 `title_generation → chat`（仅影响"使用 purpose_*_provider 配置且 title 未配"的场景，不影响当下 BUILTIN bug，但属于架构一致性补漏）。

系统未对外，无数据迁移与公开 API 兼容性约束。

## Goals / Non-Goals

**Goals:**
- **修复用户报告的具体 bug**：BUILTIN 单 client 失败时能降级到激活 provider，让标题/会话在 BUILTIN key 失效时仍能完成。
- 把鉴权错误的处理修正为"同 client 不重试 / 跨 provider 可降级"，让候选列表中的下一家有机会尝试。
- 把"非致命用途失败可吞噬"语义集中表达在 resolver 层（`optional` 参数），调用方不再写防御性 try/except。
- 把"标题该用哪个轻量模型"的知识从 resolver 移到 provider 自身，让 resolver 退化为纯调度器。
- 删干净 `title_generator.py` 中重复的重试/异常处理逻辑。
- 补全 `PURPOSE_ROUTE_FALLBACKS` 表的 `title_generation → chat` 与 `image_analysis → chat`，覆盖未来用 purpose 配置的场景。

**Non-Goals:**
- 不解耦 `BUILTIN_PROVIDER_ID` 与试用 quota 体系（不动 `_should_use_builtin_fast_for_trial_title` / `is_builtin_exhausted` / `_build_builtin_quota_error`）。
- 不改 BUILTIN quota 计数语义（"调用前/调用成功后"的计数时机保持现状）。
- 不重写流式 `chat()` 接口，`optional` 仅加在 `chat_complete()` 上。
- 不改前端、不动 UI 配置项、不改 settings 字段。
- 不引入新依赖。
- 不为不存在的问题写防御代码（如 `PURPOSE_ROUTE_FALLBACKS` 的环路防护——当前所有 fallback 值都不是表的键，结构上无环）。

## Decisions

### 决策 1：BUILTIN 调用降级到激活 provider（修当下 bug 的关键）

**选择**：修改 `_resolve_client_plan` 在 BUILTIN 分支构造 `clients` 列表后追加激活 provider 的 client（如果存在）：

```python
if route_provider == BUILTIN_PROVIDER_ID:
    ...
    if not clients:
        raise await self._build_builtin_quota_error(mode_candidate)
    # 新增：BUILTIN 失败时降级到激活 provider
    active = self._get_single_active_client()
    if active and active is not clients[0]:
        # 询问 provider 偏好的模型（决策 4 的接口）
        preferred_model = active.pick_model_for_purpose(purpose)
        if preferred_model and preferred_model != active.get_model_name():
            built = self._build_client_for_provider(
                active.provider_id, model=preferred_model
            )
            if built and built.is_available():
                active = built
        clients.append(active)
```

**理由**：
- 用户配了主 provider 时显然希望它能兜底；当前列表只放 BUILTIN 是漏配。
- 与决策 2（错误分类）配合后，BUILTIN 401 会自动尝试 `clients[1]`。
- BUILTIN quota 计数仍按现状（`builtin_mode_to_count` 在调用前已确定，与是否后续降级无关）。
- 不动 `_should_use_builtin_fast_for_trial_title` 与 `is_builtin_exhausted`，避开 BUILTIN 商业逻辑解耦。

**备选**：让 `chat()` 失败时回头重新调用 `_resolve_client_plan` 取替代用途的 client。**否决**：把"重新解析"塞进调用循环会让控制流复杂化，候选列表前置确定语义清晰。

**备选**：在 `title_generator` 内部失败时手写 `purpose="chat"` 重试。**否决**：把降级策略下沉到调用方会让"如何降级"散落在各业务模块，违背单一职责；且不能修复 `image_analysis` 等同类未来用途。

**风险**：BUILTIN quota 计数若依赖"调用结果回调"，可能因为有了下一家 fallback 而表现异常。T2 任务必须明确确认现状是"调用前提交计数"，不依赖后续结果——若现状不符则需在该任务内调整或暂停降级追加。

### 决策 2：错误分类单维化（仅保留 `try_next_provider`）

**选择**：把 `_LLMErrorDisposition` 的 `should_fallback: bool` 重命名为 `try_next_provider: bool`，并按下表填充：

| 错误类型 | try_next_provider |
|---|---|
| AuthError / HTTP 401 / HTTP 403 | true |
| HTTP 400（请求参数无效） | false |
| RateLimit / HTTP 429 | true |
| Timeout | true |
| ConnectError | true |
| HTTP 503 | true |
| 其它 APIError 与未识别异常 | true |

`message`、`log_level` 字段保留不变。

**理由**：
- 当前 `should_fallback=False` 同时表达"不重试"与"不降级"，但两件事在鉴权错场景下结论应该相反（不重试 / 但要降级）。
- 重命名为 `try_next_provider` 后语义对齐物理事实（key per-provider）。
- **不引入 `retry_same_client` 字段**：本次没有限流退避或同 client 重试场景，预留字段违反 "不为'灵活/可配置'而预先扩展"。等限流退避真正落地时再加。

**备选**：保留 `should_fallback` 但改为对鉴权错返回 `True`。**否决**：会让"key 无效请检查配置"用户友好提示丢失（用户配单家时仍应直接报错）。重命名是更准的措辞。

**备选**：保留二维（`retry_same_client` + `try_next_provider`）。**否决**：见上，违反 YAGNI。

### 决策 3：`chat_complete` 增 `optional` 参数

**选择**：方法签名改为：
```python
async def chat_complete(self, ..., optional: bool = False) -> LLMResponse | None
```
当所有候选 client（含 BUILTIN→激活降级链）全部失败且 `optional=True` 时返回 `None`，不抛异常。

**理由**：把"非致命用途的失败语义"集中在 resolver 层，避免 `title_generator`、未来的 `image_analysis` 各自写一份 try/except。

**备选**：返回 `LLMResponse(text="")`。**否决**：会和"LLM 返回空文本"两种情况混淆。

**备选**：用异常子类 `OptionalLLMFailure` 让调用方按异常类型决定是否吞噬。**否决**：异常控制流隐晦；显式参数更易读。

### 决策 4：`pick_model_for_purpose` 接口下沉

**选择**：在 `BaseLLMClient` 加默认实现：
```python
def pick_model_for_purpose(self, purpose: str) -> str | None:
    """返回该用途偏好的模型名；None 表示使用主模型。"""
    return None
```
各 provider 子类覆写，把 `TITLE_MODEL_MATCHERS` 中对应自己 provider 的关键词搬入。

**理由**：模型选择是 provider 自己的领域知识，让 resolver 维护这张映射表是错位的关注点。下沉后 resolver 内可以删除 `TITLE_MODEL_MATCHERS` 与 `_select_title_model_from_available`，`_get_title_client` 简化为通用"按 `pick_model_for_purpose` 切换 model"逻辑。

**备选**：保留 `TITLE_MODEL_MATCHERS` 在 resolver 但只暴露一个查询函数。**否决**：不解决耦合，只是包装。

**备选**：把整张映射表搬到 `simplified-model-config` 配置文件。**否决**：那里管 UI 配置，不管运行时策略。

### 决策 5：`title_generator` 大幅瘦身

**选择**：删掉 `strategies` 重试循环、`length_retry` 策略、`except Exception` 兜底；只保留：
- 一次 `chat_complete(..., purpose="title_generation", optional=True)`；
- LLM 返回为空或 None 时走 `_fallback_title` 规则兜底；
- 长度截断/前缀清洗等纯文本规范化逻辑。

**理由**：
- `length_retry` 仅在 `finish_reason=="length"` 且 `raw_text` 为空时触发，标题场景因 prompt 已严格约束"1 行内"实际触发率低。规则兜底已是合格 fallback，多一次 retry 的边际收益不抵复杂度。
- `except Exception` 兜底由 `optional=True` + resolver 内部完整降级链替代。

**评估方式**：T5 任务中，先在 `data/debug/llm/` 已有 dump 与 `nini start --reload` 日志中查找 `length_retry` 历史触发记录。如果近期数据中 ≥1 次触发，保留 `length_retry`（但移到决策 3 的 `optional` 之外作为单独 prompt 兜底）；如果 0 次触发，直接删除。**不需要构造 100 个样本跑统计**。

**保留**：`_fallback_title` 规则兜底——当 LLM 返回 None（包括 `optional=True` 下的全链失败）时仍能给出基于用户消息的合理标题。这是"无 LLM 也能工作"的最后一道护栏。

**调用方 `_auto_generate_title` 的 `try ... except`**：保留，作为顶层异步任务的通用异常防御（防止意外异常导致 task 静默死亡）；但不再为 LLM 故障写专门处理。本次不强制收窄异常类型。

### 决策 6：分阶段提交

**选择**：按 7 个 PR 切分（每任务一个），顺序合并。

| PR | 任务 | 修当下 bug 必需？ |
|---|---|---|
| T1 | `PURPOSE_ROUTE_FALLBACKS` 补全 | 否（架构补漏） |
| T2 | BUILTIN→激活 fallback | **是** |
| T3 | 错误分类单维化 | **是** |
| T4 | `chat_complete` optional 参数 | 否（前置依赖 T5） |
| T5 | `title_generator` 瘦身 | 否（依赖 T1+T3+T4） |
| T6 | provider `pick_model_for_purpose` 接口下沉 | 否（架构清理） |
| T7 | 集成验收 | 验证 |

**关键路径**：T2 + T3 合并后即可消除当下 bug（手测可验证）。T1/T4/T5/T6 是架构改造与未来用途铺路。

**理由**：每个 PR 独立通过 CI、独立 review、独立可回滚。决策 4（provider 接口下沉）覆盖 8 个 provider 文件，挤进决策 2 的 PR 会让 review 失焦。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| 删除 `should_fallback` 字段时遗漏调用方 | T0 阶段建立引用矩阵；T3 改完后全仓 grep `should_fallback` 应为 0 命中（除 OpenSpec 历史 changes 与本 spec） |
| BUILTIN→激活 fallback 影响 quota 计数语义 | T2 必读 `_resolve_client_plan` 现状确认 `builtin_mode_to_count` 是"提交即计数"还是"成功即计数"；只在前者条件下追加 fallback；后者条件下需另设方案或暂缓 |
| `try_next_provider=True` 在单 client 配置下变成空操作 | 这是预期；`optional=True` 与规则兜底仍兜底标题。proposal 已说明 |
| `pick_model_for_purpose` 在 8 个 provider 类里实现不一致 | `BaseLLMClient` 提供默认 `return None`；子类只在确有偏好时覆写；针对每 provider 一组单测断言偏好顺序 |
| 现有测试断言依赖 `should_fallback` 字段或 `_get_title_client` 私有方法 | T0 盘点；T3/T6 同步更新测试 |
| `optional=True` 让调用方误以为所有错误都被吞 | 文档与日志清晰：optional 仅吞"全链失败"的最终错；中间错仍按错误分类逐家降级并记 warning |
| 决策 4 改动 8 个 provider 文件，diff 大 | 单独 PR；每个 provider 独立小 commit；每个 provider 配 1-2 条单测 |
| 标题专用模型偏好列表与 `simplified-model-config` 中 spec 列表不一致 | 把 spec 中列表作为 ground truth，T6 实现时严格对齐；新增"偏好列表与 spec 一致"的单测 |

## Migration Plan

不涉及数据迁移、不涉及配置迁移。代码层面按 T0→T7 顺序合并即可。

**回滚策略**：
- 每个任务 PR 独立可 revert。任务依赖关系：T5 依赖 T1+T3+T4；T6 与 T2-T5 在分支层面可并行，但合并需按"依赖前者已合并"顺序。
- 回滚顺序按"依赖反向"进行：T7→T6→T5→T4→T3→T2→T1，但若仅出现局部问题可只 revert 受影响 PR。
- 因不触及任何持久化结构，回滚后无数据修复成本。

## Open Questions

- **Q1**：T6 是否要顺手把 `_should_use_builtin_fast_for_trial_title` 也搬到 BUILTIN provider 里？  
  **倾向**：暂留 resolver。该函数耦合 BUILTIN/试用 quota 概念，属于方案 C 范围，本次不扩散。
- **Q2**：BUILTIN→激活 fallback 应只对 `title_generation` / `image_analysis` 这类非致命用途生效，还是对所有 purpose 都生效？  
  **倾向**：对所有 purpose 都生效。当前 BUILTIN 分支在所有 purpose 下都构造单 client 列表，统一追加激活 client 是一致的简化。`optional` 参数控制"全链失败如何处理"是另一维度，不应与"是否追加 fallback client"耦合。T2 实现按该方向。
