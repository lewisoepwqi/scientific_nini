# Fix dispatch_agents tasks 参数丢失 + 静默失败 + transform 错误提示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复三个问题：P0——`_handle_dispatch_agents` 忽略 `tasks`/`wave_id` 参数导致每次派发 agent_count=0；P1——`dispatch_agents` 空任务时返回静默 success 应改为明确错误；P2——`dataset_transform` lambda 报错的 `recovery_hint` 未引导到 `code_session`。

**Architecture:** 三个独立改动，互不依赖，各自覆盖失败测试 → 最小修改 → 验证。P0 改 `runner.py` 一行参数提取 + 三行 execute 调用；P1 改 `dispatch_agents.py` 空判断分支；P2 改 `dataset_transform.py` 两条错误字符串。

**Tech Stack:** Python 3.12, pytest, pytest-asyncio (`asyncio_mode = "auto"`)

---

## 涉及文件

| 文件 | 修改原因 |
|------|---------|
| `src/nini/agent/runner.py:4079,4125-4130` | P0：提取 `tasks`/`wave_id` 并透传给 `skill.execute()` |
| `src/nini/tools/dispatch_agents.py:178-181` | P1：空任务返回错误而非静默成功 |
| `src/nini/tools/dataset_transform.py:918-925` | P2：lambda 报错的 `recovery_hint` 和 `minimal_example` |
| `tests/test_orchestrator_mode.py` | P0 新增：`tasks` 格式走通的集成测试 |
| `tests/test_dispatch_agents.py` | P1：更新空任务断言 + P0 新增 `tasks` 格式单元测试 |
| `tests/test_foundation_tools.py` | P2 新增：lambda 报错含 `code_session` 引导的测试 |

---

## Task 1 (P0)：修复 `_handle_dispatch_agents` 丢失 `tasks`/`wave_id` 参数

**根本原因**：`runner.py:4079` 只读 `agents`，LLM 实际发送的 `tasks=[...]` 被丢弃，`skill.execute()` 收到 `agents=[]`，走空列表提前返回路径（agent_count=0）。

**Files:**
- Modify: `tests/test_orchestrator_mode.py`
- Modify: `src/nini/agent/runner.py:4079-4130`

- [ ] **Step 1: 写失败测试——`tasks` 格式触发真实派发**

在 `tests/test_orchestrator_mode.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_handle_dispatch_agents_passes_tasks_format():
    """_handle_dispatch_agents 应正确透传 tasks=[...] 格式给 skill.execute，
    使 agent_count > 0 而非静默返回 0。"""
    from nini.agent.events import EventType

    runner = _make_runner_with_dispatch_registered()
    sub_session = _make_sub_session()

    dispatch_tc = {
        "id": "call-tasks-001",
        "function": {
            "name": "dispatch_agents",
            "arguments": '{"tasks": [{"task_id": 1, "agent_id": "literature_search", "task": "执行检索"}]}',
        },
    }

    events = []
    async for evt in runner._handle_dispatch_agents(dispatch_tc, sub_session, "turn-t01"):
        events.append(evt)

    tool_result_event = next(
        (e for e in events if getattr(e, "type", None) == EventType.TOOL_RESULT), None
    )
    assert tool_result_event is not None
    result_payload = tool_result_event.data["data"]["result"]["metadata"]
    assert result_payload["agent_count"] == 1, (
        f"期望 agent_count=1，实际 {result_payload['agent_count']}。"
        "runner.py 可能未将 tasks 透传给 skill.execute()。"
    )
    assert result_payload["success_count"] == 1


@pytest.mark.asyncio
async def test_handle_dispatch_agents_passes_wave_id():
    """wave_id 字段应从 func_args 透传给 skill.execute，出现在 metadata 中。"""
    from nini.agent.events import EventType

    runner = _make_runner_with_dispatch_registered()
    sub_session = _make_sub_session()

    dispatch_tc = {
        "id": "call-wave-001",
        "function": {
            "name": "dispatch_agents",
            "arguments": '{"wave_id": "wave-abc", "agents": [{"agent_id": "literature_search", "task": "检索"}]}',
        },
    }

    events = []
    async for evt in runner._handle_dispatch_agents(dispatch_tc, sub_session, "turn-w01"):
        events.append(evt)

    tool_result_event = next(
        (e for e in events if getattr(e, "type", None) == EventType.TOOL_RESULT), None
    )
    assert tool_result_event is not None
    result_payload = tool_result_event.data["data"]["result"]["metadata"]
    assert result_payload.get("wave_id") == "wave-abc"
```

- [ ] **Step 2: 运行确认两个新测试都失败**

```bash
pytest tests/test_orchestrator_mode.py::test_handle_dispatch_agents_passes_tasks_format tests/test_orchestrator_mode.py::test_handle_dispatch_agents_passes_wave_id -v
```

期望：FAILED（agent_count=0，因为 tasks 未被传入）

- [ ] **Step 3: 修改 `runner.py` — 提取三个参数并透传**

找到 `src/nini/agent/runner.py:4079` 的这一行：

```python
        agents_list: list[dict] = func_args.get("agents", [])
```

替换为：

```python
        agents_list: list[dict] | None = func_args.get("agents") or None
        tasks_list: list[dict] | None = func_args.get("tasks") or None
        wave_id_val: str | None = func_args.get("wave_id") or None
```

再找到 `runner.py:4125-4130` 的 `skill.execute(...)` 调用：

```python
            skill_result = await skill.execute(
                session,
                agents=agents_list,
                turn_id=turn_id,
                tool_call_id=tc_id,
            )
```

替换为：

```python
            skill_result = await skill.execute(
                session,
                agents=agents_list,
                tasks=tasks_list,
                wave_id=wave_id_val,
                turn_id=turn_id,
                tool_call_id=tc_id,
            )
```

- [ ] **Step 4: 运行新增测试，确认通过**

```bash
pytest tests/test_orchestrator_mode.py::test_handle_dispatch_agents_passes_tasks_format tests/test_orchestrator_mode.py::test_handle_dispatch_agents_passes_wave_id -v
```

期望：PASSED

- [ ] **Step 5: 运行 orchestrator_mode 全量测试，确认无回归**

```bash
pytest tests/test_orchestrator_mode.py -v
```

期望：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/nini/agent/runner.py tests/test_orchestrator_mode.py
git commit -m "fix(agent): _handle_dispatch_agents 透传 tasks/wave_id 参数，修复 tasks 格式被忽略导致 agent_count=0 的问题"
```

---

## Task 2 (P1)：`dispatch_agents` 空任务返回明确错误而非静默 success

**根本原因**：`dispatch_agents.py:178-181` 在 `task_specs=[]` 时返回 `success=True, message=""`，LLM 收到成功响应但没有任何 Agent 被启动，无法感知错误，导致多次重试。

**Files:**
- Modify: `tests/test_dispatch_agents.py`
- Modify: `src/nini/tools/dispatch_agents.py:178-181`

- [ ] **Step 1: 更新两个空任务测试——改为断言 success=False**

在 `tests/test_dispatch_agents.py` 中找到 `test_execute_empty_agents_returns_empty` 和 `test_execute_none_agents_treated_as_empty`，替换为：

```python
@pytest.mark.asyncio
async def test_execute_empty_agents_returns_error():
    """agents=[] 且 tasks 未提供时，应返回 success=False 并给出明确错误，
    不能静默返回 success=True（会让 LLM 误以为派发成功）。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=spawner)
    result = await tool.execute(None, agents=[])
    assert result.success is False
    assert result.metadata["error_code"] == "DISPATCH_AGENTS_NO_TASKS"
    assert result.metadata["agent_count"] == 0
    assert spawner.spawn_batch_calls == []


@pytest.mark.asyncio
async def test_execute_none_agents_and_no_tasks_returns_error():
    """agents=None 且 tasks 未提供时，同样返回 success=False。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=spawner)
    result = await tool.execute(None, agents=None)
    assert result.success is False
    assert result.metadata["error_code"] == "DISPATCH_AGENTS_NO_TASKS"
    assert spawner.spawn_batch_calls == []
```

同时，在同一文件末尾追加一个"提供了 tasks 不为空"的正向对比测试：

```python
@pytest.mark.asyncio
async def test_execute_tasks_format_dispatches_correctly():
    """tasks=[{task_id, agent_id, task}] 格式应正常派发，不走空列表分支。"""
    spawner = _MockSpawner(results=[
        SubAgentResult(agent_id="literature_search", success=True, summary="检索完成")
    ])
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=spawner)
    result = await tool.execute(
        None,
        tasks=[{"task_id": 1, "agent_id": "literature_search", "task": "执行检索"}],
    )
    assert result.success is True
    assert result.metadata["agent_count"] == 1
    assert len(spawner.spawn_batch_calls) == 1
```

- [ ] **Step 2: 运行更新后的测试，确认它们现在失败**

```bash
pytest tests/test_dispatch_agents.py::test_execute_empty_agents_returns_error tests/test_dispatch_agents.py::test_execute_none_agents_and_no_tasks_returns_error -v
```

期望：FAILED（当前 success=True，断言 success=False 失败）

- [ ] **Step 3: 修改 `dispatch_agents.py` — 空 task_specs 返回错误**

找到 `src/nini/tools/dispatch_agents.py:178-181`：

```python
        # 空列表快速返回
        if not task_specs:
            return ToolResult(
                success=True, message="", metadata={"agent_count": 0, "wave_id": wave_id}
            )
```

替换为：

```python
        # 空任务列表：agents 和 tasks 均为空，视为参数错误
        if not task_specs:
            return ToolResult(
                success=False,
                message=(
                    "dispatch_agents 未收到任何任务：agents 和 tasks 均为空或未提供。"
                    "请使用 tasks=[{task_id, agent_id, task}] 格式指定至少一个任务。"
                ),
                metadata={"error_code": "DISPATCH_AGENTS_NO_TASKS", "agent_count": 0, "wave_id": wave_id},
            )
```

- [ ] **Step 4: 运行所有 dispatch_agents 测试，确认通过且无回归**

```bash
pytest tests/test_dispatch_agents.py -v
```

期望：全部 PASSED。注意：`test_execute_tasks_format_dispatches_correctly` 也应通过。

- [ ] **Step 5: 运行 orchestrator_mode 测试，确认 P0 修复与 P1 修复兼容**

```bash
pytest tests/test_orchestrator_mode.py -v
```

期望：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/nini/tools/dispatch_agents.py tests/test_dispatch_agents.py
git commit -m "fix(tools): dispatch_agents 空任务列表返回明确错误，避免 LLM 静默误认为派发成功"
```

---

## Task 3 (P2)：`dataset_transform` lambda 报错引导到 `code_session`

**根本原因**：`dataset_transform.py:921` lambda 报错的 `recovery_hint` 写的是"请改写为列运算"，未提示 `code_session` 才是多条件分类的正确工具，导致 LLM 走弯路（尝试用 dispatch_agents 代劳）。

**Files:**
- Modify: `tests/test_foundation_tools.py`
- Modify: `src/nini/tools/dataset_transform.py:916-925`

- [ ] **Step 1: 写失败测试——lambda 报错的 recovery_hint 和 minimal_example 应引导到 code_session**

在 `tests/test_foundation_tools.py` 中 `test_dataset_transform_rejects_df_variable_in_expr_with_guidance` 之后追加：

```python
def test_dataset_transform_rejects_lambda_with_code_session_guidance() -> None:
    """lambda 表达式被拒绝时，recovery_hint 应明确引导用户改用 code_session，
    minimal_example 应展示 code_session 中 pd.cut 的用法。"""
    registry = create_default_tool_registry()
    session = Session()
    session.datasets["raw"] = pd.DataFrame({"小时": [1, 8, 14, 21]})

    result = asyncio.run(
        registry.execute(
            "dataset_transform",
            session=session,
            operation="run",
            dataset_name="raw",
            steps=[
                {
                    "id": "derive_period",
                    "op": "derive_column",
                    "params": {
                        "column": "时间段",
                        "expr": "小时.apply(lambda h: '早晨' if 6 <= h < 12 else '其他')",
                    },
                }
            ],
        )
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "DATASET_TRANSFORM_EXPR_LAMBDA_UNSUPPORTED"
    # recovery_hint 必须明确引导 code_session
    assert "code_session" in result["data"]["recovery_hint"], (
        f"recovery_hint 应提到 code_session，实际: {result['data']['recovery_hint']}"
    )
    # minimal_example 应展示 pd.cut 或 np.select 的具体用法
    assert "pd.cut" in result["data"]["minimal_example"] or "np.select" in result["data"]["minimal_example"], (
        f"minimal_example 应包含 pd.cut 或 np.select，实际: {result['data']['minimal_example']}"
    )
```

- [ ] **Step 2: 运行确认测试失败**

```bash
pytest "tests/test_foundation_tools.py::test_dataset_transform_rejects_lambda_with_code_session_guidance" -v
```

期望：FAILED（当前 recovery_hint 不含 `code_session`，minimal_example 不含 `pd.cut`/`np.select`）

- [ ] **Step 3: 修改 `dataset_transform.py` — 更新 lambda 报错的两个字符串**

找到 `src/nini/tools/dataset_transform.py:916-925`：

```python
            if isinstance(node, ast.Lambda):
                raise DatasetTransformValidationError(
                    "表达式不支持 lambda",
                    error_code="DATASET_TRANSFORM_EXPR_LAMBDA_UNSUPPORTED",
                    expected_params=["expr"],
                    recovery_hint="请改写为列运算、布尔表达式或拆成多步处理。",
                    minimal_example='{"column":"白天标志","expr":"(小时 >= 6) & (小时 < 22)"}',
                    step_id=step_id,
                    op=op,
                )
```

替换为：

```python
            if isinstance(node, ast.Lambda):
                raise DatasetTransformValidationError(
                    "表达式不支持 lambda",
                    error_code="DATASET_TRANSFORM_EXPR_LAMBDA_UNSUPPORTED",
                    expected_params=["expr"],
                    recovery_hint=(
                        "lambda 需要逐行执行自由 Python，请改用 code_session 并传入 dataset_name。"
                        "多条件分类示例：df['时间段'] = pd.cut(df['小时'], bins=[0,6,12,18,24], "
                        "labels=['夜间','早晨','下午','晚上'], right=False)"
                    ),
                    minimal_example=(
                        "code_session 中: df['时间段'] = pd.cut(df['小时'], "
                        "bins=[0,6,12,18,24], labels=['夜间','早晨','下午','晚上'], right=False)"
                    ),
                    step_id=step_id,
                    op=op,
                )
```

- [ ] **Step 4: 运行新增测试，确认通过**

```bash
pytest "tests/test_foundation_tools.py::test_dataset_transform_rejects_lambda_with_code_session_guidance" -v
```

期望：PASSED

- [ ] **Step 5: 运行 dataset_transform 相关全量测试，确认无回归**

```bash
pytest tests/test_foundation_tools.py -k "dataset_transform" -v
```

期望：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/nini/tools/dataset_transform.py tests/test_foundation_tools.py
git commit -m "fix(tools): dataset_transform lambda 报错 recovery_hint 引导到 code_session 并给出 pd.cut 示例"
```

---

## 最终验证

- [ ] **运行三个改动文件的全量测试**

```bash
pytest tests/test_orchestrator_mode.py tests/test_dispatch_agents.py tests/test_foundation_tools.py -v
```

期望：全部 PASSED，无任何 FAILED 或 ERROR。

- [ ] **运行完整测试套件，确认无跨模块回归**

```bash
pytest -q
```

期望：无新增失败。

---

## 自检

**Spec 覆盖：**
- P0 (`tasks`/`wave_id` 丢失) → Task 1 完整覆盖
- P1 (静默 success) → Task 2 完整覆盖（含已有测试更新）
- P2 (recovery_hint 未引导 code_session) → Task 3 完整覆盖

**类型/命名一致性：**
- `agents_list: list[dict] | None`，`tasks_list: list[dict] | None`，`wave_id_val: str | None` — 与 `skill.execute()` 签名一致（`agents`, `tasks`, `wave_id` 均为 `... | None`）
- `DISPATCH_AGENTS_NO_TASKS` error_code 在 P1 的测试和实现中保持一致

**Placeholder 检查：** 无 TBD / TODO / "类似上面" 等占位。
