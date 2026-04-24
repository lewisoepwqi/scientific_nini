# Runner 批次完成摘要注入（方案 4）

- 状态：Proposal（待实施）
- 起因会话：`0710a1455441`
- 前置 PR：`fix/task-state-init-prompt-loop`（方案 1，即时止血）
- 最后更新：2026-04-24

## 背景

当 LLM 在同一用户轮内进行多轮 tool_call 调度时，会出现"忘记自己上一轮已完成的工具调用"的现象：

```
Round 1 (parallel):
  task_state(init)                              → success
  dataset_catalog(profile, A, full)             → success
  dataset_catalog(profile, B, full)             → success

Round 2 (parallel):
  task_state(update, task1 → in_progress)       → success
  dataset_catalog(profile, A, full)             → DUPLICATE_DATASET_PROFILE_CALL
  dataset_catalog(profile, B, full)             → DUPLICATE_DATASET_PROFILE_CALL
```

现状：
- `runner.py:1909-1950` 有 `DUPLICATE_DATASET_PROFILE_CALL` 反应式守卫
- `runner.py:2296-2305` 已在 runner 层维护 `successful_dataset_profile_signatures` 与 `dataset_profile_max_view_by_name`
- 方案 1（柔化 task_state init 文案）已合并，作为 prompt 层的被动提示

但：
- 反应式守卫只能"拦截后告诉 LLM 别再这么做"，仍然消耗一次 tool_call + 一轮 LLM 思考
- 方案 1 只治 task_state init 一处，未来 `run_code`、`dataset_transform` 等若有类似守卫，每处都要改各自返回文案
- LLM 在"下一轮请求"组装上下文时，缺少明确的"本轮已完成"状态快照

## 目标

在 runner 层建立**主动、统一、可扩展**的批次完成状态通道：
每次 LLM 发起一批 tool_call、runner 汇集结果后、再次请求 LLM 之前，向 LLM 注入一条结构化的 system/developer 备注，列出本批次已成功完成的"守卫语义工具"及其关键产出摘要。

预期效果：
- LLM 进入下一轮时先看到"本轮已完成 X / Y / Z，请直接使用其结果"
- 重复调用率下降 → DUPLICATE_* 守卫命中次数显著降低
- 新增守卫语义只需在 runner 的"completion registry"注册一项，无需散落改多处 prompt

## 方案设计

### 1. Completion Registry（runner 内部）

在 `TurnRunner` 内维护一张 per-turn 的表：

```python
@dataclass
class CompletedToolSignature:
    tool_name: str
    args_signature: str            # 现有 tool_args_signature，已有
    summary: str                   # 人类可读的一句话（"血压心率_20220407.xlsx 的 full 概况（2627 行 × 8 列）"）
    action_id: str | None
    ts: str                        # ISO-8601

per_turn_completions: list[CompletedToolSignature]
```

现有 `successful_dataset_profile_signatures` / `dataset_profile_max_view_by_name` 合并为 registry 的一条"写入回调"路径——不是删除它们（守卫仍需要精确签名），而是在它们写入的同一位置也 append 一条 `CompletedToolSignature`。

### 2. Summary 生成器注册表

为每种具备"守卫语义"的工具注册一个 summarizer：

```python
CompletionSummarizer = Callable[[ToolCallResult], str | None]

COMPLETION_SUMMARIZERS: dict[str, CompletionSummarizer] = {
    "dataset_catalog": _summarize_dataset_catalog_profile,
    # 未来：
    # "dataset_transform": _summarize_dataset_transform,
    # "run_code": _summarize_run_code,
}
```

`None` 返回值表示"该次调用无需进入摘要"（例如 `dataset_catalog(operation=list)` 不是守卫对象）。

### 3. 注入点：下一轮请求组装前

在 `TurnRunner` 调用 LLM 客户端前（即 `_build_messages_for_next_round` 或等价处），若 `per_turn_completions` 非空，追加一条：

```
role: system（或 developer，取决于 provider 支持）
content:
  【本轮已完成的分析工具（请勿重复调用，直接使用结果）】
  - dataset_catalog(profile, 血压心率_20220407.xlsx, full) — 2627 行 × 8 列
  - dataset_catalog(profile, 血压心率_20220407 (2).xlsx, full) — 2627 行 × 8 列
```

注入规则：
- 仅在"本轮曾产生过 completion"时注入（无内容不注入噪声）
- 每轮重新生成（不跨轮累积，避免上下文膨胀）
- 当摘要数量 > N（默认 8）时截断并提示"仅显示最近 N 条"

### 4. 与守卫的关系

**不删除现有 DUPLICATE_* 守卫**。方案 4 是预防层，守卫是兜底层：

| 层 | 作用 | 失效时 |
|---|---|---|
| 方案 4（预防） | 注入 system 摘要，主动让 LLM 看到已完成状态 | LLM 仍忽视 → 进入守卫层 |
| 守卫（兜底，已存在） | 拦截重复调用、返回 recovery_hint | — |

两层互补。方案 4 上线后，守卫命中率应大幅下降（观测指标见下文）。

## 实施步骤

1. **数据结构**：在 `TurnRunner.__init__` 增加 `per_turn_completions: list[CompletedToolSignature]`，每轮 `run` 开始前清空
2. **Summarizer 抽象**：新增 `src/nini/agent/completion_summarizers.py`，登记 `dataset_catalog` 的 summarizer
3. **写入点**：在 `runner.py:2296-2305` 附近（tool 成功回调处）额外 `append` 到 `per_turn_completions`
4. **注入点**：在组装下一轮 messages 前（`_prepare_next_request` 或等价函数），若非空则前置一条 system message
5. **测试**：
   - 单测：summarizer 对各 tool_name 的输出正确、`None` 过滤生效
   - 集成：模拟 Round 1 两个 profile 成功 → Round 2 请求体含 summary；确认 LLM（mock 回复）收到
   - 回归：方案 1 柔化文案 + 方案 4 注入同时存在时，DUPLICATE_* 不应被触发（以固定 mock LLM 行为模拟）
6. **观测**：
   - 新增 metric：`runner.batch_completion_summary_injected_total{tool=…}`
   - 对比 metric：`guard.duplicate_call_blocked_total{tool=…}` 应在上线后下降

## 待决策问题

1. **注入位置是 `system` 还是 `developer`？**
   - 多数 OpenAI-like provider 支持 `developer`；但本地小模型可能只认 `system`。倾向于**跟随现有 system prompt 路径**（runner 已处理兼容）。
2. **摘要格式是 Markdown 列表还是 JSON？**
   - Markdown 对 LLM 更友好；JSON 便于未来工具再读取。倾向 **Markdown 列表 + 末尾隐藏 `<!-- completion-registry -->` 锚点**，两不误。
3. **跨轮持久化？**
   - 不做。跨轮持久化应走现有 `session.runtime_context` 机制，避免 runner 状态外溢。本方案仅处理 per-turn。
4. **Summary 中是否包含完整 data_summary？**
   - 不含。摘要只回答"做过什么 + 产出量级"，细节回查原 tool_result。避免上下文膨胀。

## 非目标

- 不重写现有 DUPLICATE_* 守卫
- 不修改任何单个工具的内部逻辑
- 不引入新的依赖
- 不覆盖"跨用户轮"的完成历史（那是 `context_builder` 的职责）

## 验收标准

- 复现会话 `0710a1455441` 的输入时，Round 2 不再出现 DUPLICATE_DATASET_PROFILE_CALL（mock LLM 配合测试）
- `pytest -q` 全量通过
- 新增 metric 在 `/api/metrics` 或等价端点可见
- 文档 `docs/architecture/agent-runner.md`（若存在）补充"批次完成摘要"一节

## 风险与回滚

- 风险：注入的 system message 可能与现有 prompt 冲突或导致 LLM 格式化输出偏移
  - 缓解：灰度开关 `NINI_RUNNER_COMPLETION_SUMMARY=on|off`，默认 off；观测一周后默认 on
- 回滚：翻开关即可；数据结构不持久化，无迁移成本
