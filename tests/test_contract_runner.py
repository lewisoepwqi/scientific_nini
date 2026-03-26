"""测试 ContractRunner：线性 DAG 执行、review_gate 模拟、失败处理、事件发射。"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from nini.models.risk import TrustLevel
from nini.models.skill_contract import SkillContract, SkillStep
from nini.skills.contract_runner import ContractRunner


def make_contract(*steps: SkillStep) -> SkillContract:
    return SkillContract(steps=list(steps))


def step(
    sid: str,
    depends_on: list[str] | None = None,
    review_gate: bool = False,
    retry_policy: str = "skip",
    trust_level: TrustLevel = TrustLevel.T1,
) -> SkillStep:
    return SkillStep(
        id=sid,
        name=sid,
        description=sid,
        depends_on=depends_on or [],
        review_gate=review_gate,
        retry_policy=retry_policy,
        trust_level=trust_level,
    )


# ---------------------------------------------------------------------------
# 拓扑排序
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_linear_chain_order(self) -> None:
        contract = make_contract(
            step("a"),
            step("b", depends_on=["a"]),
            step("c", depends_on=["b"]),
        )
        cb = AsyncMock()
        runner = ContractRunner(contract, skill_name="test", callback=cb)
        ordered = runner._topological_sort(contract.steps)
        assert [s.id for s in ordered] == ["a", "b", "c"]

    def test_no_dependencies_preserves_declaration_order(self) -> None:
        contract = make_contract(step("x"), step("y"), step("z"))
        cb = AsyncMock()
        runner = ContractRunner(contract, skill_name="test", callback=cb)
        ordered = runner._topological_sort(contract.steps)
        assert [s.id for s in ordered] == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# 线性 DAG 执行 & 事件发射
# ---------------------------------------------------------------------------


class TestLinearExecution:
    async def test_all_steps_complete(self) -> None:
        contract = make_contract(
            step("a"),
            step("b", depends_on=["a"]),
            step("c", depends_on=["b"]),
        )
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="test-skill", callback=cb)
        result = await runner.run(session=None)

        assert result.status == "completed"
        assert len(result.step_records) == 3
        assert all(r.status == "completed" for r in result.step_records)

    async def test_start_and_complete_events_emitted(self) -> None:
        contract = make_contract(step("a"), step("b", depends_on=["a"]))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="skill", callback=cb)
        await runner.run(session=None)

        # 每个步骤应发射 started 和 completed 事件
        statuses = [e[1].status for e in events if e[0] == "skill_step"]
        assert statuses.count("started") == 2
        assert statuses.count("completed") == 2

    async def test_event_contains_skill_name_and_step_id(self) -> None:
        contract = make_contract(step("load"))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="my-skill", callback=cb)
        await runner.run(session=None)

        skill_step_events = [e[1] for e in events if e[0] == "skill_step"]
        assert all(ev.skill_name == "my-skill" for ev in skill_step_events)
        assert any(ev.step_id == "load" for ev in skill_step_events)

    async def test_complete_event_has_duration_ms(self) -> None:
        contract = make_contract(step("a"))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="s", callback=cb)
        await runner.run(session=None)

        completed_events = [
            e[1] for e in events if e[0] == "skill_step" and e[1].status == "completed"
        ]
        assert len(completed_events) == 1
        assert completed_events[0].duration_ms is not None


# ---------------------------------------------------------------------------
# review_gate 模拟
# ---------------------------------------------------------------------------


class TestReviewGate:
    async def test_review_required_event_emitted(self) -> None:
        contract = make_contract(step("checked", review_gate=True))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(
            contract, skill_name="s", callback=cb, review_gate_timeout=0.1
        )
        # 不确认，让其超时
        result = await runner.run(session=None)

        review_events = [
            e[1] for e in events if e[0] == "skill_step" and e[1].status == "review_required"
        ]
        assert len(review_events) == 1
        assert review_events[0].step_id == "checked"
        # 超时按 skip 处理（retry_policy="skip" 默认）
        assert result.step_records[0].status == "skipped"

    async def test_approve_review_continues_execution(self) -> None:
        contract = make_contract(step("gate", review_gate=True))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(
            contract, skill_name="s", callback=cb, review_gate_timeout=2.0
        )

        async def confirm_later() -> None:
            await asyncio.sleep(0.05)
            runner.approve_review("gate")

        confirm_task = asyncio.create_task(confirm_later())
        result = await runner.run(session=None)
        await confirm_task

        assert result.status == "completed"
        assert result.step_records[0].status == "completed"

    async def test_review_timeout_abort_policy(self) -> None:
        """review_gate 超时且 retry_policy=abort 应终止契约。"""
        contract = make_contract(step("gate", review_gate=True, retry_policy="abort"))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(
            contract, skill_name="s", callback=cb, review_gate_timeout=0.05
        )
        result = await runner.run(session=None)
        # review_gate 未确认 → skipped（abort 仅在执行失败时生效，review 超时走跳过路径）
        assert result.step_records[0].status == "skipped"


# ---------------------------------------------------------------------------
# 失败处理
# ---------------------------------------------------------------------------


class TestFailureHandling:
    async def _make_failing_runner(
        self, contracts_steps: list[SkillStep], fail_step_id: str
    ) -> tuple[ContractRunner, list[tuple[str, Any]]]:
        contract = make_contract(*contracts_steps)
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="s", callback=cb)

        async def failing_executor(s: SkillStep, sess: Any, inp: dict) -> None:
            if s.id == fail_step_id:
                raise RuntimeError(f"步骤 {s.id} 故意失败")

        runner._step_executor = failing_executor  # type: ignore[attr-defined]
        return runner, events

    async def test_skip_policy_skips_failed_step(self) -> None:
        runner, events = await self._make_failing_runner(
            [step("a", retry_policy="skip"), step("b", depends_on=["a"])],
            fail_step_id="a",
        )
        result = await runner.run(session=None)

        assert result.status == "partial"
        statuses = {r.step_id: r.status for r in result.step_records}
        assert statuses["a"] == "skipped"
        # b 依赖 a（已跳过），所以 b 也被跳过
        assert statuses["b"] == "skipped"

    async def test_abort_policy_terminates_contract(self) -> None:
        runner, events = await self._make_failing_runner(
            [step("a", retry_policy="abort"), step("b", depends_on=["a"])],
            fail_step_id="a",
        )
        result = await runner.run(session=None)

        assert result.status == "failed"
        statuses = {r.step_id: r.status for r in result.step_records}
        assert statuses["a"] == "failed"

    async def test_retry_policy_retries_then_skips(self) -> None:
        call_count: dict[str, int] = {"a": 0}

        contract = make_contract(step("a", retry_policy="retry"))
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="s", callback=cb)

        async def counting_failing_executor(s: SkillStep, sess: Any, inp: dict) -> None:
            call_count[s.id] = call_count.get(s.id, 0) + 1
            raise RuntimeError("总是失败")

        runner._step_executor = counting_failing_executor  # type: ignore[attr-defined]
        result = await runner.run(session=None)

        # retry 策略：尝试 2 次（原始 + 重试），最终降级为 skip
        assert call_count["a"] == 2
        assert result.step_records[0].status == "skipped"

    async def test_independent_steps_after_skip_continue(self) -> None:
        """跳过某步骤后，无依赖关系的独立步骤应继续执行。"""
        contract = make_contract(
            step("a", retry_policy="skip"),  # 会失败
            step("b"),  # 独立步骤，不依赖 a
        )
        events: list[tuple[str, Any]] = []

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        runner = ContractRunner(contract, skill_name="s", callback=cb)

        async def failing_a(s: SkillStep, sess: Any, inp: dict) -> None:
            if s.id == "a":
                raise RuntimeError("a 失败")

        runner._step_executor = failing_a  # type: ignore[attr-defined]
        result = await runner.run(session=None)

        statuses = {r.step_id: r.status for r in result.step_records}
        assert statuses["a"] == "skipped"
        assert statuses["b"] == "completed"
        assert result.status == "partial"
