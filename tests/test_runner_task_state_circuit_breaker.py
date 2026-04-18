"""task_state 专属熔断应早于 LoopGuard FORCE_STOP 触发。"""

from __future__ import annotations


def test_task_state_l3_threshold_is_below_loop_guard_hard_limit() -> None:
    """确保 task_state L3 熔断阈值（=5）严格小于 LoopGuard hard_limit（=6）。

    两个阈值在不同文件，回归测试防止未来某次调整让 LoopGuard 再次抢跑。
    """
    from nini.agent.loop_guard import LoopGuard

    loop_guard_hard_limit = LoopGuard()._hard_limit

    # task_state L3 阈值硬编码在 runner.py 中；这里通过 grep 取值
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
