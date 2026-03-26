"""测试 SkillContract、SkillStep、ContractResult 模型。

覆盖：模型实例化、序列化、depends_on 引用验证、循环依赖检测、trust_ceiling 约束。
"""

import pytest
from pydantic import ValidationError

from nini.models.risk import TrustLevel
from nini.models.skill_contract import ContractResult, SkillContract, SkillStep, StepExecutionRecord

# ---------------------------------------------------------------------------
# SkillStep 测试
# ---------------------------------------------------------------------------


class TestSkillStep:
    def test_instantiate_minimal(self) -> None:
        step = SkillStep(id="load_data", name="加载数据", description="加载用户数据集")
        assert step.id == "load_data"
        assert step.depends_on == []
        assert step.condition is None
        assert step.input_from == {}
        assert step.output_key is None
        assert step.trust_level == TrustLevel.T1
        assert step.review_gate is False
        assert step.retry_policy == "skip"
        assert step.tool_hint is None

    def test_serialize_to_dict(self) -> None:
        step = SkillStep(id="s1", name="步骤1", description="描述")
        d = step.model_dump()
        assert d["id"] == "s1"
        assert d["name"] == "步骤1"
        assert d["trust_level"] == TrustLevel.T1
        assert "depends_on" in d
        assert "condition" in d
        assert "input_from" in d
        assert "output_key" in d
        assert "review_gate" in d

    def test_retry_policy_valid_values(self) -> None:
        for policy in ("retry", "skip", "abort"):
            step = SkillStep(id="s", name="s", description="d", retry_policy=policy)
            assert step.retry_policy == policy

    def test_retry_policy_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            SkillStep(id="s", name="s", description="d", retry_policy="ignore")


# ---------------------------------------------------------------------------
# SkillContract 实例化与序列化
# ---------------------------------------------------------------------------


class TestSkillContractInstantiation:
    def test_instantiate_with_steps(self) -> None:
        contract = SkillContract(
            steps=[
                SkillStep(id="a", name="A", description="步骤 A"),
                SkillStep(id="b", name="B", description="步骤 B", depends_on=["a"]),
            ]
        )
        assert contract.version == "1"
        assert contract.trust_ceiling == TrustLevel.T1
        assert contract.evidence_required is False
        assert len(contract.steps) == 2

    def test_instantiate_from_yaml_dict(self) -> None:
        """从 YAML frontmatter 的 contract 段解析。"""
        raw = {
            "version": "1",
            "trust_ceiling": "t1",
            "steps": [
                {"id": "define_problem", "name": "问题定义", "description": "明确研究假设"},
                {
                    "id": "choose_design",
                    "name": "设计选择",
                    "description": "选择实验设计类型",
                    "depends_on": ["define_problem"],
                },
            ],
        }
        contract = SkillContract.model_validate(raw)
        assert len(contract.steps) == 2
        assert contract.steps[1].depends_on == ["define_problem"]


# ---------------------------------------------------------------------------
# depends_on 引用验证
# ---------------------------------------------------------------------------


class TestDependsOnValidation:
    def test_valid_dependency_passes(self) -> None:
        contract = SkillContract(
            steps=[
                SkillStep(id="a", name="A", description="A"),
                SkillStep(id="b", name="B", description="B", depends_on=["a"]),
            ]
        )
        assert contract.steps[1].depends_on == ["a"]

    def test_missing_dependency_raises(self) -> None:
        with pytest.raises(ValidationError, match="不存在的步骤 ID"):
            SkillContract(
                steps=[
                    SkillStep(id="b", name="B", description="B", depends_on=["nonexistent"]),
                ]
            )

    def test_self_dependency_detected_as_circular(self) -> None:
        """步骤自引用应被循环依赖检测捕获。"""
        with pytest.raises(ValidationError):
            SkillContract(
                steps=[
                    SkillStep(id="a", name="A", description="A", depends_on=["a"]),
                ]
            )


# ---------------------------------------------------------------------------
# 循环依赖检测
# ---------------------------------------------------------------------------


class TestCircularDependencyDetection:
    def test_mutual_dependency_raises(self) -> None:
        with pytest.raises(ValidationError, match="循环依赖"):
            SkillContract(
                steps=[
                    SkillStep(id="a", name="A", description="A", depends_on=["b"]),
                    SkillStep(id="b", name="B", description="B", depends_on=["a"]),
                ]
            )

    def test_three_node_cycle_raises(self) -> None:
        with pytest.raises(ValidationError, match="循环依赖"):
            SkillContract(
                steps=[
                    SkillStep(id="a", name="A", description="A", depends_on=["c"]),
                    SkillStep(id="b", name="B", description="B", depends_on=["a"]),
                    SkillStep(id="c", name="C", description="C", depends_on=["b"]),
                ]
            )

    def test_linear_chain_no_cycle(self) -> None:
        contract = SkillContract(
            steps=[
                SkillStep(id="a", name="A", description="A"),
                SkillStep(id="b", name="B", description="B", depends_on=["a"]),
                SkillStep(id="c", name="C", description="C", depends_on=["b"]),
            ]
        )
        assert len(contract.steps) == 3


# ---------------------------------------------------------------------------
# trust_ceiling 约束
# ---------------------------------------------------------------------------


class TestTrustCeilingConstraint:
    def test_step_within_ceiling_passes(self) -> None:
        contract = SkillContract(
            trust_ceiling=TrustLevel.T2,
            steps=[
                SkillStep(id="a", name="A", description="A", trust_level=TrustLevel.T1),
                SkillStep(id="b", name="B", description="B", trust_level=TrustLevel.T2),
            ],
        )
        assert contract.trust_ceiling == TrustLevel.T2

    def test_step_exceeds_ceiling_raises(self) -> None:
        with pytest.raises(ValidationError, match="trust_ceiling"):
            SkillContract(
                trust_ceiling=TrustLevel.T1,
                steps=[
                    SkillStep(id="a", name="A", description="A", trust_level=TrustLevel.T2),
                ],
            )

    def test_t3_exceeds_t1_ceiling(self) -> None:
        with pytest.raises(ValidationError):
            SkillContract(
                trust_ceiling=TrustLevel.T1,
                steps=[
                    SkillStep(id="a", name="A", description="A", trust_level=TrustLevel.T3),
                ],
            )


# ---------------------------------------------------------------------------
# ContractResult
# ---------------------------------------------------------------------------


class TestContractResult:
    def test_completed_status(self) -> None:
        result = ContractResult(
            status="completed",
            step_records=[StepExecutionRecord(step_id="a", status="completed", duration_ms=100)],
            total_ms=100,
        )
        assert result.status == "completed"

    def test_partial_status(self) -> None:
        result = ContractResult(
            status="partial",
            step_records=[
                StepExecutionRecord(step_id="a", status="completed"),
                StepExecutionRecord(step_id="b", status="skipped"),
            ],
        )
        assert result.status == "partial"
        assert len(result.step_records) == 2
