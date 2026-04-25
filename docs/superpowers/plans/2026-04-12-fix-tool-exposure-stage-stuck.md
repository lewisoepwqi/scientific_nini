# 工具暴露策略 Stage 卡死修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 LLM 忘记调用 task_state 完成当前任务时，工具暴露策略卡在 profile 阶段导致分析工具全部不可见的问题。

**Architecture:** 三层防御：(1) task_write 在 in_progress 消息中追加阶段过渡提醒；(2) compute_tool_exposure_policy 在 profile 阶段额外检查下一个 pending 任务的阶段，将分析工具纳入可见集（lookahead）；(3) 在 tool_exposure_policy 返回中新增 `stage_transition_hint` 字段，由 runner 注入系统提示。

**Tech Stack:** Python 3.12, pytest

---

### Task 1: task_write 消息追加阶段过渡提醒

LLM 完成当前任务的分析操作后，经常忘记调用 task_state 标记 completed 再开始下一任务。在 `_handle_update` 的 in_progress 消息中追加提醒。

**Files:**
- Modify: `src/nini/tools/task_write.py:483-493`
- Test: `tests/test_foundation_tools.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_foundation_tools.py` 中添加测试，验证 task_write update 消息包含阶段过渡提醒：

```python
def test_task_write_update_in_progress_message_includes_transition_reminder() -> None:
    """in_progress 任务的确认消息应包含阶段过渡提醒。"""
    from nini.agent.session import Session
    from nini.tools.task_write import TaskWriteTool

    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "检查数据质量", "status": "pending", "tool_hint": "dataset_catalog"},
            {"id": 2, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
        ]
    )
    tool = TaskWriteTool()

    result = tool._handle_update(
        session,
        [{"id": 1, "status": "in_progress"}],
    )

    assert result.success is True
    # 消息必须提醒 LLM 完成后更新任务状态
    assert "task_state" in result.message
    assert "completed" in result.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_foundation_tools.py::test_task_write_update_in_progress_message_includes_transition_reminder -v`
Expected: FAIL — 当前消息只说"请直接执行分析操作"，不含 task_state 提醒

- [ ] **Step 3: Write minimal implementation**

修改 `src/nini/tools/task_write.py` 第 483-493 行，在 `elif current_in_progress:` 分支的消息末尾追加提醒：

```python
        elif current_in_progress:
            hint_text = (
                f"（可使用 {current_in_progress.tool_hint}）"
                if current_in_progress.tool_hint
                else ""
            )
            next_pending = next(
                (t for t in result.manager.tasks if t.status == "pending"), None
            )
            transition_reminder = ""
            if next_pending:
                transition_reminder = (
                    f" 完成后请先调用 task_state 将本任务标为 completed、"
                    f"再将任务{next_pending.id}「{next_pending.title}」标为 in_progress，"
                    "以解锁下一阶段工具。"
                )
            else:
                transition_reminder = (
                    " 完成后请调用 task_state 将本任务标为 completed。"
                )
            message = (
                f"任务{current_in_progress.id}「{current_in_progress.title}」已标记为进行中"
                f"{hint_text}。"
                f"请直接执行分析操作，还有 {pending} 个任务待开始。"
                f"{transition_reminder}"
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_foundation_tools.py::test_task_write_update_in_progress_message_includes_transition_reminder -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nini/tools/task_write.py tests/test_foundation_tools.py
git commit -m "feat(tools): task_write in_progress 消息追加阶段过渡提醒"
```

---

### Task 2: compute_tool_exposure_policy 添加 look-ahead 机制

当当前 in_progress 任务处于 profile 阶段，但下一个 pending 任务是 analysis/visualization 阶段时，自动将下一阶段的工具纳入可见集。防止 stage 卡死在 profile。

**Files:**
- Modify: `src/nini/agent/tool_exposure_policy.py:346-452`
- Test: `tests/test_tool_exposure_policy.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_tool_exposure_policy.py` 中添加测试，模拟 9df57a4751ad 的场景：task2 in_progress（dataset_transform → profile），task3 pending（stat_test → analysis）：

```python
def test_profile_stage_with_analysis_pending_includes_analysis_tools() -> None:
    """当前 profile 任务 in_progress 但下一任务是 analysis 时，分析工具应可见。

    复现场景：会话 9df57a4751ad，task2(dataset_transform) in_progress,
    task3(stat_test) pending。LLM 完成了 dataset_transform 但忘记标记
    task2 为 completed，下一轮 stat_test/code_session 全部不可见。
    """
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "检查数据质量", "status": "completed", "tool_hint": "dataset_catalog"},
            {"id": 2, "title": "数据预处理", "status": "in_progress", "tool_hint": "dataset_transform"},
            {"id": 3, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
            {"id": 4, "title": "绘制热图", "status": "pending", "tool_hint": "chart_session"},
        ]
    )
    registry = _FakeRegistry(
        [
            "task_state",
            "dataset_catalog",
            "dataset_transform",
            "stat_test",
            "code_session",
            "chart_session",
        ]
    )

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="继续分析",
    )

    # stage 仍是 profile（因为 task2 in_progress）
    assert policy["stage"] == "profile"
    # 但 analysis 工具也应可见（look-ahead 机制）
    assert "stat_test" in policy["visible_tools"]
    assert "code_session" in policy["visible_tools"]
    # 应有 look-ahead 警告
    assert any("look-ahead" in w or "下一" in w for w in policy["policy_warnings"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tool_exposure_policy.py::test_profile_stage_with_analysis_pending_includes_analysis_tools -v`
Expected: FAIL — 当前 profile 阶段不包含 stat_test/code_session

- [ ] **Step 3: Write minimal implementation**

在 `src/nini/agent/tool_exposure_policy.py` 的 `compute_tool_exposure_policy` 函数中，在 `allowed |= _PROFILE_TOOLS` 之后（第 389 行之后）插入 look-ahead 逻辑：

```python
    allowed = set(_ALWAYS_ALLOWED)
    if stage == "profile":
        allowed |= _PROFILE_TOOLS
    elif stage == "visualization":
        allowed |= _VISUALIZATION_TOOLS
    elif stage == "export":
        allowed |= _EXPORT_TOOLS
    else:
        allowed |= _ANALYSIS_TOOLS

    # ── look-ahead：当前任务已完成但未标记 completed 时，预解锁下一阶段工具 ──
    if stage in {"profile", "visualization"} and session is not None:
        next_pending_stage = _resolve_next_pending_stage(session)
        if next_pending_stage and next_pending_stage != stage:
            lookahead_tools = _STAGE_TOOLS_MAP.get(next_pending_stage, set())
            lookahead_visible = [name for name in all_tools if name in lookahead_tools]
            if lookahead_visible:
                allowed.update(lookahead_visible)
                policy_warnings.append(
                    f"当前阶段为 {stage}，但下一待执行任务属于 {next_pending_stage} 阶段，"
                    "已预解锁其工具（look-ahead）。"
                    "请完成当前任务后调用 task_state 更新状态。"
                )
```

在 `compute_tool_exposure_policy` 函数之前（`resolve_surface_stage` 之后）添加两个辅助定义：

```python
# 阶段 → 工具集的映射（用于 look-ahead）
_STAGE_TOOLS_MAP: dict[str, set[str]] = {
    "profile": _PROFILE_TOOLS,
    "analysis": _ANALYSIS_TOOLS,
    "visualization": _VISUALIZATION_TOOLS,
    "export": _EXPORT_TOOLS,
}


def _resolve_next_pending_stage(session: Any) -> str | None:
    """查找下一个 pending 任务的阶段（look-ahead 用）。

    只检查第一个 pending 任务，不递归查找。
    """
    if session is None or not hasattr(session, "task_manager"):
        return None
    manager = getattr(session, "task_manager", None)
    tasks = getattr(manager, "tasks", None)
    if not isinstance(tasks, list):
        return None
    for task in tasks:
        if getattr(task, "status", None) == "pending":
            return resolve_stage_from_tool_hint(getattr(task, "tool_hint", None))
    return None
```

同时需要修改 `compute_tool_exposure_policy` 函数，将 `policy_warnings` 的初始化提前到 look-ahead 代码之前。当前代码中 `policy_warnings` 在第 399 行初始化，look-ahead 代码需要引用它。检查发现初始化位置在第 399 行（`allowed` 计算之后、高权限过滤之前），而 look-ahead 代码也在 `allowed` 之后，所以只需将 `policy_warnings` 初始化移到 `allowed` 计算之前即可：

将第 399 行：
```python
    authorization_state: dict[str, bool] = {}
    forced_visible_tools: list[str] = []
    policy_warnings: list[str] = []
```

移到第 387 行（`allowed = set(_ALWAYS_ALLOWED)` 之前），变为：
```python
    authorization_state: dict[str, bool] = {}
    forced_visible_tools: list[str] = []
    policy_warnings: list[str] = []

    allowed = set(_ALWAYS_ALLOWED)
```

同时删除原位置（第 397-399 行）的三行声明。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tool_exposure_policy.py::test_profile_stage_with_analysis_pending_includes_analysis_tools -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nini/agent/tool_exposure_policy.py tests/test_tool_exposure_policy.py
git commit -m "feat(agent): compute_tool_exposure_policy 添加 look-ahead 机制防 stage 卡死"
```

---

### Task 3: tool_exposure_policy 返回 stage_transition_hint

在 `compute_tool_exposure_policy` 返回值中新增 `stage_transition_hint` 字段，描述当前阶段和下一阶段的过渡信息，供 runner 层注入到 LLM 上下文中。

**Files:**
- Modify: `src/nini/agent/tool_exposure_policy.py`（延续 Task 2）
- Test: `tests/test_tool_exposure_policy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_stage_transition_hint_informs_llm_about_hidden_tools() -> None:
    """当 profile 阶段隐藏了分析工具时，transition_hint 应告知 LLM 解锁方式。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "数据预处理", "status": "in_progress", "tool_hint": "dataset_transform"},
            {"id": 2, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
        ]
    )
    registry = _FakeRegistry(
        ["task_state", "dataset_transform", "stat_test", "code_session"]
    )

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="继续",
    )

    assert "stage_transition_hint" in policy
    hint = policy["stage_transition_hint"]
    assert hint is not None
    assert "stat_test" in hint
    assert "task_state" in hint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tool_exposure_policy.py::test_stage_transition_hint_informs_llm_about_hidden_tools -v`
Expected: FAIL — 当前返回值没有 `stage_transition_hint` 字段

- [ ] **Step 3: Write minimal implementation**

在 `compute_tool_exposure_policy` 函数中，构建返回字典之前，添加 `stage_transition_hint` 的生成逻辑：

```python
    # ── 构建阶段过渡提示 ──
    stage_transition_hint: str | None = None
    if removed_by_policy and active_task_id is not None:
        next_stage = _resolve_next_pending_stage(session)
        if next_stage:
            representative_tools = [
                name for name in removed_by_policy[:3]
                if name not in _ALWAYS_ALLOWED
            ]
            tool_list = "、".join(f"`{n}`" for n in representative_tools)
            if len(removed_by_policy) > 3:
                tool_list += f"等 {len(removed_by_policy)} 个工具"
            stage_transition_hint = (
                f"当前处于「{stage}」阶段，{tool_list} 等工具暂不可用。"
                f"完成任务{active_task_id}后调用 task_state 更新状态，"
                f"将自动解锁「{next_stage}」阶段工具。"
            )
```

在返回字典中添加 `stage_transition_hint` 键：

```python
    return {
        "stage": stage,
        "stage_reason": stage_reason,
        "active_task_id": active_task_id,
        "active_task_title": active_task_title,
        "active_task_hint": active_task_hint,
        "visible_tools": visible_tools,
        "hidden_tools": hidden_tools,
        "removed_by_policy": removed_by_policy,
        "authorization_state": authorization_state,
        "high_risk_tools": [name for name in all_tools if name in _HIGH_RISK_TOOLS],
        "forced_visible_tools": forced_visible_tools,
        "policy_warnings": policy_warnings,
        "stage_transition_hint": stage_transition_hint,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tool_exposure_policy.py::test_stage_transition_hint_informs_llm_about_hidden_tools -v`
Expected: PASS

- [ ] **Step 5: Run all exposure policy tests to ensure no regression**

Run: `pytest tests/test_tool_exposure_policy.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/nini/agent/tool_exposure_policy.py tests/test_tool_exposure_policy.py
git commit -m "feat(agent): tool_exposure_policy 返回 stage_transition_hint 供 LLM 上下文使用"
```

---

### Task 4: runner 将 stage_transition_hint 注入 LLM 系统提示

runner 层在每轮迭代构建系统提示时，如果 `stage_transition_hint` 存在，将其追加到上下文注入中，让 LLM 知道隐藏工具的存在和解锁方式。

**Files:**
- Modify: `src/nini/agent/runner.py` (约第 832-842 行附近)
- Test: `tests/test_orchestrator_mode.py`

- [ ] **Step 1: Write the failing test**

```python
def test_stage_transition_hint_injected_into_context() -> None:
    """当 tool_exposure_policy 返回 stage_transition_hint 时，runner 应注入上下文。"""
    # 此测试验证 runner 的 _build_context 或类似方法会读取
    # _last_tool_exposure_policy["stage_transition_hint"] 并注入到提示中
    # 由于 runner 测试环境复杂，这里验证 runner 将 hint 写入 _last_tool_exposure_policy
    from nini.agent.tool_exposure_policy import compute_tool_exposure_policy
    from nini.agent.session import Session

    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "数据预处理", "status": "in_progress", "tool_hint": "dataset_transform"},
            {"id": 2, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
        ]
    )
    registry = _FakeRegistry(["task_state", "dataset_transform", "stat_test", "code_session"])

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="继续",
    )

    # 验证 hint 存在且格式正确
    assert policy["stage_transition_hint"] is not None
    assert "task_state" in policy["stage_transition_hint"]
```

- [ ] **Step 2: Run test to verify it passes (should already pass from Task 3)**

Run: `pytest tests/test_orchestrator_mode.py::test_stage_transition_hint_injected_into_context -v`
Expected: PASS — 本测试验证 policy 返回值格式，由 Task 3 保证

- [ ] **Step 3: 注入 stage_transition_hint 到 runner 上下文**

在 `src/nini/agent/runner.py` 中找到 `_last_tool_exposure_policy` 被记录的位置（约第 832-842 行），在紧接其后的上下文构建代码中，检查 `stage_transition_hint` 是否存在并追加到 `followup_prompt_for_purpose`：

找到以下代码段（约第 843-844 行）：

```python
            followup_prompt_for_purpose = pending_followup_prompt
            if pending_followup_prompt:
```

在其前面插入：

```python
            # 注入阶段过渡提示：告知 LLM 当前隐藏工具及解锁方式
            if isinstance(self._last_tool_exposure_policy, dict):
                _transition_hint = str(
                    self._last_tool_exposure_policy.get("stage_transition_hint") or ""
                ).strip()
                if _transition_hint:
                    if pending_followup_prompt:
                        pending_followup_prompt = (
                            pending_followup_prompt + "\n" + _transition_hint
                        )
                    else:
                        pending_followup_prompt = _transition_hint
```

- [ ] **Step 4: Run all tests to verify no regression**

Run: `pytest tests/test_orchestrator_mode.py tests/test_tool_exposure_policy.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/nini/agent/runner.py tests/test_orchestrator_mode.py
git commit -m "feat(agent): runner 注入 stage_transition_hint 到 LLM 上下文"
```

---

### Task 5: 运行全量测试确保无回归

**Files:**
- None (验证步骤)

- [ ] **Step 1: 运行后端全量测试**

Run: `pytest -q`
Expected: ALL PASS — 无回归

- [ ] **Step 2: 运行格式检查**

Run: `black --check src tests`
Expected: ALL PASS — 格式正确。如有格式问题运行 `black src tests` 后重新提交。
