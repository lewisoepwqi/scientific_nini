# Agent 鲁棒性分析与优化报告

> 日期：2026-04-01
> 分析会话：`df0d6255b269`、`a6646a7339e1`、`6fc06c120e52`
> 测试模型：GLM-5（智谱 AI）

---

## 一、背景

通过对三个真实血压心率时间序列分析会话的逐帧分析，识别出 Agent 在执行 PDCA 分析任务时的系统性失效模式。分析发现：失效根因并非单纯模型能力问题，而是系统在**软约束与硬约束的边界选择**上存在设计偏差——大量关键执行约束依赖"模型读懂消息后主动遵守"，对较弱模型缺乏结构性保障。

---

## 二、已发现的问题

### 2.1 工具调用模式问题

#### P0-1：task_state(init) 重复调用
**会话**：`df0d6255b269`
**现象**：LLM 连续调用两次 `task_state(init)`，第二次被拒绝，但消耗了一个 LLM 轮次。
**根因**：`init` 返回消息引导 LLM 调用 `task_state(update)` 开始第一个任务，LLM 误将其解读为需要再次 `init`。
**状态**：✅ 已修复（修改 1：init 自动启动首任务，无需 LLM 再调用 update）

---

#### P1-3：create_script 未跟随 run_script（持续复发）
**会话**：`a6646a7339e1`、`6fc06c120e52`
**现象**：LLM 调用 `code_session(create_script)` 后，将返回的 `success: true` 解读为"脚本已执行"，跳过必要的 `run_script` 调用，直接进行下一步分析。在 `6fc06c120e52` 会话中，简化版时间趋势脚本（`script_abaf8b8c384f`）从未被执行，但 LLM reasoning 中明确写道"时间趋势分析已经成功执行"。

**事件回放**：
```
L2  run_script(script_a5ccfc340f82)  → 超时失败
L4  create_script(简化版)            → ⚠️ 返回"尚未执行"警告
L6  REASONING: "时间趋势分析已经成功执行"   ← 完全忽略 ⚠️ 警告
L7  create_script(相关性分析)        → ⚠️ 返回"尚未执行"警告
L9  REASONING: "需要执行相关性分析脚本"    ← 这次正确识别
L10 run_script(相关性分析脚本)       → 成功
```

**根因**：
- `create_script` 返回 `success: true`，模型对 `success` 字段的信任高于消息文本
- 在"超时→重建脚本"的恢复路径下，模型处于"任务焦点切换"状态，会跳过上一步的警告
- ⚠️ 警告是纯文本干预，对弱模型的优先级低于结构化字段
**状态**：⚠️ 已部分修复（修改 6：加入警告文本），但恢复路径仍复发，需结构性修复

---

#### P0-3：task_state(update) 全量状态重发（5 任务全 no-op）
**会话**：`a6646a7339e1`
**现象**：进入最后"汇总结论"任务时，LLM 向 `task_state(update)` 发送了全部 5 个任务的完整当前状态，5 个全部是 no-op。触发 noop_repeat ≥ 2 熔断警告。
**根因（双重）**：
- 模型原因（主）：上下文压缩后丢失了"哪些任务已完成"的精确状态，GLM-5 倾向于"确认所有状态"以消除不确定性
- 提示词原因（辅）：进入最后任务时的返回消息含"回顾前面所有步骤的结果"，暗示 LLM 需要重新检视所有任务
**状态**：✅ 已修复（修改 5：改写复盘消息，明确"不要再调用 task_state"）

---

#### P2-2："回顾"消息引导不当
**会话**：`a6646a7339e1`
**现象**：最后任务的返回消息中"回顾前面所有步骤的结果"被弱模型理解为"需要重新同步任务状态"。
**状态**：✅ 已修复（同修改 5）

---

### 2.2 沙箱执行问题

#### P1-4：代码执行超时（60s 统一限制）
**会话**：`6fc06c120e52`
**现象**：时间趋势分析脚本在 2627 行数据上执行 fill_between + 多图渲染，超过 60s 沙箱限制。
**根因**：60s 是所有脚本的统一超时，可视化脚本（多图渲染 + 数据聚合）的天然耗时远高于统计计算脚本。
**状态**：🔴 未修复

---

### 2.3 上下文压缩问题

#### CP-1：轻量摘要丢失关键分析结果
**现象**：上下文压缩触发后，轻量摘要（`_summarize_messages`）将每条消息截断到 140 字符，最多保留 20 条。对 38+ 条消息的 PDCA 会话，18 条后半段消息被完全丢弃，工具返回的统计结果（均值、标准差、p 值等）全部丢失。
**影响**：模型在压缩后无法知道各任务的具体产出，被迫通过重发 task_state 来"回忆"进度。
**状态**：✅ 已改进（修改 9：tool_result 截断由 140→300 字符，max_items 由 20→30）

---

#### CP-2：LLM 摘要 prompt 不含 PDCA 任务状态要求
**现象**：LLM 摘要 prompt 要求保留 6 类信息，但未要求保留每个任务的完成状态和关键产出，导致摘要中可能只有"已完成数据分析"，而非"任务 2 completed（发现收缩压 118.09±10.87 mmHg）"。
**状态**：✅ 已改进（修改 10：新增 ⑥⑦ 两项要求，摘要上限从 600→800 字）

---

#### CP-3：轻量摘要不区分消息优先级
**现象**：`_summarize_messages` 线性处理，用户消息（3 字）与工具返回（含数值结果）平等截断到 140 字符。
**状态**：⚠️ 部分改进（修改 9 给 tool_result 更多空间，但未实现按类型动态优先级）

---

### 2.4 Harness 完成校验问题

#### HC-1：`ignored_tool_failures` 依赖关键词匹配
**现象**：校验规则要求最终文本含"失败"/"报错"/"error"/"未完成"之一。`6fc06c120e52` 会话中，时间趋势分析超时失败，最终报告未提及，触发 BlockedState。
**根因**：文本关键词匹配是弱信号——模型可以用"无法完成"替代"未完成"来逃过检测，也可以用"报错"一笔带过而不处理。
**状态**：🔴 未修复

---

#### HC-2：Recovery 提示不区分失败类型
**现象**：无论是"未忽略失败工具"还是"承诺产物未生成"，模型收到的恢复提示文本完全相同。弱模型收到"补齐缺口：未忽略失败工具"后，不知道需要具体做什么。
**状态**：🔴 未修复

---

#### HC-3：`_TRANSITIONAL_TEXT_RE` 只匹配全文开头
**现象**：正则 `r"^(接下来|下一步|..."` 使用 `^` 锚定，只能检测文本最开头的过渡性措辞。模型输出 Markdown 标题后跟过渡段落时会漏检。
**状态**：🔴 未修复

---

### 2.5 KV-cache 效率问题

#### KC-2：skills_snapshot 排在提示词首位
**现象**：skills_snapshot 内容随用户启用/禁用技能而变化，排在最前面会导致任何技能变动都使后续所有组件的 KV-cache 失效。
**状态**：✅ 已修复（修改 7：调整组件顺序，稳定组件在前，skills_snapshot 移至末位）

---

#### KC-4：chart_preference/completed_profiles 不走标准格式
**现象**：这两个 context 块直接用裸文本，不经过 `format_untrusted_context_block()`，`trim_runtime_context_by_priority` 无法识别，在上下文紧张时它们会挤占优先级更高的块。
**状态**：✅ 已修复（修改 8：标准化块格式，并在 UNTRUSTED_CONTEXT_HEADERS 中注册）

---

## 三、已完成的修复（修改 5-10）

| 编号 | 文件 | 内容 | 状态 |
|------|------|------|------|
| 修改 5 | `tools/task_write.py` | 改写复盘分支消息，消除"回顾所有步骤"暗示，加入"不要再调用 task_state"明确指令 | ✅ |
| 修改 6 | `tools/code_session.py` | create_script 返回消息加入 ⚠️ 警告，明确要求调用 run_script | ✅ |
| 修改 7 | `agent/prompts/builder.py` | 系统提示词组件顺序：稳定组件（identity→security→strategy）在前，skills_snapshot 移至末位 | ✅ |
| 修改 8 | `agent/components/context_builder.py` + `agent/prompt_policy.py` | chart_preference/completed_profiles 使用标准 `format_untrusted_context_block` 格式，并在 UNTRUSTED_CONTEXT_HEADERS/RUNTIME_CONTEXT_BLOCK_PRIORITY 中注册 | ✅ |
| 修改 9 | `memory/compression.py` | 轻量摘要增强：tool_result 截断 140→300 字符，max_items 20→30 | ✅ |
| 修改 10 | `memory/compression.py` | LLM 摘要 prompt 新增 ⑥⑦ 两项（任务产出+PDCA 状态），摘要上限 600→800 字 | ✅ |

全部修改已通过 1975 个测试，0 失败。

---

## 四、待实施的优化建议

以下按优先级排序，分三层：**结构性改进**（消除依赖模型服从的缺陷）、**提示词/消息改进**（降低门槛）、**监控与可观测性**。

---

### 层 1：结构性改进（优先级最高）

#### 优化 A：create_script 支持 auto_run 模式（P0）

**问题**：create → run 是两步 API，但"必须执行第二步"的责任完全压在模型文本理解上。

**方案**：在 `create_script` 加入 `auto_run: bool`（默认 `True`）参数。当 `auto_run=True` 时，创建后立即执行，直接返回执行结果。彻底消除 create-without-run 整类问题。

```python
# code_session.py — create_script handler
async def _handle_create_script(self, session, **kwargs):
    auto_run = bool(kwargs.get("auto_run", True))
    # ... 创建脚本逻辑 ...
    if auto_run:
        # 直接执行并返回运行结果
        return await self._handle_run_script(session, script_id=script_id, ...)
    else:
        # 保持现有行为：返回 ⚠️ 警告
        return ToolResult(success=True, message=f"脚本已创建：{script_id}。⚠️ ...")
```

`auto_run=False` 保留供需要先审查代码再执行的场景（目前模型实践中几乎不用）。

**涉及文件**：`src/nini/tools/code_session.py`
**测试**：新增 `test_create_script_auto_run_executes_immediately`

---

#### 优化 B：Session 持久化"未执行脚本"状态，注入 runtime context（P0）

**问题**：即使加了 ⚠️ 警告，压缩后 LLM 丢失了"某个脚本已创建但未执行"的记忆。

**方案**：在 `Session` 中维护 `pending_script_ids: list[str]`（已创建未执行的脚本）。每次 `run_script` 成功后从列表移除。在 `ContextBuilder` 中增加 `pending_scripts` 块，每轮注入到 runtime context。

```python
# 在 Session 中
pending_script_ids: list[str] = []

# 在 ContextBuilder.build_messages_and_retrieval 中
if session.pending_script_ids:
    scripts_desc = "、".join(session.pending_script_ids)
    context_parts.append(
        format_untrusted_context_block(
            "pending_scripts",
            f"以下脚本已创建但尚未执行，请优先运行：{scripts_desc}。"
        )
    )
```

此信息存在 session 结构化字段中，不受压缩影响。

**涉及文件**：`src/nini/agent/session.py`、`src/nini/tools/code_session.py`、`src/nini/agent/components/context_builder.py`、`src/nini/agent/prompt_policy.py`

---

#### 优化 C：task_state noop 返回 `success: false`（P1）

**问题**：noop 检测后替换消息文本，但 `success: true` 字段仍保持，弱模型对字段的信任高于消息文本。

**方案**：连续 noop ≥ 2 时返回 `success: false`，错误码 `TASK_NOOP_LOOP`，使 circuit breaker 接管后续处理。

```python
# agent/runner.py — noop 检测分支
if task_state_noop_repeat_count >= 2:
    result["success"] = False
    result["error_code"] = "TASK_NOOP_LOOP"
    result["message"] = (
        "⚠️ task_state 连续无操作（重复 ≥2 次），已拒绝本次调用。"
        "请立即调用实际分析工具执行当前任务，不要再调用 task_state。"
    )
    has_error = True
```

**涉及文件**：`src/nini/agent/runner.py`
**测试**：更新 `test_task_state_noop_repeat_triggers_warning`

---

#### 优化 D：runtime context 注入当轮工具失败摘要（P1）

**问题**：Harness 检测到工具失败后，这个信息只存在于消息历史中，不在结构化 runtime context 里。被压缩后 LLM 丢失此信息。

**方案**：在 session 中维护 `current_turn_tool_failures: list[ToolFailure]`（每轮重置），ContextBuilder 注入 `tool_failures` 块。

```python
if session.current_turn_tool_failures:
    failures_desc = "\n".join(
        f"- {f.tool_name}：{f.error_message[:80]}"
        for f in session.current_turn_tool_failures
    )
    context_parts.append(
        format_untrusted_context_block(
            "tool_failures",
            f"本轮存在以下工具执行失败，最终总结前必须处理或说明影响：\n{failures_desc}"
        )
    )
```

**涉及文件**：`src/nini/agent/session.py`、`src/nini/agent/components/context_builder.py`、`src/nini/agent/prompt_policy.py`

---

#### 优化 E：沙箱超时按 purpose 区分（P1）

**问题**：60s 统一超时，可视化脚本（多图渲染 + 大数据集聚合）天然慢于统计计算脚本。

**方案**：

```python
# sandbox/policy.py 或 config
SANDBOX_TIMEOUT_BY_PURPOSE: Final[dict[str, int]] = {
    "computation": 30,      # 统计计算
    "visualization": 120,   # 绘图允许更长
    "report": 90,
    "default": 60,
}
```

同时在工具描述中加入提示："数据量 >1000 行时，绘图前建议先聚合或采样（如按小时/天聚合），避免超时"。

**涉及文件**：`src/nini/sandbox/policy.py`（或配置文件）、`src/nini/tools/code_session.py`（工具描述）

---

### 层 2：提示词与消息改进（优先级中）

#### 优化 F：Completion Recovery 提示按失败类型定制（P1）

**问题**：所有校验失败使用相同的恢复提示，弱模型不知道该采取什么具体行动。

**方案**：在 `_build_completion_recovery_prompt` 中按 `missing_actions` 的 key 选择针对性指令：

```python
_RECOVERY_HINTS: Final[dict[str, str]] = {
    "ignored_tool_failures": (
        "存在工具执行失败未被处理。你的最终总结必须明确提及失败步骤及其影响，"
        "或先调用工具重试失败的分析步骤，再输出总结。"
    ),
    "artifact_generated": (
        "你声明了图表已生成，但系统未检测到图表产物事件。"
        "请先调用 code_session(operation='run_script') 执行绘图脚本，再输出总结。"
    ),
    "all_tasks_completed": (
        "仍有未完成的分析任务，请继续执行对应工具，不要提前输出总结。"
    ),
    "not_transitional": (
        "你描述了下一步计划，但尚未执行。请直接调用工具完成分析，再输出总结。"
    ),
}

@staticmethod
def _build_completion_recovery_prompt(completion, *, remaining_tasks=0):
    hints = []
    for item in completion.items:
        if not item.passed and item.key in _RECOVERY_HINTS:
            hints.append(_RECOVERY_HINTS[item.key])
    body = "\n".join(hints) if hints else "请补齐完成条件后重试。"
    prefix = f"还有 {remaining_tasks} 个任务尚未完成。" if remaining_tasks > 0 else ""
    return f"{prefix}请不要结束当前任务。\n{body}"
```

**涉及文件**：`src/nini/harness/runner.py`

---

#### 优化 G：`ignored_tool_failures` 检测改为结构性校验（P1）

**问题**：关键词匹配（"失败"/"报错"）是弱信号，可被绕过，也会误判近义词。

**方案**：改为检测"失败工具后是否有后续成功的工具调用"，作为"已处理"的结构性证据：

```python
# harness/runner.py — CompletionCheckItem ignored_tool_failures
tool_failures = [
    (i, msg) for i, msg in enumerate(messages)
    if msg.get("event_type") == "tool_result" and msg.get("status") == "error"
]
handled = False
if tool_failures:
    last_failure_idx = max(i for i, _ in tool_failures)
    failed_tool_names = {msg.get("tool_name") for _, msg in tool_failures}
    # 检查失败后是否有同类工具的成功调用
    subsequent_success = any(
        msg.get("event_type") == "tool_result"
        and msg.get("status") == "success"
        and msg.get("tool_name") in failed_tool_names
        for msg in messages[last_failure_idx + 1:]
    )
    # 或文本中明确提及失败（扩展词汇表）
    failure_tokens = ("失败", "报错", "error", "未完成", "超时", "无法完成", "未执行")
    text_acknowledged = any(token in final_text.lower() for token in failure_tokens)
    handled = subsequent_success or text_acknowledged

passed = not strict_analysis_mode or not tool_failures or handled
```

**涉及文件**：`src/nini/harness/runner.py`

---

#### 优化 H：修复 `_TRANSITIONAL_TEXT_RE` 行首锚定问题（P2）

**问题**：`^` 锚定只匹配全文开头，Markdown 标题后的过渡段落漏检。

**方案**：改为匹配每个段落开头：

```python
_TRANSITIONAL_TEXT_RE = re.compile(
    r"(?:^|\n)(接下来|下一步|我将|我会继续|我会先|下面将|随后将)",
    re.MULTILINE,
)
```

**涉及文件**：`src/nini/harness/runner.py`

---

#### 优化 I：任务产出摘要注入 runtime context（P2）

**背景**：计划中的"修改 C"，已识别但尚未实施。

**方案**：task_state(update) 的 schema 新增可选 `summary` 字段。LLM 将任务标记为 completed 时可附带一句话总结。ContextBuilder 在 `task_progress` 块中显示每个 completed 任务的 summary。

```python
# task_write.py — schema 新增
{
  "id": 2,
  "status": "completed",
  "summary": "收缩压均值 118.09±10.87 mmHg，无显著异常值"  # 可选
}

# context_builder.py — task_progress 块增强
for t in tasks:
    line = f"  - [{t.status}] {t.title}"
    if t.status == "completed" and t.summary:
        line += f"（{t.summary}）"
```

**涉及文件**：`src/nini/tools/task_write.py`、`src/nini/agent/task_manager.py`、`src/nini/agent/components/context_builder.py`

---

#### 优化 J：code_session 工具描述加入数据量提示（P2）

**方案**：在工具 description 字段中加入：
> "数据量 >1000 行时，绘图前建议先聚合（如按小时/天取均值），避免超时。"

工具 description 不受系统提示词截断影响，是最可靠的常驻提示位置。

**涉及文件**：`src/nini/tools/code_session.py`（工具 schema description）

---

### 层 3：可观测性（优先级低）

#### 优化 K：记录 LLM 摘要成功/失败指标（P2）

**方案**：在 `compress_session_history_with_llm` 中增加 metric 日志：

```python
if summary is not None:
    logger.info("compression: llm_summary=success chars=%d session=%s", len(summary), session_id)
else:
    logger.warning("compression: llm_summary=failed fallback=lightweight session=%s", session_id)
```

有助于了解轻量摘要的实际触发频率，指导后续优化优先级。

**涉及文件**：`src/nini/memory/compression.py`

---

## 五、架构设计原则总结

### 核心诊断

当前系统是**"软约束为主、硬约束为辅"**的混合设计。所有已观察到的失效都发生在软约束侧：

| 机制 | 类型 | 弱模型漏洞 |
|------|------|-----------|
| create_script ⚠️ 警告 | 软约束（文本提示） | 模型以 `success=true` 为准，忽略消息体 |
| task_state noop 消息替换 | 软约束（消息替换） | `success=true` 字段比消息文本更权威 |
| Completion recovery 提示 | 软约束（文本注入） | 弱模型不知道"补齐缺口"的具体行动 |
| Runtime context 块 | 软约束（提示词注入） | 压缩后依赖模型从摘要重建状态 |

### 改进方向：将软约束升级为结构性约束

```
软约束（依赖模型服从）             →  结构性约束（不依赖模型）
─────────────────────────────────────────────────────────────
"⚠️ 请调用 run_script"           →  create_script 直接执行（auto_run）
                                   →  pending_scripts 常驻注入 runtime context
"task_state noop，请调用工具"     →  返回 success=false，circuit breaker 接管
"未忽略失败工具（关键词匹配）"     →  检测失败后是否有后续成功工具调用
"generic recovery 提示"           →  按失败类型注入具体行动指令
"压缩摘要里的工具失败信息"         →  tool_failures 常驻注入 runtime context
60s 统一超时                       →  按 purpose 区分超时限制
```

### 兼容更多模型的关键洞察

> 对较弱的模型，**不应该问"如何让消息更清晰"，而应该问"哪些行为我们能在系统层强制执行"**。

系统已有的硬约束（Dataset IO Guard、Circuit Breaker、Budget Limit）是正确的方向。上述优化 A~E 均是将现有软约束升级为硬约束或结构化状态，不依赖模型的文本理解能力。

---

## 六、实施优先级汇总

| 编号 | 内容 | 优先级 | 工作量 | 依赖 |
|------|------|--------|--------|------|
| 优化 A | create_script auto_run 模式 | P0 | 中 | 无 |
| 优化 B | pending_scripts runtime context | P0 | 中 | Session 改动 |
| 优化 C | task_state noop → success:false | P1 | 小 | 优化 B 无关 |
| 优化 D | tool_failures runtime context 注入 | P1 | 中 | Session 改动 |
| 优化 E | 沙箱超时按 purpose 区分 | P1 | 小 | 无 |
| 优化 F | Completion recovery 按类型定制 | P1 | 小 | 无 |
| 优化 G | ignored_tool_failures 结构性校验 | P1 | 小 | 无 |
| 优化 H | TRANSITIONAL_TEXT_RE 行首锚定修复 | P2 | 极小 | 无 |
| 优化 I | task_state summary 字段 + runtime context | P2 | 大 | task_manager 改动 |
| 优化 J | code_session 工具描述加数据量提示 | P2 | 极小 | 无 |
| 优化 K | LLM 摘要成功/失败日志 | P2 | 极小 | 无 |

**建议实施顺序**：
第一批（高价值低风险）：优化 H → 优化 K → 优化 E → 优化 J → 优化 F → 优化 G → 优化 C
第二批（中等工作量）：优化 A → 优化 B + D（协同改动 Session）
第三批（schema 变更）：优化 I（需评估向前兼容性）

---

*文档由会话分析自动生成，详细代码参见对应 git 提交记录。*
