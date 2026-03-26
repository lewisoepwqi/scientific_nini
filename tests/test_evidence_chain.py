"""证据链模型、收集器与契约集成测试。"""

from typing import Any

import pytest
from pydantic import ValidationError

from nini.agent.evidence_collector import EvidenceCollector
from nini.agent.session import Session
from nini.models.session_resources import EvidenceChain, EvidenceNode
from nini.models.skill_contract import SkillContract, SkillStep
from nini.models.risk import TrustLevel
from nini.skills.contract_runner import ContractRunner
from nini.tools.query_evidence import QueryEvidenceTool
from nini.tools.registry import create_default_tool_registry


def _step(
    step_id: str,
    *,
    depends_on: list[str] | None = None,
    tool_hint: str | None = None,
) -> SkillStep:
    return SkillStep(
        id=step_id,
        name=step_id,
        description=step_id,
        depends_on=depends_on or [],
        tool_hint=tool_hint,
        trust_level=TrustLevel.T1,
    )


class TestEvidenceModels:
    def test_evidence_node_creation(self) -> None:
        node = EvidenceNode(id="n1", node_type="data", label="blood_pressure.csv")
        assert node.id == "n1"
        assert node.parent_ids == []

    def test_evidence_node_type_validation(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceNode(id="n2", node_type="unsupported", label="bad")  # type: ignore[arg-type]

    def test_evidence_chain_creation(self) -> None:
        chain = EvidenceChain(
            session_id="session-1",
            nodes=[
                EvidenceNode(id="data-1", node_type="data", label="blood_pressure.csv"),
                EvidenceNode(
                    id="analysis-1",
                    node_type="analysis",
                    label="t_test",
                    parent_ids=["data-1"],
                ),
            ],
        )
        assert len(chain.nodes) == 2


class TestEvidenceCollector:
    def test_add_nodes_and_get_upstream_chain(self) -> None:
        collector = EvidenceCollector("session-1")
        data_node = collector.add_data_node("blood_pressure.csv")
        analysis_node = collector.add_analysis_node(
            "t_test",
            params={"alpha": 0.05},
            result_ref="stat:1",
            parent_ids=[data_node.id],
        )
        conclusion_node = collector.add_conclusion_node(
            "治疗组血压显著低于对照组",
            parent_ids=[analysis_node.id],
        )

        chain = collector.get_chain_for(conclusion_node.id)
        assert [node.node_type for node in chain.nodes] == ["conclusion", "analysis", "data"]
        assert chain.nodes[0].label == "治疗组血压显著低于对照组"


class TestQueryEvidenceTool:
    async def test_query_returns_matching_chain(self) -> None:
        session = Session()
        data_node = session.evidence_collector.add_data_node("blood_pressure.csv")
        analysis_node = session.evidence_collector.add_analysis_node(
            "t_test",
            parent_ids=[data_node.id],
            result_ref="stat:1",
        )
        session.evidence_collector.add_conclusion_node(
            "治疗组血压显著低于对照组",
            parent_ids=[analysis_node.id],
        )

        result = await QueryEvidenceTool().execute(session, query="显著低于")

        assert result.success is True
        assert result.data["matches"][0]["node_type"] == "conclusion"
        assert [node["node_type"] for node in result.data["chains"][0]["nodes"]] == [
            "conclusion",
            "analysis",
            "data",
        ]

    async def test_query_returns_empty_when_no_match(self) -> None:
        session = Session()
        result = await QueryEvidenceTool().execute(session, query="不存在的结论")
        assert result.success is True
        assert result.data["matches"] == []


class TestContractRunnerEvidenceIntegration:
    async def test_collects_evidence_when_required(self) -> None:
        contract = SkillContract(
            evidence_required=True,
            steps=[
                _step("load_data", tool_hint="load_dataset"),
                _step("run_test", depends_on=["load_data"], tool_hint="stat_test"),
                _step("summarize", depends_on=["run_test"], tool_hint="report_summary"),
            ],
        )
        session = Session()

        async def cb(event_type: str, data: Any) -> None:
            return None

        async def executor(step: SkillStep, session: Session, inputs: dict[str, Any]) -> dict[str, Any]:
            if step.id == "load_data":
                return {"dataset_name": "blood_pressure.csv"}
            if step.id == "run_test":
                return {
                    "data": {
                        "dataset_name": "blood_pressure.csv",
                        "params": {"method": "independent_t"},
                        "result_ref": "stat:1",
                    }
                }
            return {"claim": "治疗组血压显著低于对照组"}

        runner = ContractRunner(contract, skill_name="evidence-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        result = await runner.run(session=session)

        assert result.status == "completed"
        assert result.evidence_chain is not None
        assert [node.node_type for node in result.evidence_chain.nodes] == [
            "data",
            "analysis",
            "conclusion",
        ]
        final_chain = session.evidence_collector.get_chain_for(result.evidence_chain.nodes[-1].id)
        assert [node.node_type for node in final_chain.nodes] == ["conclusion", "analysis", "data"]

    async def test_skips_evidence_collection_when_not_required(self) -> None:
        contract = SkillContract(
            evidence_required=False,
            steps=[_step("run_test", tool_hint="stat_test")],
        )
        session = Session()

        async def cb(event_type: str, data: Any) -> None:
            return None

        async def executor(step: SkillStep, session: Session, inputs: dict[str, Any]) -> dict[str, Any]:
            return {"data": {"dataset_name": "blood_pressure.csv", "result_ref": "stat:1"}}

        runner = ContractRunner(contract, skill_name="plain-skill", callback=cb)
        runner._step_executor = executor  # type: ignore[attr-defined]

        result = await runner.run(session=session)

        assert result.evidence_chain is None
        assert session.evidence_collector.chain.nodes == []


def test_query_evidence_registered_in_default_registry() -> None:
    registry = create_default_tool_registry()
    assert registry.get("query_evidence") is not None
