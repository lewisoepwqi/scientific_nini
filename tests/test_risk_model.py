"""风险分级与输出等级模型的单元测试。"""

import json

import pytest

from nini.models.risk import (
    MANDATORY_REVIEW_SCENARIOS,
    OUTPUT_LEVEL_META,
    PROHIBITED_BEHAVIORS,
    RISK_LEVEL_META,
    TRUST_CEILING_MAP,
    OutputLevel,
    RiskLevel,
    TrustLevel,
    requires_human_review,
    validate_output_level,
)
from nini.models.event_schemas import DoneEventData, TextEventData


# ---- RiskLevel 枚举测试 ----


class TestRiskLevel:
    def test_枚举值完整(self):
        values = {e.value for e in RiskLevel}
        assert values == {"low", "medium", "high", "critical"}

    def test_枚举可序列化为字符串(self):
        assert json.dumps(RiskLevel.HIGH) == '"high"'
        assert json.dumps(RiskLevel.CRITICAL) == '"critical"'

    def test_元数据可查询(self):
        meta = RISK_LEVEL_META[RiskLevel.CRITICAL]
        assert meta["name"] == "极高"
        assert "definition" in meta
        assert "example" in meta

    def test_所有等级均有元数据(self):
        for level in RiskLevel:
            assert level in RISK_LEVEL_META
            assert "name" in RISK_LEVEL_META[level]


# ---- TrustLevel 枚举测试 ----


class TestTrustLevel:
    def test_枚举值完整(self):
        values = {e.value for e in TrustLevel}
        assert values == {"t1", "t2", "t3"}

    def test_枚举可序列化为字符串(self):
        assert json.dumps(TrustLevel.T1) == '"t1"'


# ---- OutputLevel 枚举测试 ----


class TestOutputLevel:
    def test_枚举值完整(self):
        values = {e.value for e in OutputLevel}
        assert values == {"o1", "o2", "o3", "o4"}

    def test_枚举可序列化为字符串(self):
        assert json.dumps(OutputLevel.O3) == '"o3"'

    def test_元数据可查询(self):
        meta = OUTPUT_LEVEL_META[OutputLevel.O2]
        assert meta["name"] == "草稿级"
        assert "可编辑初稿" in meta["definition"]
        assert "user_expectation" in meta

    def test_所有等级均有元数据(self):
        for level in OutputLevel:
            assert level in OUTPUT_LEVEL_META
            assert "name" in OUTPUT_LEVEL_META[level]
            assert "definition" in OUTPUT_LEVEL_META[level]
            assert "user_expectation" in OUTPUT_LEVEL_META[level]


# ---- TRUST_CEILING_MAP 测试 ----


class TestTrustCeilingMap:
    def test_T1信任等级仅允许O1和O2(self):
        allowed = TRUST_CEILING_MAP[TrustLevel.T1]
        assert set(allowed) == {OutputLevel.O1, OutputLevel.O2}

    def test_T2信任等级允许O1到O3(self):
        allowed = TRUST_CEILING_MAP[TrustLevel.T2]
        assert set(allowed) == {OutputLevel.O1, OutputLevel.O2, OutputLevel.O3}

    def test_T3信任等级允许所有等级(self):
        allowed = TRUST_CEILING_MAP[TrustLevel.T3]
        assert set(allowed) == {OutputLevel.O1, OutputLevel.O2, OutputLevel.O3, OutputLevel.O4}

    def test_所有TrustLevel均有映射(self):
        for trust in TrustLevel:
            assert trust in TRUST_CEILING_MAP
            assert len(TRUST_CEILING_MAP[trust]) > 0


# ---- validate_output_level 测试 ----


class TestValidateOutputLevel:
    def test_合法组合校验通过(self):
        assert validate_output_level(TrustLevel.T2, OutputLevel.O3) is True

    def test_非法组合校验失败(self):
        assert validate_output_level(TrustLevel.T1, OutputLevel.O4) is False

    def test_T1不允许O3(self):
        assert validate_output_level(TrustLevel.T1, OutputLevel.O3) is False

    def test_T3允许O4(self):
        assert validate_output_level(TrustLevel.T3, OutputLevel.O4) is True

    def test_所有TrustLevel都允许O1(self):
        for trust in TrustLevel:
            assert validate_output_level(trust, OutputLevel.O1) is True


# ---- MANDATORY_REVIEW_SCENARIOS 测试 ----


class TestMandatoryReviewScenarios:
    def test_场景列表至少包含7项(self):
        assert len(MANDATORY_REVIEW_SCENARIOS) >= 7

    def test_包含样本量计算场景(self):
        assert any("样本量" in s for s in MANDATORY_REVIEW_SCENARIOS)

    def test_包含统计结论场景(self):
        assert any("统计结论" in s for s in MANDATORY_REVIEW_SCENARIOS)

    def test_包含临床伦理场景(self):
        assert any("临床" in s or "伦理" in s for s in MANDATORY_REVIEW_SCENARIOS)


# ---- PROHIBITED_BEHAVIORS 测试 ----


class TestProhibitedBehaviors:
    def test_禁止性规则清单包含8条(self):
        assert len(PROHIBITED_BEHAVIORS) == 8

    def test_包含草稿伪装规则(self):
        assert any("草稿级" in b for b in PROHIBITED_BEHAVIORS)

    def test_包含跳过复核门规则(self):
        assert any("复核门" in b for b in PROHIBITED_BEHAVIORS)


# ---- requires_human_review 测试 ----


class TestRequiresHumanReview:
    def test_高风险触发复核(self):
        assert requires_human_review(RiskLevel.HIGH, []) is True

    def test_极高风险触发复核(self):
        assert requires_human_review(RiskLevel.CRITICAL, []) is True

    def test_低风险且无场景标签不触发(self):
        assert requires_human_review(RiskLevel.LOW, []) is False

    def test_中风险且无场景标签不触发(self):
        assert requires_human_review(RiskLevel.MEDIUM, []) is False

    def test_低风险但命中复核场景触发(self):
        assert requires_human_review(RiskLevel.LOW, ["统计结论的最终解释"]) is True

    def test_中风险命中样本量场景触发(self):
        assert requires_human_review(RiskLevel.MEDIUM, ["样本量计算与关键参数推荐"]) is True

    def test_未命中任何场景不触发(self):
        assert requires_human_review(RiskLevel.LOW, ["普通数据预览"]) is False


# ---- DoneEventData 扩展测试 ----


class TestDoneEventDataOutputLevel:
    def test_不传output_level时默认为None(self):
        event = DoneEventData()
        assert event.output_level is None

    def test_可赋值output_level(self):
        event = DoneEventData(output_level=OutputLevel.O2)
        assert event.output_level == OutputLevel.O2

    def test_序列化包含output_level字段(self):
        event = DoneEventData(output_level=OutputLevel.O2)
        data = json.loads(event.model_dump_json())
        assert data["output_level"] == "o2"

    def test_序列化None时字段为null(self):
        event = DoneEventData()
        data = json.loads(event.model_dump_json())
        assert data["output_level"] is None


# ---- TextEventData 扩展测试 ----


class TestTextEventDataOutputLevel:
    def test_不传output_level时默认为None(self):
        event = TextEventData(content="test")
        assert event.output_level is None

    def test_可赋值output_level(self):
        event = TextEventData(content="test", output_level=OutputLevel.O1)
        assert event.output_level == OutputLevel.O1
