# task_state 循环与降级兜底修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复会话 `2dfc01fe2a83` 暴露的 task_state 死循环（自相矛盾指令 + 阈值错位 + 终止无兜底），让 FORCE_STOP 不再让用户"白跑"。

**Architecture:** 四层收敛：(1) `task_write.py` 最后任务分支改为"隐式自动完成"语义，消除"先 call 工具再总结"的两步指令；(2) runner 在 turn 结束时把 last in_progress 任务自动置 completed；(3) task_state 专属熔断阈值前移至 LoopGuard FORCE_STOP 之前，让更信息丰富的降级先触发；(4) FORCE_STOP 时从 `session.messages` 抓最近 artifact 与成功 tool stdout，合成兜底总结文本再 yield。

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, pydantic v2。

**前置：** 在 `fix/task-state-loop-and-graceful-fallback` 分支执行（已切出），单 PR 提交。

---

## 文件结构

| 文件 | 角色 | 动作 |
|---|---|---|
| `src/nini/tools/task_write.py` | task_state 工具 | 修改：最后任务分支消息改为"不要再调用 task_state，直接输出总结"；设置 `session.task_manager_pending_auto_complete_id` |
| `src/nini/agent/session.py` | Session 状态 | 修改：新增属性 `pending_auto_complete_task_id: int | None` |
| `src/nini/agent/runner.py` | Agent runner | 修改：(a) 阈值调整；(b) turn 结束前 hook 自动完成 last in_progress；(c) FORCE_STOP 分支调用 fallback summary |
| `src/nini/agent/loop_guard.py` | 循环守卫 | 修改：`hard_limit=6`（默认），避免抢跑 task_state L3 |
| `src/nini/utils/fallback_summary.py` | 降级兜底 | 新建：`build_fallback_summary(messages, user_request) -> str \| None` |
| `tests/test_task_write_last_task_message.py` | task_write 最后任务测试 | 新建 |
| `tests/test_runner_turn_auto_complete.py` | turn-end auto-complete 测试 | 新建 |
| `tests/test_loop_guard.py` | LoopGuard 测试 | 修改：hard_limit 默认值断言 |
| `tests/test_fallback_summary.py` | fallback summary 工具测试 | 新建 |
| `tests/test_runner_force_stop_fallback.py` | runner FORCE_STOP 降级集成测试 | 新建 |
| `data/prompt_components/strategy_task_state.md`（或插入 `strategy_core.md`） | task_state 规则 prompt 组件 | 修改/新建：显式化 idempotency + 最后任务语义 |

---

## Task 1: 改写 task_write.py 最后任务分支消息 + session 标记

**Files:**
- Modify: `src/nini/agent/session.py`（新增 `pending_auto_complete_task_id` 属性）
- Modify: `src/nini/tools/task_write.py:479-487`
- Test: `tests/test_task_write_last_task_message.py`（新建）

**背景：** 当 `pending==0 and current_in_progress` 时（task4 刚进入 in_progress），当前消息要求模型"将本任务标记为 completed **再**输出最终总结"——两步指令。再下一轮 `all_done` 时又禁止调工具，两条消息语义冲突。会话 2dfc01fe2a83 event 54 → 57 → 59+ 的循环正是此处。修复方向：把最后任务视为"你回复总结后系统自动关闭"，消除两步。

- [ ] **Step 1: 给 Session 加 `pending_auto_complete_task_id` 属性**

打开 `src/nini/agent/session.py`，找到 Session 类字段区（约第 80-110 行之间 `artifacts: dict[str, Any] = field(default_factory=dict)` 附近），在 dataclass 字段里追加：

```python
    pending_auto_complete_task_id: int | None = None
```

位置：与 `artifacts` 属性同块声明。若 Session 不是 dataclass（是 plain class），则在 `__init__` 里初始化 `self.pending_auto_complete_task_id = None`。先 `Read` 该文件的 80-130 行确认形态再改。

- [ ] **Step 2: 写失败测试（新建文件）**

创建 `tests/test_task_write_last_task_message.py`：

```python
"""task_write 最后任务分支消息与自动完成标记测试。"""

from __future__ import annotations

import pytest

from nini.agent.session import Session
from nini.tools.task_write import TaskWriteTool


@pytest.mark.asyncio
async def test_last_remaining_task_message_forbids_task_state_call() -> None:
    """最后一个任务（pending==0 且仅该任务 in_progress）的消息不能要求再调 task_state。"""
    session = Session()
    tool = TaskWriteTool()

    # 初始化 2 个任务
    await tool.execute(
        session,
        operation="init",
        tasks=[
            {"id": 1, "title": "加载数据", "status": "pending"},
            {"id": 2, "title": "汇总结论", "status": "pending"},
        ],
    )

    # 把 1 → completed，2 → in_progress（此时 pending==0，只剩 2 在 in_progress）
    result = await tool.execute(
        session,
        operation="update",
        tasks=[
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"},
        ],
    )

    assert result.success, result.message
    msg = result.message
    # 绝对不能要求再次调用 task_state
    assert "将本任务标记为 completed 再输出" not in msg, msg
    assert "标记为 completed" not in msg or "不要再调用" in msg, msg
    # 必须显式告诉模型"直接输出总结"
    assert "直接输出" in msg or "直接给出" in msg, msg
    # 必须显式禁止再调 task_state
    assert "不要再调用 task_state" in msg or "无需再调用 task_state" in msg, msg


@pytest.mark.asyncio
async def test_last_remaining_task_marks_session_for_auto_complete() -> None:
    """最后一个任务进入 in_progress 时，session 应记录其 id，用于 turn 结束自动关闭。"""
    session = Session()
    tool = TaskWriteTool()

    await tool.execute(
        session,
        operation="init",
        tasks=[
            {"id": 1, "title": "加载数据", "status": "pending"},
            {"id": 2, "title": "汇总结论", "status": "pending"},
        ],
    )

    await tool.execute(
        session,
        operation="update",
        tasks=[
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"},
        ],
    )

    assert session.pending_auto_complete_task_id == 2


@pytest.mark.asyncio
async def test_non_last_task_does_not_mark_auto_complete() -> None:
    """非最后任务 in_progress 不应设置 auto_complete 标记。"""
    session = Session()
    tool = TaskWriteTool()

    await tool.execute(
        session,
        operation="init",
        tasks=[
            {"id": 1, "title": "加载数据", "status": "pending"},
            {"id": 2, "title": "分析", "status": "pending"},
            {"id": 3, "title": "汇总", "status": "pending"},
        ],
    )

    # 只让任务 1 进入 in_progress，任务 2、3 还是 pending
    await tool.execute(
        session,
        operation="update",
        tasks=[{"id": 1, "status": "in_progress"}],
    )

    assert session.pending_auto_complete_task_id is None
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_task_write_last_task_message.py -v`
Expected: 所有测试 FAIL 或 ERROR（属性不存在 / 消息依旧要求两步）。

- [ ] **Step 4: 修改 task_write.py 最后任务分支**

替换 `src/nini/tools/task_write.py:479-487` 的 `elif current_in_progress and pending == 0:` 分支：

```python
        elif current_in_progress and pending == 0:
            # 最后一个任务（通常是"汇总结论"或"复盘检查"）：
            # 视为隐式自动完成——避免模型陷入"先 call 再总结"的两步循环。
            session.pending_auto_complete_task_id = current_in_progress.id
            message = (
                f"所有前序任务已完成，当前仅剩任务{current_in_progress.id}"
                f"「{current_in_progress.title}」。"
                "请**直接输出最终分析总结**，引用已生成的图表 artifact；"
                "本任务会在你回复后由系统自动标记为 completed，"
                "**无需再调用 task_state**。"
            )
```

不改其他分支。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_task_write_last_task_message.py -v`
Expected: 3 条全 PASS。

- [ ] **Step 6: 格式化 + 提交**

```bash
black src/nini/agent/session.py src/nini/tools/task_write.py tests/test_task_write_last_task_message.py
git add src/nini/agent/session.py src/nini/tools/task_write.py tests/test_task_write_last_task_message.py
git commit -m "fix(task_state): 最后任务分支改为隐式自动完成，消除两步指令循环"
```

---

## Task 2: runner turn-end 自动完成 last in_progress

**Files:**
- Modify: `src/nini/agent/runner.py`（在 turn 成功结束前新增 hook）
- Test: `tests/test_runner_turn_auto_complete.py`（新建）

**背景：** Task 1 在 session 里标记了 `pending_auto_complete_task_id`。Runner 需要在 turn 结束（发完最终 text event、准备 yield done_event 之前）检查该标记，若非 None 且该 task 仍处于 in_progress，则静默置 completed 并发 plan_step_update_event。

- [ ] **Step 1: 定位 runner turn 收尾处**

先 Read `src/nini/agent/runner.py` 大约第 1800-1900 行（turn 主循环退出前、`yield eb.build_done_event` 附近）确认结构。若没有统一的 "turn end" 汇合点，可能需要抽一个内部函数 `_finalize_turn(session, turn_id)` 并在所有退出路径调用。

- [ ] **Step 2: 写失败测试（新建文件）**

创建 `tests/test_runner_turn_auto_complete.py`：

```python
"""Runner turn 结束自动完成 last in_progress 任务测试。"""

from __future__ import annotations

import pytest

from nini.agent.runner import AgentRunner
from nini.agent.session import Session


@pytest.mark.asyncio
async def test_turn_end_auto_completes_pending_task(monkeypatch) -> None:
    """turn 结束时，若 session.pending_auto_complete_task_id 有值且任务仍 in_progress，应置 completed。"""
    session = Session()

    # 模拟已初始化的任务列表：任务 1 in_progress
    from nini.agent.task_manager import TaskItem, TaskManager

    session.task_manager = TaskManager(
        tasks=[TaskItem(id=1, title="汇总", status="in_progress")],
        initialized=True,
    )
    session.pending_auto_complete_task_id = 1

    runner = AgentRunner(session=session)
    # 直接调用内部收尾函数（由 Task 2 实现的 _finalize_turn）
    runner._finalize_turn(session, turn_id="test-turn")

    target = next(t for t in session.task_manager.tasks if t.id == 1)
    assert target.status == "completed"
    # 标记应被清除避免重复触发
    assert session.pending_auto_complete_task_id is None


@pytest.mark.asyncio
async def test_turn_end_skips_if_task_already_completed() -> None:
    """若目标任务已非 in_progress（被模型手动改过），auto-complete 应幂等跳过。"""
    session = Session()
    from nini.agent.task_manager import TaskItem, TaskManager

    session.task_manager = TaskManager(
        tasks=[TaskItem(id=1, title="汇总", status="completed")],
        initialized=True,
    )
    session.pending_auto_complete_task_id = 1

    runner = AgentRunner(session=session)
    runner._finalize_turn(session, turn_id="test-turn")

    target = next(t for t in session.task_manager.tasks if t.id == 1)
    assert target.status == "completed"
    assert session.pending_auto_complete_task_id is None


@pytest.mark.asyncio
async def test_turn_end_skips_if_no_pending_flag() -> None:
    """未设置 pending_auto_complete_task_id 时不应改动任务列表。"""
    session = Session()
    from nini.agent.task_manager import TaskItem, TaskManager

    session.task_manager = TaskManager(
        tasks=[TaskItem(id=1, title="汇总", status="in_progress")],
        initialized=True,
    )
    session.pending_auto_complete_task_id = None

    runner = AgentRunner(session=session)
    runner._finalize_turn(session, turn_id="test-turn")

    target = next(t for t in session.task_manager.tasks if t.id == 1)
    assert target.status == "in_progress"
```

Run: `pytest tests/test_runner_turn_auto_complete.py -v`
Expected: 全部 FAIL（`_finalize_turn` 不存在 / session 属性未初始化）。

- [ ] **Step 3: 在 `runner.py` 的 `AgentRunner` 类里新增 `_finalize_turn` 方法**

在 `AgentRunner` 类（含 `self._loop_guard` 的那个类，约第 400-500 行）内，**靠近其他私有方法**的位置加入：

```python
    def _finalize_turn(self, session: Session, turn_id: str) -> None:
        """turn 结束时的统一收尾：自动完成被标记的 last in_progress 任务。

        被 task_write 在"最后任务"分支里设置 session.pending_auto_complete_task_id，
        这里在 turn 成功结束前把它静默置 completed，避免模型陷入
        "先 call task_state 再输出总结"的两步指令循环。
        """
        pending_id = getattr(session, "pending_auto_complete_task_id", None)
        if pending_id is None:
            return

        manager = session.task_manager
        for task in manager.tasks:
            if task.id == pending_id and task.status == "in_progress":
                task.status = "completed"
                logger.info(
                    "turn 结束自动完成任务: session=%s task_id=%d title=%s",
                    session.id,
                    task.id,
                    task.title,
                )
                break

        session.pending_auto_complete_task_id = None
```

- [ ] **Step 4: 在 turn 退出路径调用 `_finalize_turn`**

在 `runner.py` 主循环中搜索所有 `yield eb.build_done_event(turn_id=turn_id)` 出现位置（至少 3 处：正常结束、FORCE_STOP 提前返回、异常处理）。在每个 `build_done_event` **之前**加一行：

```python
                self._finalize_turn(session, turn_id)
                yield eb.build_done_event(turn_id=turn_id)
```

⚠️ 注意 FORCE_STOP 分支也要调用——该任务虽然被循环打断，但最后任务标记依旧应清除，避免下轮脏状态。

- [ ] **Step 5: 运行测试确认通过 + 跑 runner 相关测试确保无回归**

Run: `pytest tests/test_runner_turn_auto_complete.py -v`
Expected: 全 PASS。

Run: `pytest tests/test_agent_runner.py tests/test_agent_runner_loop_guard.py -v 2>&1 | tail -30`（若文件存在；不存在则跳过）
Expected: 无回归。

- [ ] **Step 6: 格式化 + 提交**

```bash
black src/nini/agent/runner.py tests/test_runner_turn_auto_complete.py
git add src/nini/agent/runner.py tests/test_runner_turn_auto_complete.py
git commit -m "feat(runner): turn 结束自动完成被标记的 last in_progress 任务"
```

---

## Task 3: 阈值调整 — task_state L3 先于 LoopGuard FORCE_STOP 触发

**Files:**
- Modify: `src/nini/agent/loop_guard.py:119-128`（默认 `hard_limit` 从 5 提到 6）
- Modify: `src/nini/agent/runner.py:1713,1683`（L2 从 ≥4 提前到 ≥3；L3 从 ≥6 提前到 ≥5）
- Test: `tests/test_loop_guard.py`（追加/更新阈值断言）
- Test: `tests/test_runner_task_state_circuit_breaker.py`（新建，验证 L3 在 LoopGuard FORCE_STOP 前触发）

**背景：** 会话 2dfc01fe2a83 中 `task_state` 专属 L3 熔断阈值为 ≥6，但 LoopGuard FORCE_STOP 阈值为 ≥5，导致 LoopGuard 先终止整轮，L3 的结构化 `TASK_STATE_NOOP_CIRCUIT_BREAKER` 错误根本没机会下发给模型。调整后 L3 先触发，模型能收到包含 `recovery_hint` 的结构化错误；若仍不收手，LoopGuard 在下一轮兜底。

- [ ] **Step 1: 写 LoopGuard 默认值断言测试**

追加到 `tests/test_loop_guard.py` 末尾：

```python
def test_loop_guard_default_hard_limit_is_six() -> None:
    """hard_limit 默认值应为 6，让 task_state L3 熔断先于 LoopGuard FORCE_STOP 触发。"""
    from nini.agent.loop_guard import LoopGuard

    guard = LoopGuard()
    assert guard._hard_limit == 6
    assert guard._warn_threshold == 4


def test_loop_guard_force_stops_at_count_six() -> None:
    """同一 fingerprint 出现 6 次时应触发 FORCE_STOP（而非 5 次）。"""
    from nini.agent.loop_guard import LoopGuard, LoopGuardDecision

    guard = LoopGuard()
    tc = [{"function": {"name": "task_state", "arguments": '{"operation":"update","tasks":[{"id":1,"status":"completed"}]}'}}]
    decisions = []
    for _ in range(6):
        d, _ = guard.check(tc, "sess-1")
        decisions.append(d)
    # 前 5 次不应 FORCE_STOP（count=1..5）；第 6 次才 FORCE_STOP
    assert decisions[0] == LoopGuardDecision.NORMAL
    assert decisions[3] == LoopGuardDecision.WARN  # count=4
    assert decisions[4] == LoopGuardDecision.WARN  # count=5（仍是 WARN）
    assert decisions[5] == LoopGuardDecision.FORCE_STOP  # count=6
```

Run: `pytest tests/test_loop_guard.py::test_loop_guard_default_hard_limit_is_six tests/test_loop_guard.py::test_loop_guard_force_stops_at_count_six -v`
Expected: FAIL（默认值当前为 5）。

- [ ] **Step 2: 改 `loop_guard.py:119-128` 默认 hard_limit=6**

打开 `src/nini/agent/loop_guard.py`，找到 `LoopGuard.__init__` 的默认值：

```python
    def __init__(
        self,
        warn_threshold: int = 4,
        hard_limit: int = 5,      # ← 改成 6
        window_size: int = 20,
        max_sessions: int = 100,
    ) -> None:
```

改为 `hard_limit: int = 6`。

Run: `pytest tests/test_loop_guard.py -v`
Expected: 全 PASS（含新增 2 条）。

- [ ] **Step 3: 调整 task_state L2/L3 阈值**

在 `src/nini/agent/runner.py:1676` 起的 no-op 检测块中：

```python
                        if task_state_noop_repeat_count >= 6:  # ← 改成 5
                            # 第三级：硬熔断，跳过执行并返回失败
                            ...
                        elif task_state_noop_repeat_count >= 4:  # ← 改成 3
                            # 第二级：注入 system prompt 警告 + 清理 data 中的 no_op_ids
                            ...
                        elif task_state_noop_repeat_count >= 2:
                            # 第一级：替换返回消息（轻量干预）——保持不变
                            ...
```

新阈值：L1≥2、L2≥3、L3≥5；LoopGuard FORCE_STOP≥6。序列：L1 在第 2 次触发、L2 在第 3 次、L3 在第 5 次返回 TASK_STATE_NOOP_CIRCUIT_BREAKER 错误，若模型第 6 次仍发同样调用，LoopGuard 兜底 FORCE_STOP。

- [ ] **Step 4: 写集成测试验证顺序**

创建 `tests/test_runner_task_state_circuit_breaker.py`：

```python
"""task_state 专属熔断应早于 LoopGuard FORCE_STOP 触发。"""

from __future__ import annotations

import pytest


def test_task_state_l3_threshold_is_below_loop_guard_hard_limit() -> None:
    """确保 task_state L3 熔断阈值（=5）严格小于 LoopGuard hard_limit（=6）。

    两个阈值在不同文件，回归测试防止未来某次调整让 LoopGuard 再次抢跑。
    """
    from nini.agent.loop_guard import LoopGuard

    loop_guard_hard_limit = LoopGuard()._hard_limit

    # task_state L3 阈值硬编码在 runner.py:1683 附近；这里通过 grep 取值
    import pathlib
    import re

    runner_src = pathlib.Path(__file__).parent.parent / "src" / "nini" / "agent" / "runner.py"
    text = runner_src.read_text(encoding="utf-8")
    m = re.search(r"if task_state_noop_repeat_count >= (\d+):\s*\n\s*#\s*第三级", text)
    assert m is not None, "未找到 task_state L3 熔断分支"
    task_state_l3_threshold = int(m.group(1))

    assert task_state_l3_threshold < loop_guard_hard_limit, (
        f"task_state L3 熔断阈值 ({task_state_l3_threshold}) 必须小于 "
        f"LoopGuard hard_limit ({loop_guard_hard_limit})，"
        "否则 LoopGuard 会抢先 FORCE_STOP，吞掉 TASK_STATE_NOOP_CIRCUIT_BREAKER 结构化错误。"
    )
```

Run: `pytest tests/test_runner_task_state_circuit_breaker.py -v`
Expected: PASS。

- [ ] **Step 5: 跑完整 runner/loop_guard 测试**

Run: `pytest tests/test_loop_guard.py tests/test_runner_task_state_circuit_breaker.py -v`
Expected: 全 PASS。

- [ ] **Step 6: 格式化 + 提交**

```bash
black src/nini/agent/loop_guard.py src/nini/agent/runner.py tests/test_loop_guard.py tests/test_runner_task_state_circuit_breaker.py
git add src/nini/agent/loop_guard.py src/nini/agent/runner.py tests/test_loop_guard.py tests/test_runner_task_state_circuit_breaker.py
git commit -m "fix(loop_guard): 调整阈值让 task_state L3 熔断先于 LoopGuard FORCE_STOP 触发"
```

---

## Task 4: 新建 fallback summary 工具

**Files:**
- Create: `src/nini/utils/fallback_summary.py`
- Test: `tests/test_fallback_summary.py`（新建）

**背景：** FORCE_STOP 触发时，session 里通常已经有成功的 artifact（会话 2dfc01fe2a83 就生成了 `cellulose_content_bar_chart.pdf/png/svg`）和 stdout 数据。让兜底总结复用这些，至少给用户可读结果。

**接口契约：**

```python
def build_fallback_summary(
    messages: list[dict[str, Any]],   # session.messages（含 role/content/event_type/...）
    user_request: str | None = None,  # 本轮最早的 user 消息文本
) -> str | None:
    """
    从 turn 内的 tool_result / artifact 事件抽取关键信息，合成 Markdown 兜底总结。
    返回 None 表示数据不足（例如 turn 内连工具调用都没成功过），由调用方决定是否 fallback 到原始"检测到死循环"提示。
    """
```

- [ ] **Step 1: 写失败测试（新建文件）**

创建 `tests/test_fallback_summary.py`：

```python
"""fallback_summary 兜底总结合成测试。"""

from __future__ import annotations

from nini.utils.fallback_summary import build_fallback_summary


def test_returns_none_when_no_tool_results() -> None:
    """没有任何 tool_result 时应返回 None。"""
    messages = [
        {"role": "user", "content": "画个图"},
        {"role": "assistant", "content": "好的"},
    ]
    assert build_fallback_summary(messages, user_request="画个图") is None


def test_collects_chart_artifact_urls() -> None:
    """从 artifact 事件抽取 chart 类型产物并用 Markdown 图片语法引用。"""
    messages = [
        {"role": "user", "content": "画柱状图"},
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {
                    "name": "bar_chart.png",
                    "type": "chart",
                    "download_url": "/api/artifacts/session/bar_chart.png",
                },
                {
                    "name": "bar_chart.pdf",
                    "type": "chart",
                    "download_url": "/api/artifacts/session/bar_chart.pdf",
                },
            ],
        },
    ]
    out = build_fallback_summary(messages, user_request="画柱状图")
    assert out is not None
    # png 优先引用
    assert "![bar_chart.png](/api/artifacts/session/bar_chart.png)" in out
    # 应说明是兜底总结
    assert "兜底" in out or "系统终止" in out


def test_extracts_tool_stdout_stats() -> None:
    """tool_result 中的 stdout 若含统计数字应被纳入总结。"""
    messages = [
        {"role": "user", "content": "分析数据"},
        {
            "role": "tool",
            "tool_name": "code_session",
            "content": (
                '{"success": true, '
                '"message": "脚本执行成功\\nstdout:\\n'
                'Col-0: Mean=9.13%, SEM=0.19%, n=3\\n'
                'ANAC017: Mean=6.85%, SEM=0.20%, n=3"}'
            ),
        },
    ]
    out = build_fallback_summary(messages, user_request="分析数据")
    assert out is not None
    assert "Mean=9.13%" in out
    assert "Mean=6.85%" in out


def test_output_is_plain_markdown() -> None:
    """输出不能含 HTML；应是纯 Markdown 可渲染。"""
    messages = [
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {"name": "x.png", "type": "chart", "download_url": "/a/x.png"},
            ],
        }
    ]
    out = build_fallback_summary(messages, user_request="test")
    assert out is not None
    assert "<" not in out.replace("<br>", "").replace("<unknown>", "")  # 允许 <br> 等


def test_multiple_artifacts_each_referenced_once() -> None:
    """多个 chart artifact 时，同名图表的不同格式只引用一次（优先 png）。"""
    messages = [
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {"name": "c.pdf", "type": "chart", "download_url": "/a/c.pdf"},
                {"name": "c.png", "type": "chart", "download_url": "/a/c.png"},
                {"name": "c.svg", "type": "chart", "download_url": "/a/c.svg"},
            ],
        }
    ]
    out = build_fallback_summary(messages, user_request="test")
    assert out is not None
    # png 出现、pdf/svg 不出现
    assert "/a/c.png" in out
    assert "/a/c.pdf" not in out
    assert "/a/c.svg" not in out
```

Run: `pytest tests/test_fallback_summary.py -v`
Expected: ImportError（模块不存在）。

- [ ] **Step 2: 实现模块**

创建 `src/nini/utils/fallback_summary.py`：

```python
"""兜底总结合成器。

当 agent turn 被 LoopGuard/FORCE_STOP 中断时，从 session.messages 里抓取本轮
已成功的 artifact 与 tool stdout，拼成一段 Markdown 文本交给用户。
目的：让"终止"不等于"白跑"，模型产出的结果仍可读。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any


def _stem_and_ext(name: str) -> tuple[str, str]:
    """拆 'bar_chart.pdf' -> ('bar_chart', 'pdf')。无扩展名时 ext 为 ''。"""
    if "." not in name:
        return name, ""
    stem, ext = name.rsplit(".", 1)
    return stem, ext.lower()


_FORMAT_PRIORITY = ["png", "svg", "jpg", "jpeg", "webp", "pdf"]


def _pick_preferred_format(group: list[dict[str, Any]]) -> dict[str, Any]:
    """同一 stem 的多个格式里挑优先级最高的（png > svg > jpg > pdf）。"""
    def rank(item: dict[str, Any]) -> int:
        _, ext = _stem_and_ext(str(item.get("name", "")))
        try:
            return _FORMAT_PRIORITY.index(ext)
        except ValueError:
            return len(_FORMAT_PRIORITY)

    return sorted(group, key=rank)[0]


def _collect_chart_artifacts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 assistant/artifact 事件收集 chart 类型产物，按 stem 去重后挑最佳格式。"""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for msg in messages:
        if msg.get("event_type") != "artifact":
            continue
        for art in msg.get("artifacts", []) or []:
            if art.get("type") != "chart":
                continue
            stem, _ext = _stem_and_ext(str(art.get("name", "")))
            grouped[stem].append(art)
    return [_pick_preferred_format(g) for g in grouped.values() if g]


_STDOUT_SNIPPET_RE = re.compile(r"(Mean=[^\s,\"\\]+|p\s*[=<>]\s*[\d.eE+-]+|SEM=[^\s,\"\\]+)")


def _extract_stat_lines(messages: list[dict[str, Any]]) -> list[str]:
    """从 tool 消息 content（JSON 字符串）里提取含统计数字的行。"""
    lines: list[str] = []
    seen: set[str] = set()
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        raw = msg.get("content", "")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            parsed = json.loads(raw)
            stdout = parsed.get("message", "") if isinstance(parsed, dict) else ""
        except json.JSONDecodeError:
            stdout = raw
        for line in str(stdout).splitlines():
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            if _STDOUT_SNIPPET_RE.search(stripped):
                lines.append(stripped)
                seen.add(stripped)
    return lines


def build_fallback_summary(
    messages: list[dict[str, Any]],
    user_request: str | None = None,
) -> str | None:
    """合成兜底总结。数据不足时返回 None。"""
    charts = _collect_chart_artifacts(messages)
    stat_lines = _extract_stat_lines(messages)

    if not charts and not stat_lines:
        return None

    parts: list[str] = [
        "> ⚠️ 系统终止了自动化执行循环，以下是**兜底总结**（基于已生成的工具产物与统计输出）："
    ]
    if user_request:
        req = user_request.strip().splitlines()[0][:120]
        parts.append(f"\n**原始请求**：{req}")

    if stat_lines:
        parts.append("\n**关键统计结果**：")
        parts.extend(f"- {line}" for line in stat_lines[:12])

    if charts:
        parts.append("\n**生成的图表**：")
        for art in charts:
            name = str(art.get("name", "chart"))
            url = str(art.get("download_url", ""))
            parts.append(f"\n![{name}]({url})")

    return "\n".join(parts)
```

- [ ] **Step 3: 运行测试确认通过**

```bash
black src/nini/utils/fallback_summary.py tests/test_fallback_summary.py
pytest tests/test_fallback_summary.py -v
```

Expected: 5 条全 PASS。

- [ ] **Step 4: 提交**

```bash
git add src/nini/utils/fallback_summary.py tests/test_fallback_summary.py
git commit -m "feat(utils): 新增 fallback_summary 合成器，从 artifact/stdout 拼兜底总结"
```

---

## Task 5: runner FORCE_STOP 分支接入兜底总结

**Files:**
- Modify: `src/nini/agent/runner.py:1347-1371`
- Test: `tests/test_runner_force_stop_fallback.py`（新建）

**背景：** Task 4 的合成器就位后，在 `FORCE_STOP` 分支调用它；若合成返回非 None，先 yield 兜底 text 事件、再 yield 原来的"检测到死循环"警告文本（让用户既看到结果又知道发生了什么），否则只 yield 原文本（保持旧行为）。

- [ ] **Step 1: 写集成测试（新建文件）**

创建 `tests/test_runner_force_stop_fallback.py`：

```python
"""Runner FORCE_STOP 分支应在有产物时 yield 兜底总结。"""

from __future__ import annotations

import pytest


def test_force_stop_emits_fallback_summary_when_artifacts_present() -> None:
    """若 session.messages 含 chart artifact，FORCE_STOP 应先 yield 兜底总结。"""
    from nini.agent.session import Session
    from nini.agent.runner import AgentRunner

    session = Session()
    session.messages = [
        {"role": "user", "content": "画柱状图"},
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {"name": "c.png", "type": "chart", "download_url": "/a/c.png"},
            ],
        },
    ]

    runner = AgentRunner(session=session)
    # 直接调用内部 helper 获取 FORCE_STOP 文本序列（避免构造完整 async 循环）
    texts = list(runner._build_force_stop_texts(session))

    # 至少 2 段：兜底总结 + 原警告
    assert len(texts) >= 2
    assert "![c.png](/a/c.png)" in texts[0]
    assert "检测到工具调用死循环" in texts[-1]


def test_force_stop_falls_back_to_warning_only_when_no_artifacts() -> None:
    """session 里没可用产物时，仍只 yield 原警告文本。"""
    from nini.agent.session import Session
    from nini.agent.runner import AgentRunner

    session = Session()
    session.messages = [{"role": "user", "content": "test"}]

    runner = AgentRunner(session=session)
    texts = list(runner._build_force_stop_texts(session))

    assert len(texts) == 1
    assert "检测到工具调用死循环" in texts[0]
```

Run: `pytest tests/test_runner_force_stop_fallback.py -v`
Expected: FAIL（`_build_force_stop_texts` 不存在）。

- [ ] **Step 2: 在 `AgentRunner` 类里新增 `_build_force_stop_texts`**

在 `AgentRunner` 类（与 `_finalize_turn` 相邻）加入：

```python
    def _build_force_stop_texts(self, session: Session) -> list[str]:
        """构造 FORCE_STOP 时要 yield 的文本序列。

        若能从 session.messages 合成有效兜底总结，则返回 [兜底总结, 警告]；
        否则只返回 [警告]。
        """
        from nini.utils.fallback_summary import build_fallback_summary

        user_msg = next(
            (m.get("content") for m in session.messages if m.get("role") == "user"),
            None,
        )
        fallback = build_fallback_summary(
            list(session.messages),
            user_request=user_msg if isinstance(user_msg, str) else None,
        )
        warning = (
            "⚠️ 检测到工具调用死循环（相同工具组合已重复调用多次），"
            "系统已自动终止当前任务。请尝试调整问题描述或手动干预。"
        )
        if fallback:
            return [fallback, warning]
        return [warning]
```

- [ ] **Step 3: 改写 runner.py:1347-1371 FORCE_STOP 分支**

把原来的：

```python
            if _loop_decision == LoopGuardDecision.FORCE_STOP:
                _stop_msg = (
                    "⚠️ 检测到工具调用死循环（相同工具组合已重复调用多次），"
                    "系统已自动终止当前任务。请尝试调整问题描述或手动干预。"
                )
                logger.warning(...)
                yield eb.build_text_event(
                    content=_stop_msg,
                    turn_id=turn_id,
                    metadata={"source": "loop_guard", "decision": "force_stop"},
                )
                session.add_message(
                    "assistant",
                    _stop_msg,
                    turn_id=turn_id,
                    operation="complete",
                )
                yield eb.build_done_event(turn_id=turn_id)
                return
```

替换为：

```python
            if _loop_decision == LoopGuardDecision.FORCE_STOP:
                logger.warning(
                    "循环守卫触发 FORCE_STOP: session=%s iteration=%d tools=%s",
                    session.id,
                    iteration,
                    _loop_tool_names,
                )
                _texts = self._build_force_stop_texts(session)
                for idx, _text in enumerate(_texts):
                    # 第一段若是兜底总结，来源标 fallback_summary；最后一段警告来源保持 loop_guard
                    _source = "fallback_summary" if (idx == 0 and len(_texts) > 1) else "loop_guard"
                    yield eb.build_text_event(
                        content=_text,
                        turn_id=turn_id,
                        metadata={"source": _source, "decision": "force_stop"},
                    )
                    session.add_message(
                        "assistant",
                        _text,
                        turn_id=turn_id,
                        operation="complete",
                    )
                self._finalize_turn(session, turn_id)
                yield eb.build_done_event(turn_id=turn_id)
                return
```

- [ ] **Step 4: 运行测试确认通过**

```bash
black src/nini/agent/runner.py tests/test_runner_force_stop_fallback.py
pytest tests/test_runner_force_stop_fallback.py -v
```

Expected: 2 条全 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/nini/agent/runner.py tests/test_runner_force_stop_fallback.py
git commit -m "feat(runner): FORCE_STOP 前合成兜底总结，保留产物展示"
```

---

## Task 6: prompt 组件补充 task_state 规则

**Files:**
- Modify: `data/prompt_components/strategy_core.md`（若已存在"任务调度"段落则追加；否则在文件末尾追加）

**背景：** 显式化 `task_state` 的幂等性与"最后任务"语义，让模型 planning 层就知道不要重试。

- [ ] **Step 1: 确认文件位置与现有结构**

Run: `ls data/prompt_components/ | grep -i "task\|core\|strategy"`
Read 找到的相关文件（大概率是 `strategy_core.md`），确认是否已有"任务调度"类段落。

- [ ] **Step 2: 在 `strategy_core.md` 末尾追加段落**

追加以下内容（保留原有全部内容）：

```markdown

task_state 使用规则（必须遵循）：
- `task_state(update)` 是**幂等**工具：对同一 task id 传同一 status 不会产生任何效果，也不是"失败"。看到"已处于请求的状态"消息说明上一次已生效，**绝对不要**重试。
- 看到"任务4 已处于请求的状态"或"所有任务已完成"消息后，下一个动作必须是**输出最终 Markdown 文本总结**，而不是再 call 工具。
- 若工具消息包含"无需再调用 task_state"或"系统自动标记"，表示**最后任务会由系统自动关闭**；你只需输出总结文字。
- 连续调用同一 task_state 调用 ≥3 次是异常行为，系统会升级警告并可能终止本轮任务。
```

- [ ] **Step 3: 跑相关测试**

Run: `pytest tests/test_context_components.py -v`
Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add data/prompt_components/strategy_core.md
git commit -m "docs(prompt): 显式化 task_state 幂等性与最后任务语义"
```

---

## Task 7: 全量验证

**Files:** 无代码改动，仅校验。

- [ ] **Step 1: 事件 schema 一致性**

Run: `python3 scripts/check_event_schema_consistency.py`
Expected: 退出码 0。

- [ ] **Step 2: 格式与类型（仅本次 touched 文件）**

```bash
black --check \
  src/nini/agent/session.py \
  src/nini/agent/runner.py \
  src/nini/agent/loop_guard.py \
  src/nini/tools/task_write.py \
  src/nini/utils/fallback_summary.py \
  tests/test_task_write_last_task_message.py \
  tests/test_runner_turn_auto_complete.py \
  tests/test_loop_guard.py \
  tests/test_runner_task_state_circuit_breaker.py \
  tests/test_fallback_summary.py \
  tests/test_runner_force_stop_fallback.py
mypy \
  src/nini/agent/session.py \
  src/nini/agent/runner.py \
  src/nini/agent/loop_guard.py \
  src/nini/tools/task_write.py \
  src/nini/utils/fallback_summary.py
```

Expected: 均通过。

- [ ] **Step 3: 跑全部后端测试**

Run: `pytest -q`
Expected: 全绿（含新增 ~15 条测试）。

- [ ] **Step 4: 快照检查**

Run: `git status && git log --oneline main..HEAD`
Expected: 工作区干净；7 个 commit（Task 1-6 + 本 plan 文件）。

---

## Self-Review

**Spec coverage（根因 → 任务映射）：**
- ① task_write 最后任务消息矛盾（Cause 1）→ Task 1 ✅
- ② 模型 reasoning/action 漂移（Cause 2，模型层不可修）→ 通过 Task 1 的隐式自动完成绕开 + Task 6 prompt 强化 ✅
- ③ 阈值错位让 LoopGuard 抢跑（Cause 3）→ Task 3 ✅
- ④ FORCE_STOP 无兜底（Cause 4）→ Task 4 + Task 5 ✅
- ⑤ prompt 层 task_state 幂等性未显式化 → Task 6 ✅

**Placeholder scan：** 无 TBD/TODO；每步都有具体代码/命令。

**Type consistency：**
- `session.pending_auto_complete_task_id: int | None` — Task 1 声明、Task 2 读取，签名一致。
- `AgentRunner._finalize_turn(self, session: Session, turn_id: str) -> None` — Task 2 声明、Task 5 调用，签名一致。
- `build_fallback_summary(messages, user_request=None) -> str | None` — Task 4 声明、Task 5 通过 `_build_force_stop_texts` 调用，签名一致。
- `_build_force_stop_texts(self, session: Session) -> list[str]` — Task 5 声明与测试一致。

**风险点：**
- Task 2 的 `_finalize_turn` 在所有 turn 退出路径调用 — 需要仔细 grep `build_done_event` 覆盖全部（正常、FORCE_STOP、异常）。Step 4 已强调。
- Task 3 的阈值调整可能让历史回归测试对"count=5 FORCE_STOP"敏感；Step 1 的 `test_loop_guard_force_stops_at_count_six` 已声明新阈值，老测试需同步更新。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-fix-task-state-loop-and-graceful-fallback.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
