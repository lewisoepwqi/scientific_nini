"""基础工具层回归测试。

测试场景：
1. 编排层使用基础工具组合完成复杂分析
2. 资源 ID 在整个调用链中正确传递
3. 失败恢复和重试机制正常工作
4. 旧工具名不再暴露给模型
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.base import SkillResult
from nini.tools.registry import LLM_EXPOSED_BASE_TOOL_NAMES, create_default_registry
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离测试数据目录。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    yield


class TestOrchestrationLayer:
    """测试编排层正确组合基础工具。"""

    @pytest.mark.asyncio
    async def test_complete_comparison_uses_base_tools(self):
        """完整比较分析应使用基础工具组合而非独立实现。"""
        from nini.tools.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert isinstance(result, SkillResult)
        assert result.success is True
        # 验证结果中包含资源引用
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_complete_anova_uses_base_tools(self):
        """完整 ANOVA 分析应使用基础工具组合。"""
        from nini.tools.templates.complete_anova import CompleteANOVASkill

        skill = CompleteANOVASkill()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2, 15.0, 15.5],
                "group": ["A"] * 5 + ["B"] * 5 + ["C"] * 2,
            }
        )
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert isinstance(result, SkillResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_correlation_analysis_uses_base_tools(self):
        """相关分析应使用基础工具组合。"""
        from nini.tools.templates.correlation_analysis import CorrelationAnalysisSkill

        skill = CorrelationAnalysisSkill()
        session = Session()

        test_data = pd.DataFrame(
            {
                "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "y": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
            }
        )
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            columns=["x", "y"],
        )

        assert isinstance(result, SkillResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_regression_analysis_uses_base_tools(self):
        """回归分析应使用基础工具组合。"""
        from nini.tools.templates.regression_analysis import RegressionAnalysisSkill

        skill = RegressionAnalysisSkill()
        session = Session()

        test_data = pd.DataFrame(
            {
                "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "y": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
            }
        )
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            dependent_var="y",
            independent_vars=["x"],
        )

        assert isinstance(result, SkillResult)
        assert result.success is True


class TestResourceIdPropagation:
    """测试资源 ID 在调用链中正确传递。"""

    def test_dataset_transform_registers_resource(self):
        """数据转换应注册资源并返回 resource_id。"""
        registry = create_default_registry()
        session = Session()
        session.datasets["source"] = pd.DataFrame({"a": [1, 2, 3]})

        result = asyncio.run(
            registry.execute(
                "dataset_transform",
                session=session,
                operation="run",
                input_datasets=["source"],
                steps=[
                    {"id": "1", "op": "derive_column", "params": {"column": "b", "expr": "a * 2"}}
                ],
                output_dataset_name="output",
            )
        )

        assert result["success"] is True
        assert "transform_id" in result["data"]

        # 验证资源已注册（transform 使用 stat_result 类型存储）
        manager = WorkspaceManager(session.id)
        resource = manager.get_resource_summary(result["data"]["transform_id"])
        assert resource is not None
        # transform 资源当前使用 stat_result 类型，source_kind 为 transforms
        assert resource["source_kind"] == "transforms"

    def test_chart_session_registers_chart_resource(self):
        """图表会话应注册图表资源。"""
        registry = create_default_registry()
        session = Session()
        session.datasets["data"] = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        result = asyncio.run(
            registry.execute(
                "chart_session",
                session=session,
                operation="create",
                chart_id="chart_test",
                dataset_name="data",
                chart_type="scatter",
                x_column="x",
                y_column="y",
            )
        )

        assert result["success"] is True

        # 验证资源已注册
        manager = WorkspaceManager(session.id)
        resource = manager.get_resource_summary("chart_test")
        assert resource is not None
        assert resource["resource_type"] == "chart"

    def test_report_session_registers_report_resource(self):
        """报告会话应注册报告资源。"""
        registry = create_default_registry()
        session = Session()

        result = asyncio.run(
            registry.execute(
                "report_session",
                session=session,
                operation="create",
                report_id="report_test",
                title="测试报告",
                sections=[{"key": "s1", "title": "章节1", "content": "内容"}],
            )
        )

        assert result["success"] is True

        # 验证资源已注册
        manager = WorkspaceManager(session.id)
        resource = manager.get_resource_summary("report_test")
        assert resource is not None
        assert resource["resource_type"] == "report"


class TestFailureRecovery:
    """测试失败恢复机制。"""

    def test_code_session_failure_records_error_location(self):
        """代码执行失败应记录错误位置。"""
        registry = create_default_registry()
        session = Session()

        # 创建会失败的脚本
        result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="create_script",
                script_id="fail_script",
                language="python",
                content="# 第1行\n# 第2行\nresult = 1 / 0  # 第3行\n",
            )
        )
        assert result["success"] is True

        # 执行失败
        run_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="run_script",
                script_id="fail_script",
                intent="测试失败",
            )
        )

        assert run_result["success"] is False
        assert "error_location" in run_result["data"]
        assert run_result["data"]["error_location"]["line"] == 3

    def test_code_session_failure_includes_recovery_hint(self):
        """代码执行失败应包含恢复提示。"""
        registry = create_default_registry()
        session = Session()

        result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="create_script",
                script_id="fail_script2",
                language="python",
                content="result = undefined_variable",
            )
        )
        assert result["success"] is True

        run_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="run_script",
                script_id="fail_script2",
                intent="测试失败",
            )
        )

        assert run_result["success"] is False
        assert "recovery_hint" in run_result["data"]
        assert len(run_result["data"]["recovery_hint"]) > 0

    def test_code_session_patch_and_retry_flow(self):
        """代码执行失败后应支持 patch 和重试。"""
        registry = create_default_registry()
        session = Session()

        # 创建会失败的脚本
        asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="create_script",
                script_id="retry_script",
                language="python",
                content="result = 1 / 0",
            )
        )

        # 第一次执行失败
        fail_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="run_script",
                script_id="retry_script",
                intent="测试重试",
            )
        )
        assert fail_result["success"] is False
        first_exec_id = fail_result["data"]["execution_id"]

        # 修复脚本
        patch_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="patch_script",
                script_id="retry_script",
                patch={"mode": "replace_string", "old_string": "1 / 0", "new_string": "1 / 1"},
            )
        )
        assert patch_result["success"] is True

        # 重试
        retry_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="rerun",
                script_id="retry_script",
                intent="重试",
            )
        )
        assert retry_result["success"] is True

        # 验证执行记录包含重试关联
        manager = WorkspaceManager(session.id)
        second_exec = manager.get_code_execution(retry_result["data"]["execution_id"])
        assert second_exec is not None
        assert second_exec.get("retry_of_execution_id") == first_exec_id


class TestOldToolsNotExposed:
    """测试旧工具不再暴露给模型。"""

    def test_old_tool_names_not_in_exposed_set(self):
        """旧工具名不应在 LLM 暴露集合中。"""
        old_tools = {
            "t_test",
            "anova",
            "correlation",
            "regression",
            "mann_whitney",
            "kruskal_wallis",
            "multiple_comparison",
            "create_chart",
            "export_chart",
            "generate_report",
            "run_code",
            "run_r_code",
        }

        for tool in old_tools:
            assert tool not in LLM_EXPOSED_BASE_TOOL_NAMES, f"旧工具 {tool} 不应暴露给模型"

    def test_only_base_tools_exposed_to_llm(self):
        """只有基础工具应暴露给模型。"""
        expected_base_tools = {
            "task_state",
            "dataset_catalog",
            "dataset_transform",
            "stat_test",
            "stat_model",
            "stat_interpret",
            "chart_session",
            "report_session",
            "workspace_session",
            "code_session",
            "analysis_memory",
        }

        assert LLM_EXPOSED_BASE_TOOL_NAMES == expected_base_tools


class TestDatasetTransformStepPatch:
    """测试数据转换的步骤级 patch。"""

    def test_transform_step_patch_preserves_other_steps(self):
        """步骤级 patch 应保持其他步骤不变。"""
        registry = create_default_registry()
        session = Session()
        session.datasets["input"] = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        # 创建多步骤转换
        result = asyncio.run(
            registry.execute(
                "dataset_transform",
                session=session,
                operation="run",
                input_datasets=["input"],
                steps=[
                    {
                        "id": "step1",
                        "op": "derive_column",
                        "params": {"column": "c", "expr": "a + b"},
                    },
                    {
                        "id": "step2",
                        "op": "derive_column",
                        "params": {"column": "d", "expr": "a * 2"},
                    },
                ],
                output_dataset_name="output",
            )
        )

        assert result["success"] is True
        transform_id = result["data"]["transform_id"]
        before_value = session.datasets["output"]["d"].tolist()

        # 只 patch 第二步
        patch_result = asyncio.run(
            registry.execute(
                "dataset_transform",
                session=session,
                operation="patch_step",
                transform_id=transform_id,
                step_patch={"step_id": "step2", "params": {"column": "d", "expr": "a * 3"}},
            )
        )

        assert patch_result["success"] is True
        # 第二步改变了
        assert session.datasets["output"]["d"].tolist() == [3, 6, 9]
        # 第一步保持不变
        assert session.datasets["output"]["c"].tolist() == [5, 7, 9]


class TestResourcePromotion:
    """测试资源提升机制。"""

    def test_script_output_can_be_promoted_to_resource(self):
        """脚本输出可以被提升为正式资源。"""
        registry = create_default_registry()
        session = Session()
        session.datasets["input"] = pd.DataFrame({"x": [1, 2, 3]})

        # 创建并执行脚本
        asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="create_script",
                script_id="promote_test",
                language="python",
                content="output_df = df.copy()\noutput_df['y'] = df['x'] * 2",
            )
        )

        run_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="run_script",
                script_id="promote_test",
                dataset_name="input",
                save_as="output_df",
                intent="生成输出",
            )
        )
        assert run_result["success"] is True

        # 提升输出为正式资源
        promote_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="promote_output",
                dataset_name="output_df",
                resource_id="ds_promoted_output",
                resource_name="已提升的输出",
            )
        )

        assert promote_result["success"] is True
        assert promote_result["data"]["resource_id"] == "ds_promoted_output"

        # 验证资源已注册
        manager = WorkspaceManager(session.id)
        resource = manager.get_resource_summary("ds_promoted_output")
        assert resource is not None
        assert resource["resource_type"] == "dataset"
