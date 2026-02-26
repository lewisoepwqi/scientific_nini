"""ANOVA 改进回归测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session


class TestANOVABoundaries:
    @pytest.mark.asyncio
    async def test_anova_less_than_2_groups(self) -> None:
        """验证 1 组时友好错误。"""
        pytest.importorskip("scipy")
        from nini.tools.statistics import ANOVASkill

        session = Session()
        session.datasets["one_group.csv"] = pd.DataFrame(
            {
                "group": ["A", "A", "A"],
                "value": [1.0, 1.5, 2.0],
            }
        )

        result = await ANOVASkill().execute(
            session,
            dataset_name="one_group.csv",
            value_column="value",
            group_column="group",
        )
        assert result.success is False
        assert "单样本 t 检验" in result.message

    @pytest.mark.asyncio
    async def test_anova_2_groups_hint_t_test(self) -> None:
        """验证 2 组时提示使用 t_test。"""
        pytest.importorskip("scipy")
        from nini.tools.statistics import ANOVASkill

        session = Session()
        session.datasets["two_groups.csv"] = pd.DataFrame(
            {
                "group": ["A", "A", "A", "B", "B", "B"],
                "value": [1.0, 1.1, 0.9, 1.8, 1.9, 2.0],
            }
        )

        result = await ANOVASkill().execute(
            session,
            dataset_name="two_groups.csv",
            value_column="value",
            group_column="group",
        )
        assert result.success is True
        assert isinstance(result.data, dict)
        assert "recommendation" in result.data
        assert "t_test" in str(result.data["recommendation"])

    @pytest.mark.asyncio
    async def test_anova_post_hoc_trigger_p_boundary(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """验证 p=0.05 触发事后检验。"""
        pytest.importorskip("scipy")
        from nini.tools.statistics import ANOVASkill
        import nini.tools.statistics as statistics_module

        session = Session()
        session.datasets["three_groups.csv"] = pd.DataFrame(
            {
                "group": ["A"] * 10 + ["B"] * 10 + ["C"] * 10,
                "value": np.linspace(1.0, 3.0, 30),
            }
        )

        monkeypatch.setattr(statistics_module, "f_oneway", lambda *_args: (3.2, 0.05))

        class _DummyTukey:
            groupsunique = np.array(["A", "B", "C"])
            pvalues = np.array([0.049, 0.051, 0.05])
            meandiffs = np.array([0.2, 0.1, 0.3])
            reject = np.array([True, False, True])

        monkeypatch.setattr(
            statistics_module, "pairwise_tukeyhsd", lambda *_args, **_kwargs: _DummyTukey()
        )

        result = await ANOVASkill().execute(
            session,
            dataset_name="three_groups.csv",
            value_column="value",
            group_column="group",
        )
        assert result.success is True
        assert isinstance(result.data, dict)
        assert result.data["significant"] is True
        assert "post_hoc" in result.data
        assert "post_hoc_recommendation" in result.data
        assert result.data["post_hoc_recommendation"]["triggered"] is True
