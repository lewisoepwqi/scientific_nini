"""DAG 执行引擎测试。"""

import asyncio
from typing import Any

from nini.models.skill_contract import SkillContract, SkillStep
from nini.skills.contract_runner import ContractRunner


def make_contract(*steps: SkillStep) -> SkillContract:
    return SkillContract(steps=list(steps))


def step(
    step_id: str,
    *,
    depends_on: list[str] | None = None,
    condition: str | None = None,
    input_from: dict[str, str] | None = None,
    output_key: str | None = None,
    retry_policy: str = "skip",
) -> SkillStep:
    return SkillStep(
        id=step_id,
        name=step_id,
        description=step_id,
        depends_on=depends_on or [],
        condition=condition,
        input_from=input_from or {},
        output_key=output_key,
        retry_policy=retry_policy,
    )


class TestDagEngine:
    async def test_parallel_branches_execute_in_same_layer_and_join_waits(self) -> None:
        contract = make_contract(
            step("a", output_key="source"),
            step("b", depends_on=["a"]),
            step("c", depends_on=["a"]),
            step("d", depends_on=["b", "c"]),
        )
        events: list[tuple[str, Any]] = []
        started_branches: set[str] = set()
        completed_branches: set[str] = set()
        branch_ready = asyncio.Event()
        release_branches = asyncio.Event()

        async def cb(event_type: str, data: Any) -> None:
            events.append((event_type, data))

        async def executor(step: SkillStep, session: Any, inputs: dict[str, Any]) -> dict[str, Any]:
            if step.id == "a":
                return {"dataset": [1, 2, 3]}
            if step.id in {"b", "c"}:
                started_branches.add(step.id)
                if len(started_branches) == 2:
                    branch_ready.set()
                await release_branches.wait()
                completed_branches.add(step.id)
                return {"branch": step.id}
            assert completed_branches == {"b", "c"}
            return {"merged": True}

        runner = ContractRunner(contract, skill_name="dag-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        run_task = asyncio.create_task(runner.run(session=None))
        await asyncio.wait_for(branch_ready.wait(), timeout=1.0)
        assert started_branches == {"b", "c"}
        release_branches.set()
        result = await run_task

        assert result.status == "completed"
        assert [record.status for record in result.step_records] == [
            "completed",
            "completed",
            "completed",
            "completed",
        ]

        branch_started_events = {
            event.step_id: event.layer
            for event_type, event in events
            if event_type == "skill_step" and event.status == "started"
        }
        assert branch_started_events["a"] == 0
        assert branch_started_events["b"] == 1
        assert branch_started_events["c"] == 1
        assert branch_started_events["d"] == 2

    async def test_condition_false_skips_step(self) -> None:
        contract = make_contract(
            step("load", output_key="loaded"),
            step("maybe_run", depends_on=["load"], condition="loaded.should_run"),
        )

        async def cb(event_type: str, data: Any) -> None:
            return None

        async def executor(step: SkillStep, session: Any, inputs: dict[str, Any]) -> dict[str, Any]:
            if step.id == "load":
                return {"should_run": False}
            raise AssertionError("condition=False 的步骤不应被执行")

        runner = ContractRunner(contract, skill_name="dag-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        result = await runner.run(session=None)

        assert result.status == "partial"
        assert {record.step_id: record.status for record in result.step_records} == {
            "load": "completed",
            "maybe_run": "skipped",
        }

    async def test_data_binding_supports_step_output_and_output_alias(self) -> None:
        contract = make_contract(
            step("load"),
            step(
                "transform",
                depends_on=["load"],
                input_from={"data": "load.dataset"},
                output_key="prepared",
            ),
            step(
                "analyze",
                depends_on=["transform"],
                condition="prepared.cleaned[0] == 2",
                input_from={"data": "prepared.cleaned"},
            ),
        )
        seen_inputs: dict[str, Any] = {}

        async def cb(event_type: str, data: Any) -> None:
            return None

        async def executor(step: SkillStep, session: Any, inputs: dict[str, Any]) -> dict[str, Any]:
            seen_inputs[step.id] = dict(inputs)
            if step.id == "load":
                return {"dataset": [1, 2, 3]}
            if step.id == "transform":
                assert inputs["data"] == [1, 2, 3]
                return {"cleaned": [2, 3]}
            assert inputs["data"] == [2, 3]
            return {"mean": 2.5}

        runner = ContractRunner(contract, skill_name="dag-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        result = await runner.run(session=None, inputs={"request_id": "req-1"})

        assert result.status == "completed"
        assert seen_inputs["transform"]["request_id"] == "req-1"
        assert seen_inputs["transform"]["data"] == [1, 2, 3]
        assert seen_inputs["analyze"]["data"] == [2, 3]

    async def test_parallel_failure_does_not_block_sibling_branch(self) -> None:
        contract = make_contract(
            step("a"),
            step("b", depends_on=["a"], retry_policy="skip"),
            step("c", depends_on=["a"]),
            step("d", depends_on=["b", "c"]),
        )
        started_branches: set[str] = set()
        branch_ready = asyncio.Event()
        release_branches = asyncio.Event()
        completed_steps: list[str] = []

        async def cb(event_type: str, data: Any) -> None:
            return None

        async def executor(step: SkillStep, session: Any, inputs: dict[str, Any]) -> dict[str, Any]:
            if step.id == "a":
                completed_steps.append("a")
                return {"root": True}
            if step.id in {"b", "c"}:
                started_branches.add(step.id)
                if len(started_branches) == 2:
                    branch_ready.set()
                await release_branches.wait()
                if step.id == "b":
                    raise RuntimeError("b 故意失败")
                completed_steps.append("c")
                return {"ok": True}
            completed_steps.append("d")
            return {"joined": True}

        runner = ContractRunner(contract, skill_name="dag-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        run_task = asyncio.create_task(runner.run(session=None))
        await asyncio.wait_for(branch_ready.wait(), timeout=1.0)
        release_branches.set()
        result = await run_task

        assert result.status == "partial"
        assert started_branches == {"b", "c"}
        assert completed_steps == ["a", "c"]
        assert {record.step_id: record.status for record in result.step_records} == {
            "a": "completed",
            "b": "skipped",
            "c": "completed",
            "d": "skipped",
        }

    async def test_linear_contract_behavior_remains_serial(self) -> None:
        contract = make_contract(
            step("a"),
            step("b", depends_on=["a"]),
            step("c", depends_on=["b"]),
        )
        execution_order: list[str] = []

        async def cb(event_type: str, data: Any) -> None:
            return None

        async def executor(step: SkillStep, session: Any, inputs: dict[str, Any]) -> dict[str, Any]:
            execution_order.append(step.id)
            return {"step": step.id}

        runner = ContractRunner(contract, skill_name="linear-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        result = await runner.run(session=None)

        assert result.status == "completed"
        assert execution_order == ["a", "b", "c"]
