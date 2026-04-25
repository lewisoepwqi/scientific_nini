# Phase 3 详细设计分析

> 本文档是 `2026-04-13-over-engineering-cleanup.md` Phase 3（Task 12-16）的深度预分析，
> 执行前必须先阅读本文档，并按本文档的修订建议替代原计划中的部分步骤。

---

## 总体风险评级

| Task | 文件 | 行数变化 | 风险 | 是否修订原计划 |
|------|------|---------|------|--------------|
| 12 | `runner.py` run() 拆分 | 不减少总行，run() 从 2355→约 200 行 | **极高** | 是（核心方案调整） |
| 13 | `event_builders.py` 提取辅助函数 | −300 行 | 低 | 否（原计划可行） |
| 14 | `config_manager.py` 拆分 | ≈0（结构重组） | 中 | 轻微调整 |
| 15 | `compression.py` 拆分 | ≈0（结构重组） | 中 | 是（拆分边界调整） |
| 16 | Memory Provider 抽象简化 | −约 100 行 | 低-中 | 否（原计划可行） |

---

## Task 12：拆分 `AgentRunner.run()` 巨型方法

### 现状精确分析

`run()` 方法边界：**lines 428–2783**（约 2355 行）

#### 各段落边界映射

```
428–450   签名 + turn_id + append_user_message
452–467   MemoryManager 惰性初始化（可能抛异常，吞掉继续）
468–475   active_markdown_tools + 图表偏好检测
477–485   中断恢复：重播任务状态（yield build_analysis_plan_event）
487–529   试用模式前置检查（yield TRIAL_EXPIRED + return 或 yield TRIAL_ACTIVATED）
519–529   Contract skill 拦截（async for ... yield ... return）
531–573   主循环状态变量初始化（iteration、tool_failure_chains、pending_* 等 20+ 个变量）
574–582   意图澄清（yield intent clarification events）
584–741   7 个嵌套闭包定义（_build_tool_args_signature 等）
743–747   前置 auto-compress 检查（yield compress_event）
748–2783  主 ReAct while 循环
  748–799   双超时检查（wall_clock + effective_elapsed）
  800–884   消息构建 + tool injection（pending_followup_prompt 等）
  886–1113  LLM 流式请求（inner while True 重试循环）
  1114–1199 Token 追踪 + 过渡性文本重试
  1200–1278 Confirmation fallback（Task 10 已提取为 _handle_confirmation_fallback）
  1280–1358 纯文本回复路径 + done + memory finalization + return
  1360–1442 工具调用入口（assistant 消息追加 + dispatch_agents 拦截）
  1443–1535 循环检测守卫（LoopGuard）
  1535+     per-tool 执行循环（for tc in tool_calls: ...）
  2724–2775 generate_report 最终输出路径
  2775–2783 iteration += 1 + max_iter 超出处理
```

#### 核心障碍：7 个嵌套闭包

lines 584–741 定义的 7 个闭包是拆分的核心挑战：

```
_build_tool_args_signature  → 无外部状态捕获，可提取为静态方法
_to_plan_status             → 无外部状态捕获，可提取为静态方法
_build_plan_progress_payload → 捕获 active_plan（读取）
_new_plan_progress_event    → 捕获 plan_event_seq（nonlocal 写入！）、active_plan、turn_id
_new_analysis_plan_event    → 捕获 plan_event_seq（nonlocal 写入！）、turn_id
_new_plan_step_update_event → 捕获 plan_event_seq（nonlocal 写入！）、turn_id
_new_task_attempt_event     → 捕获 plan_event_seq（nonlocal 写入！）、session、turn_id
```

**关键问题**：4 个闭包都有 `nonlocal plan_event_seq` 写入操作，且 `plan_event_seq` 被用于所有计划事件的序号。这使得这 4 个闭包不能简单提取为类方法（因为它们依赖一个在调用栈上存在的可变变量）。

#### 修订方案：RunState 数据类 + 最小拆分

**原计划方案**（10 个 AsyncGenerator 阶段）的问题：将 `plan_event_seq` 传递给 10 个方法，每次调用后都需要取回更新后的值，形成"乒乓传参"——这比现有的闭包还复杂，且类型不安全。

**推荐方案：RunState 数据类 + 3 个阶段 Generator**

```python
# 新增文件：src/nini/agent/_run_state.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RunState:
    """AgentRunner.run() 跨阶段共享的可变状态容器。"""
    # 计划追踪
    plan_event_seq: int = 0
    active_plan: Any = None   # AnalysisPlan | None
    next_step_idx: int = 0

    # 循环控制
    iteration: int = 0
    message_seq: int = 0
    current_message_id: str | None = None
    tool_followup_retry_used: bool = False
    synthesis_prompt_used: bool = False

    # 注入提示
    pending_followup_prompt: str | None = None
    pending_loop_warn_message: str | None = None
    pending_breaker_fallback_prompt: str | None = None

    # 失败追踪
    tool_failure_chains: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_state_noop_repeat_count: int = 0
    consecutive_tool_failure_count: int = 0

    # 数据去重
    emitted_data_preview_signatures: set[str] = field(default_factory=set)
    successful_dataset_profile_signatures: set[str] = field(default_factory=set)
    dataset_profile_max_view_by_name: dict[str, str] = field(default_factory=dict)

    # 报告
    report_markdown_for_turn: str | None = None

    # 模型信息（跨迭代共享）
    effective_model_info: dict[str, Any] | None = None
    fallback_chain: list[dict[str, Any]] = field(default_factory=list)
```

这样，7 个闭包可以重写为引用 `state.plan_event_seq` 的方法（而非 `nonlocal`），或者更简单地**保留为 `_run_react_loop` 内部的闭包**，只是捕获 `state` 而不是分散的变量。

#### 推荐的 3 段拆分方案

```python
async def run(self, session, user_message, *, ...):
    """主调度器，约 50 行。"""
    turn_id = turn_id or uuid.uuid4().hex[:12]
    if append_user_message:
        session.add_message("user", user_message, turn_id=turn_id)

    # 阶段 1：前置准备（MemoryManager、试用检查、contract skill）
    # 通过 RunState.preloop_complete 标记是否应进入主循环
    state = RunState()
    async for event in self._run_preloop(
        session, user_message, state=state, turn_id=turn_id, stage_override=stage_override
    ):
        yield event
    if not state.preloop_complete:
        return  # 试用到期 / contract skill 消费了请求

    # 阶段 2：主 ReAct 循环
    async for event in self._run_react_loop(
        session, user_message, state=state, turn_id=turn_id,
        stop_event=stop_event, stage_override=stage_override,
    ):
        yield event
```

```python
async def _run_preloop(self, session, user_message, *, state: RunState, turn_id, stage_override):
    """前置准备阶段（约 300 行）：MemoryManager、试用检查、intent 澄清。
    完成后设置 state.preloop_complete = True；早退出时直接 return。
    """
    # MemoryManager 惰性初始化（lines 452-467）
    ...
    # 图表偏好（lines 468-475）
    ...
    # 任务状态重播（lines 477-485）
    yield ...
    # 试用检查（lines 487-529）
    if expired:
        yield trial_expired_event
        return   # 不设置 preloop_complete → run() 中 return
    ...
    # Contract skill 拦截（lines 519-529）
    if contract_invocation:
        async for ev in self._run_contract_markdown_skill(...):
            yield ev
        return   # 不设置 preloop_complete
    # Intent 澄清（lines 574-582）
    async for ev in self._maybe_handle_intent_clarification(...):
        yield ev
    # 成功标记
    state.allowed_tool_whitelist = ...
    state.preloop_complete = True
```

```python
async def _run_react_loop(self, session, user_message, *, state: RunState, turn_id, ...):
    """主 ReAct 循环（约 2000 行 → 保留所有工具执行逻辑）。
    7 个闭包在此处定义，改为捕获 state 而非 nonlocal 变量。
    """
    # 7 个闭包（lines 584-741），改写为：
    def _new_plan_progress_event(...):
        state.plan_event_seq += 1   # 改 nonlocal 为 state. 属性访问
        ...

    # 前置 auto-compress（lines 743-747）
    ...
    # 主 while 循环（lines 748-2783）
    while max_iter <= 0 or state.iteration < max_iter:
        ...
```

**注意**：`_run_react_loop` 依然约 2000 行。这是**预期结果**——它将进一步内部化 `_run_llm_iteration`（LLM 流式子循环，lines 886-1113）和 `_run_tool_dispatch`（per-tool 执行，lines 1535+）作为方法，但这属于第二轮重构，不应在 Task 12 中一次完成。

#### Task 12 实际产出

- `run()` 从 2355 行 → **约 50 行**（纯调度器）
- `_run_preloop()` 约 **300 行**（前置准备）
- `_run_react_loop()` 约 **2000 行**（包含所有主循环逻辑 + 闭包）
- 新增：`src/nini/agent/_run_state.py`（约 50 行）
- **总行数增加约 50 行**，但结构清晰度大幅提升

#### 风险控制

- `RunState` 中的所有字段必须与 `run()` 原有变量同名，以最小化"寻找并替换"的工作量
- 原有 `nonlocal plan_event_seq` 全部改为 `state.plan_event_seq +=`（搜索所有 `nonlocal plan_event_seq` 确保无遗漏）
- 提取 `_run_preloop` 后，测试：直接发送一条普通消息、触发试用到期场景（mock）、触发 contract skill

#### 执行命令（验证）

```bash
# 迁移后必须通过的完整测试套件
pytest tests/ -q --timeout=60
mypy src/nini/agent/runner.py src/nini/agent/_run_state.py
```

---

## Task 13：简化 `event_builders.py`

### 现状精确分析

**44 个 `build_*` 函数**，按结构分类：

**A 类 — 标准型（约 35 个函数）**

函数体 = Pydantic 构造 → `model_dump()` → `data.update(extra)` → `AgentEvent(...)`

典型示例（`build_error_event`, `build_done_event`, `build_session_event` 等）：

```python
def build_error_event(message, code=None, *, turn_id=None, **extra):
    event_data = ErrorEventData(message=message, code=code)
    data = event_data.model_dump()
    data.update(extra)
    return AgentEvent(type=EventType.ERROR, data=data, turn_id=turn_id)
```

这类函数 10-12 行，通过 `_make_event` 可缩为 3-5 行。

**B 类 — 带 metadata 的标准型（约 5 个函数）**

`build_tool_call_event`, `build_tool_result_event` 等需要传入 `metadata` 且 AgentEvent 有额外字段（`tool_call_id`, `tool_name`）：

```python
return AgentEvent(
    type=EventType.TOOL_CALL, data=data, turn_id=turn_id,
    metadata=metadata or {},
    tool_call_id=tool_call_id, tool_name=name,
)
```

这类需要 `_make_event` 的扩展版本，或保持原样。

**C 类 — 特殊型（约 4 个函数，不应修改）**

`build_analysis_plan_event`（lines 58-120）：构建 `AnalysisPlanStep` 对象列表，有复杂前置处理。

`build_reasoning_event`（lines 751-822）：对 `content` 做 LLM 类型检测，有业务逻辑。

`build_token_usage_event`（lines 400-426）：手动组装 `metadata`，格式复杂。

`build_reasoning_data_event`（lines 776-822）：类似复杂度。

### 辅助函数设计（修订原计划）

原计划的 `_make_event` 签名需要细化处理 B 类函数的 `extra_agent_event_kwargs`：

```python
# src/nini/agent/_event_builder_helpers.py
from __future__ import annotations
from typing import Any
from nini.agent.events import AgentEvent, EventType
from pydantic import BaseModel


def _make_event(
    event_type: EventType,
    data_model: BaseModel,
    turn_id: str | None,
    seq: int | None,
    extra: dict[str, Any] | None = None,
    **agent_event_kwargs: Any,
) -> AgentEvent:
    """标准事件构建辅助：Pydantic 模型 → AgentEvent。"""
    data = data_model.model_dump()
    if extra:
        data.update(extra)
    metadata: dict[str, Any] = {}
    if seq is not None:
        metadata["seq"] = seq
    return AgentEvent(
        type=event_type,
        data=data,
        turn_id=turn_id,
        metadata=metadata if metadata else None,
        **agent_event_kwargs,
    )
```

### 函数改写示例

**A 类（最简单）**：
```python
# 原来（10 行）
def build_error_event(message, code=None, *, turn_id=None, **extra):
    event_data = ErrorEventData(message=message, code=code)
    data = event_data.model_dump()
    data.update(extra)
    return AgentEvent(type=EventType.ERROR, data=data, turn_id=turn_id)

# 改后（3 行）
def build_error_event(message, code=None, *, turn_id=None, **extra):
    """构造 ERROR 事件。"""
    return _make_event(EventType.ERROR, ErrorEventData(message=message, code=code), turn_id, None, extra or None)
```

**B 类（带额外 AgentEvent 参数）**：
```python
# 原来（14 行）
def build_tool_call_event(tool_call_id, name, arguments, *, turn_id=None, metadata=None, **extra):
    ...
    return AgentEvent(type=EventType.TOOL_CALL, data=data, turn_id=turn_id,
                      metadata=metadata or {}, tool_call_id=tool_call_id, tool_name=name)

# 改后（4 行）
def build_tool_call_event(tool_call_id, name, arguments, *, turn_id=None, metadata=None, **extra):
    """构造 TOOL_CALL 事件。"""
    parsed_args = _parse_tool_arguments(arguments)  # 提取 JSON 解析为独立函数
    return _make_event(EventType.TOOL_CALL, ToolCallEventData(id=tool_call_id, name=name, arguments=parsed_args),
                       turn_id, None, extra or None, metadata=metadata or {}, tool_call_id=tool_call_id, tool_name=name)
```

### 预计行数

- 原文件：1,216 行
- 标准型 35 个函数：平均节省 6 行/函数 = **−210 行**
- 新增辅助文件 `_event_builder_helpers.py`：约 **+40 行**
- 净减少：约 **170 行**（原计划估算 300 行略偏高，因部分函数不属于最简结构）

### 风险

**极低**。函数签名完全不变，只改函数体内部。只要：
1. 创建辅助文件先通过类型检查（`mypy src/nini/agent/_event_builder_helpers.py`）
2. 逐函数改写并在每次改写后运行测试
3. C 类函数不碰

---

## Task 14：拆分 `config_manager.py`

### 现状精确分析

`config_manager.py` 1081 行，按实际代码结构（非原计划估算）：

```
1–68      模块 imports + 常量（VALID_PROVIDERS 等）
69–143    纯函数（normalize_api_mode, get_default_base_url_for_mode 等）
144–165   ModelPurposeRoute TypedDict + _ensure_app_settings_table（DB 辅助）
167–796   模型配置 CRUD（save_model_config → list_user_configured_provider_ids）
797–864   试用模式（get_trial_status, activate_trial）
865–907   主 Provider 管理（get_active_provider_id, set_active_provider, remove_model_config）
908–1081  内置用量追踪（get_builtin_usage, increment_builtin_usage 等）
```

### 修订拆分方案（调整原计划的目录结构）

原计划创建 `config_parts/` 子包，但这引入了新包边界，所有外部 import 路径都不变（因为 config_manager.py 做 re-export），但维护时需要知道具体文件在哪里。

**建议改为平级文件**（更接近项目已有模式）：

```
src/nini/
├── config_manager.py          ← 保留，变为薄 re-export facade（约 80 行）
├── _config_model_crud.py      ← 模型配置 CRUD（lines 144-796，约 650 行）
├── _config_trial.py           ← 试用模式（lines 797-864，约 70 行）
├── _config_usage.py           ← 内置用量追踪（lines 908-1081，约 175 行）
```

注意：用 `_` 前缀表明这些是内部模块，外部代码应从 `config_manager` 导入，不直接导入 `_config_*`。

**关键约束**：`_ensure_app_settings_table`（line 152）被 `save_model_config`（line 167）调用，必须随 CRUD 代码一起迁移。

### 迁移顺序

1. 先迁移 `_config_usage.py`（最独立，无依赖于其他 config 代码，只依赖 `settings` 和 DB）
2. 再迁移 `_config_trial.py`（依赖 `_ensure_app_settings_table` → 从 `_config_model_crud` 导入）
3. 最后迁移 `_config_model_crud.py`（最大块，依赖 `ModelPurposeRoute` TypedDict）
4. 将 `config_manager.py` 简化为 re-export facade：
   ```python
   from nini._config_model_crud import *     # 或明确列出
   from nini._config_trial import *
   from nini._config_usage import *
   ```

### 外部调用者分析

外部 import 主要来自：
- `api/models_routes.py`（12+ 处 `from nini.config_manager import ...`）
- `agent/model_resolver.py`（6+ 处）
- `agent/runner.py`（1 处 inline import）
- `harness/autoresearch.py`（1 处）

这些 **全部无需修改**，只要 `config_manager.py` 保持完整 re-export。

### 风险

**中等**。主要风险点：
1. `_ensure_app_settings_table` 的迁移归属（建议随 CRUD，在 `_config_model_crud.py` 内部使用，不 re-export）
2. `BUILTIN_PROVIDER_ID` 常量（line 64）被 `model_resolver.py` 直接 import：`from nini.config_manager import BUILTIN_PROVIDER_ID`；需确保 re-export 包含此常量
3. `ModelPurposeRoute` TypedDict 的归属：随 `_config_model_crud.py`，但 `config_manager.py` 需 re-export

---

## Task 15：拆分 `compression.py`

### 现状精确分析

`compression.py` 1337 行，**两大独立关切**：

```
1–779    会话压缩（Session Compression）
  30–74    CompressionSegment 数据类
  76–460   私有辅助函数（_now_ts、_strip_upload_mentions、_summarize_messages、
             _extract_tools_used、_extract_stat_results 等 17 个)
  462–514  try_merge_oldest_segments（公开）
  514–602  _archive_messages、_append_to_search_index（私有）
  603–778  compress_session_history、compress_session_history_with_llm、rollback_compression（公开）

780–1337  分析记忆（Analysis Memory）
  780–793  _analysis_memory_dir、_analysis_memory_path（私有辅助）
  795–1237  Finding、StatisticResult、Decision、Artifact、AnalysisMemory 类
  1236     _analysis_memories 模块级缓存字典
  1239–1337 save/load/get/list/clear CRUD 函数（公开）
```

**两半之间完全没有相互依赖**（会话压缩不引用 AnalysisMemory，AnalysisMemory 不引用压缩函数）。

### 修订拆分方案（调整原计划的三路拆分）

原计划创建 3 个文件（`compression.py` + `analysis_memory.py` + `memory_extraction.py`）。但仔细分析，"提取辅助函数"那半（lines 76-460）与 `compress_session_history` 是不可分的（这些函数只被压缩函数使用）。创建独立的 `memory_extraction.py` 没有实质意义。

**建议改为 2 路拆分**：

```
src/nini/memory/
├── compression.py      ← 保留，只包含会话压缩（lines 1-779，约 780 行）
├── analysis_memory.py  ← 新增，包含 AnalysisMemory（lines 780-1337，约 557 行）
```

**无需 `memory_extraction.py`**：那些私有辅助函数（`_extract_tools_used` 等）只服务于压缩，放在 `compression.py` 中最合适。

### 调用者迁移分析

按函数归属，各调用者需要修改：

**调用分析记忆（Analysis Memory）函数的调用者** — 需更新 import 路径或通过 re-export 兼容：

| 调用者 | 函数 | 迁移后路径 |
|-------|------|-----------|
| `scientific_provider.py` | `list_session_analysis_memories` | `analysis_memory` |
| `long_term_memory.py` | `list_session_analysis_memories`, `save_analysis_memory` | `analysis_memory` |
| `tools/analysis_memory_tool.py` | `list_session_analysis_memories` | `analysis_memory` |
| `tools/collect_artifacts.py` | `list_session_analysis_memories` | `analysis_memory` |
| `tools/statistics/base.py` | `StatisticResult`, `get_analysis_memory` | `analysis_memory` |
| `agent/session.py` line 824 | `clear_session_analysis_memory_cache` | `analysis_memory` |
| `agent/components/context_builder.py` | `list_session_analysis_memories` | `analysis_memory` |

**调用会话压缩函数的调用者** — 不需改动，继续从 `compression` import：

| 调用者 | 函数 |
|-------|------|
| `api/session_routes.py` | `compress_session_history_with_llm`, `compress_session_history`, `rollback_compression` |
| `agent/session.py` lines 566, 645 | `CompressionSegment`, `compress_session_history` |
| `agent/components/context_compressor.py` | `compress_session_history_with_llm` |

**兼容性策略**：在 `compression.py` 底部添加 re-export，使现有 import 零修改：

```python
# compression.py 末尾添加（向后兼容 re-export）
from nini.memory.analysis_memory import (
    Finding,
    StatisticResult,
    Decision,
    Artifact,
    AnalysisMemory,
    save_analysis_memory,
    load_analysis_memory,
    get_analysis_memory,
    remove_analysis_memory,
    list_session_analysis_memories,
    clear_session_analysis_memories,
    clear_session_analysis_memory_cache,
)
```

这样拆分后，所有调用者都不需要修改 import（通过兼容 re-export）。未来可以逐步将调用者迁移到 `analysis_memory`，最终删除 re-export。

### AnalysisMemory 内部自引用

`AnalysisMemory.add_finding()` 方法内部调用 `save_analysis_memory(self)`（line 881），而 `save_analysis_memory` 是同文件的函数。迁移后两者都在 `analysis_memory.py`，无循环引用问题。

### 风险

**低-中**。主要风险：
1. re-export 顺序问题（`compression.py` 导入 `analysis_memory.py`，`analysis_memory.py` 不能反过来导入 `compression.py`）→ 安全，两者无相互依赖
2. 模块级缓存 `_analysis_memories: dict[str, AnalysisMemory]` 必须随 CRUD 函数一起迁移到 `analysis_memory.py`

---

## Task 16：简化 Memory Provider 抽象

### 现状精确分析

```
src/nini/memory/
├── provider.py          ← ABC（60 行）：MemoryProvider(ABC) 有 initialize/prefetch/sync_turn/on_session_end
├── manager.py           ← MemoryManager（185 行）：持有 list[MemoryProvider]，遍历调用
├── scientific_provider.py ← ScientificMemoryProvider(MemoryProvider)（约 290 行）
```

**`manager.py` 当前结构**：
```python
class MemoryManager:
    def __init__(self):
        self._providers: list[MemoryProvider] = []

    def add_provider(self, provider: MemoryProvider) -> None:
        self._providers.append(provider)

    async def initialize_all(self, session_id: str) -> None:
        for p in self._providers:
            await p.initialize(session_id)
    # ... 4 个同类遍历方法
```

**仅有 1 个 Provider 实现**（`ScientificMemoryProvider`），且 `runner.py` 中的初始化代码（lines 452-467）：
```python
_mm = MemoryManager()
_mm.add_provider(ScientificMemoryProvider(db_path=db_path))
await _mm.initialize_all(session.id)
```

### 修订后的简化方案（与原计划一致）

`MemoryManager` 简化为直接持有 `ScientificMemoryProvider`：

```python
class MemoryManager:
    def __init__(self, provider: ScientificMemoryProvider | None = None):
        self._provider = provider

    async def initialize_all(self, session_id: str) -> None:
        if self._provider:
            await self._provider.initialize(session_id)

    async def prefetch(self, session_id: str, user_message: str) -> str:
        if self._provider:
            return await self._provider.prefetch(session_id, user_message)
        return ""
    # ...
```

`runner.py` 中的初始化代码改为：
```python
_mm = MemoryManager(provider=ScientificMemoryProvider(db_path=db_path))
await _mm.initialize_all(session.id)
```

`ScientificMemoryProvider` 删除 `(MemoryProvider)` 继承，保留所有方法。

### 确认无其他 Provider 实现

```bash
grep -r "class.*MemoryProvider\b" src/ --include="*.py"
# Expected: 只有 provider.py 中的 ABC 定义
grep -r "MemoryProvider\)" src/ --include="*.py"
# Expected: 只有 scientific_provider.py
```

### 风险

**低**。唯一注意点：`manager.py` 中 `add_provider()` 方法在 `runner.py` 中被调用，删除后需同步更新 `runner.py`（上面已展示）。

---

## 执行建议

### 推荐执行顺序

```
Task 13（event_builders）← 风险最低，可以热身
    ↓
Task 16（memory provider）← 独立，不影响其他 Task
    ↓
Task 15（compression 拆分）← 有 re-export 保护，影响可控
    ↓
Task 14（config_manager 拆分）← 需仔细 re-export
    ↓
Task 12（runner.py 拆分）← 留到最后，最高风险
```

### 各 Task 独立 Worktree 建议

所有 Phase 3 Task 应在独立 worktree 中执行，分支命名：
- `refactor/event-builders` → Task 13
- `refactor/memory-provider` → Task 16
- `refactor/split-compression` → Task 15
- `refactor/split-config-manager` → Task 14
- `refactor/split-runner-run` → Task 12

### Task 12 特殊说明

在执行 Task 12 之前，**建议先合并 Task 10（extract-approval-handlers）**，因为：
1. Task 10 已将 `_handle_ask_user_question_tool` 和 `_handle_confirmation_fallback` 提取为方法
2. Task 12 拆分 `run()` 时，如果 Task 10 未合并，run() 里面还有那两大段内联代码，增加 `_run_react_loop` 的复杂度
3. 合并顺序：Task 10 → Task 11 → Task 13 → Task 16 → Task 15 → Task 14 → Task 12

---

## 工作量估算（修订）

| Task | 预计代码行变化 | 预计时间 |
|------|-------------|---------|
| 13 | −170 行 | 2-3h |
| 16 | −100 行 | 1-2h |
| 15 | ≈0（2路拆分） | 2-3h |
| 14 | ≈0（3路拆分） | 3-4h |
| 12 | +50 行（新 RunState 文件） | 4-6h |
| **合计** | **−220 行 + 结构改善** | **12-18h** |
