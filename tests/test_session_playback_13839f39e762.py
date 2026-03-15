"""端到端回放测试 - 会话 13839f39e762

会话背景：
-----------
会话 ID: 13839f39e762
问题类型: 实际使用中遇到的状态不稳定问题
主要痛点:
1. 图表写入路径不存在，导致整个绘图脚本失败
2. 合并后的中间数据集没有显式持久化，后续步骤反复报"数据集不存在"
3. 单次失败后只能重新生成大段代码，而不是对失败位置做局部修补

测试目标：
-----------
使用新工具基础层重构后，验证以下能力：
1. 中间数据集复用 - 转换步骤生成的数据集可被后续步骤稳定引用
2. 路径受管输出 - 图表/报告写入受管目录，不会路径错误
3. 局部 patch 恢复 - 失败后可以对脚本局部修补并重试

设计说明：
-----------
这是一个设计文档和测试框架。实际回放需要会话 13839f39e762 的原始消息历史，
当前实现使用模拟数据演示测试结构。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.registry import create_default_tool_registry
from nini.workspace import WorkspaceManager


# =============================================================================
# 回放数据模型
# =============================================================================

class PlaybackEvent:
    """回放事件基类。"""

    def __init__(self, turn_id: str, event_type: str, data: dict[str, Any]):
        self.turn_id = turn_id
        self.event_type = event_type
        self.data = data


class ToolCallEvent(PlaybackEvent):
    """工具调用事件。"""

    def __init__(
        self,
        turn_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        expected_resource_id: str | None = None,
    ):
        super().__init__(turn_id, "tool_call", {"tool": tool_name, "args": arguments})
        self.tool_name = tool_name
        self.arguments = arguments
        self.expected_resource_id = expected_resource_id


class UserMessageEvent(PlaybackEvent):
    """用户消息事件。"""

    def __init__(self, turn_id: str, content: str, attachments: list[str] | None = None):
        super().__init__(
            turn_id, "user_message", {"content": content, "attachments": attachments or []}
        )
        self.content = content


# =============================================================================
# 会话 13839f39e762 的关键事件序列（重构后）
# =============================================================================

def get_session_playback_events() -> list[PlaybackEvent]:
    """
    获取会话 13839f39e762 的关键回放事件。

    原始会话流程（简化）：
    1. 用户上传数据文件
    2. 进行数据清洗和合并
    3. 生成中间数据集
    4. 尝试绘制图表但路径错误导致失败
    5. 重新生成完整代码块重试

    重构后期望流程：
    1. 数据通过 dataset_catalog 加载
    2. 使用 dataset_transform 进行清洗合并，生成中间数据集
    3. 使用 chart_session 创建图表（路径由系统管理）
    4. 如失败，使用 patch_script 局部修复而非重写
    """
    return [
        # Turn 1: 加载数据
        UserMessageEvent("turn_1", "请帮我分析这份实验数据"),
        ToolCallEvent(
            "turn_1",
            "dataset_catalog",
            {"operation": "load", "file_path": "experiment_data.csv"},
            expected_resource_id="ds_experiment_001",
        ),

        # Turn 2: 数据清洗和转换
        UserMessageEvent("turn_2", "请清洗数据，合并重复项并创建月份列"),
        ToolCallEvent(
            "turn_2",
            "dataset_transform",
            {
                "operation": "run",
                "input_datasets": ["experiment_data"],
                "steps": [
                    {"id": "clean", "op": "clean_data", "params": {"remove_duplicates": True}},
                    {"id": "derive_month", "op": "derive_column", "params": {"column": "month", "expr": "date.dt.month"}},
                ],
                "output_dataset_name": "cleaned_data",
            },
            expected_resource_id="tf_clean_001",
        ),

        # Turn 3: 创建图表（使用 chart_session 而非直接代码）
        UserMessageEvent("turn_3", "绘制月度趋势图"),
        ToolCallEvent(
            "turn_3",
            "chart_session",
            {
                "operation": "create",
                "chart_id": "chart_monthly_trend",
                "dataset_name": "cleaned_data",
                "chart_type": "line",
                "x_column": "month",
                "y_column": "value",
                "title": "月度趋势分析",
            },
            expected_resource_id="chart_monthly_trend",
        ),

        # Turn 4: 导出图表
        ToolCallEvent(
            "turn_4",
            "chart_session",
            {
                "operation": "export",
                "chart_id": "chart_monthly_trend",
                "format": "png",
                "filename": "monthly_trend",
            },
        ),
    ]


# =============================================================================
# 端到端回放测试
# =============================================================================

@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离测试数据目录。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    yield


class TestSessionPlayback13839f39e762:
    """
    端到端回放测试：会话 13839f39e762

    验证重构后的工具基础层解决原会话中的问题。
    """

    def test_intermediate_dataset_reuse(self):
        """
        测试：中间数据集复用

        原问题：
        - 合并后的中间数据集没有显式持久化
        - 后续步骤反复报"数据集不存在"

        验证点：
        - dataset_transform 生成的中间数据集可被后续步骤稳定引用
        - 资源索引正确记录了中间数据集
        """
        registry = create_default_tool_registry()
        session = Session()

        # 模拟原始数据
        raw_data = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10),
            "value": [10, 12, 11, 13, 15, 14, 16, 18, 17, 19],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["raw_data"] = raw_data

        # 步骤1: 数据转换生成中间数据集
        result = self._run_transform(
            registry,
            session,
            input_datasets=["raw_data"],
            steps=[
                {"id": "derive", "op": "derive_column", "params": {"column": "month", "expr": "date.dt.month"}},
            ],
            output_dataset_name="intermediate_data",
        )

        assert result["success"] is True
        transform_id = result["data"]["transform_id"]

        # 验证中间数据集已在会话中
        assert "intermediate_data" in session.datasets

        # 验证中间数据集已注册为资源
        manager = WorkspaceManager(session.id)
        resource = manager.get_resource_summary(transform_id)
        assert resource is not None
        assert resource["source_kind"] == "transforms"

        # 步骤2: 后续分析引用中间数据集（不应报错）
        # 使用 code_session 引用中间数据集进行进一步分析
        import asyncio

        code_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="create_script",
                script_id="analyze_intermediate",
                language="python",
                content="result = len(df)",
            )
        )
        assert code_result["success"] is True

        run_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="run_script",
                script_id="analyze_intermediate",
                dataset_name="intermediate_data",  # 引用中间数据集
                intent="分析中间数据集",
            )
        )

        assert run_result["success"] is True, "应能稳定引用中间数据集"

    def test_managed_path_output(self):
        """
        测试：路径受管输出

        原问题：
        - 图表写入路径不存在，导致整个绘图脚本失败
        - 模型依赖自由路径写入最终产物

        验证点：
        - chart_session 创建的图表资源由系统管理路径
        - 导出操作使用受管目录，不会路径错误
        """
        registry = create_default_tool_registry()
        session = Session()

        # 准备数据
        session.datasets["data"] = pd.DataFrame({
            "x": [1, 2, 3],
            "y": [4, 5, 6],
        })

        # 创建图表会话
        result = self._run_chart_create(
            registry,
            session,
            chart_id="managed_chart",
            dataset_name="data",
        )

        assert result["success"] is True

        # 验证图表资源已注册
        manager = WorkspaceManager(session.id)
        chart_resource = manager.get_resource_summary("managed_chart")
        assert chart_resource is not None

        # 验证图表路径在受管目录内
        chart_path = chart_resource.get("path")
        if chart_path:
            assert "charts" in str(chart_path), "图表应在受管 charts 目录内"

        # 验证可以成功导出（不会因为路径问题失败）
        export_result = self._run_chart_export(
            registry,
            session,
            chart_id="managed_chart",
            format="json",
        )

        assert export_result["success"] is True, "导出不应因路径问题失败"

    def test_partial_patch_recovery(self):
        """
        测试：局部 patch 恢复

        原问题：
        - 单次失败后只能重新生成大段代码
        - 不能对失败位置做局部修补

        验证点：
        - 脚本失败后可以使用 patch_script 局部修改
        - rerun 可以重用之前的上下文
        - 执行历史记录重试关联
        """
        import asyncio

        registry = create_default_tool_registry()
        session = Session()
        session.datasets["data"] = pd.DataFrame({"x": [1, 2, 3]})

        # 步骤1: 创建包含错误的脚本
        create_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="create_script",
                script_id="recovery_test",
                language="python",
                content=(
                    "# 数据预处理\n"
                    "processed = df.copy()\n"
                    "processed['scaled'] = processed['x'] * 2\n"
                    "# 绘图\n"
                    "import matplotlib.pyplot as plt\n"
                    "plt.plot([1, 2, undefined_variable])  # 第6行: 错误在这里\n"  # 故意错误
                    "plt.savefig('/tmp/test.png')\n"
                ),
            )
        )

        assert create_result["success"] is True

        # 步骤2: 执行失败
        run_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="run_script",
                script_id="recovery_test",
                dataset_name="data",
                intent="测试恢复",
            )
        )

        assert run_result["success"] is False
        first_exec_id = run_result["data"]["execution_id"]

        # 验证错误定位信息
        assert "error_location" in run_result["data"]
        assert run_result["data"]["error_location"]["line"] == 6

        # 步骤3: 局部 patch（只修改错误行，不重写整个脚本）
        patch_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="patch_script",
                script_id="recovery_test",
                patch={
                    "mode": "replace_string",
                    "old_string": "plt.plot([1, 2, undefined_variable])",
                    "new_string": "plt.plot([1, 2, 3])",
                },
            )
        )

        assert patch_result["success"] is True

        # 步骤4: 使用 rerun 重试（保留之前的上下文和输出路径）
        retry_result = asyncio.run(
            registry.execute(
                "code_session",
                session=session,
                operation="rerun",
                script_id="recovery_test",
                dataset_name="data",
                intent="修复后重试",
            )
        )

        assert retry_result["success"] is True, "局部修补后应成功"

        # 验证执行历史记录了重试关联
        manager = WorkspaceManager(session.id)
        second_exec = manager.get_code_execution(retry_result["data"]["execution_id"])
        assert second_exec is not None
        assert second_exec.get("retry_of_execution_id") == first_exec_id

    # ==========================================================================
    # 辅助方法
    # ==========================================================================

    def _run_transform(
        self, registry, session, input_datasets: list[str], steps: list[dict], output_dataset_name: str
    ) -> dict:
        """执行数据转换。"""
        import asyncio

        return asyncio.run(
            registry.execute(
                "dataset_transform",
                session=session,
                operation="run",
                input_datasets=input_datasets,
                steps=steps,
                output_dataset_name=output_dataset_name,
            )
        )

    def _run_chart_create(
        self, registry, session, chart_id: str, dataset_name: str
    ) -> dict:
        """创建图表会话。"""
        import asyncio

        return asyncio.run(
            registry.execute(
                "chart_session",
                session=session,
                operation="create",
                chart_id=chart_id,
                dataset_name=dataset_name,
                chart_type="line",
                x_column="x",
                y_column="y",
            )
        )

    def _run_chart_export(
        self, registry, session, chart_id: str, format: str
    ) -> dict:
        """导出图表。"""
        import asyncio

        return asyncio.run(
            registry.execute(
                "chart_session",
                session=session,
                operation="export",
                chart_id=chart_id,
                format=format,
                filename=f"{chart_id}_export",
            )
        )


# =============================================================================
# 回放测试基础设施（待扩展）
# =============================================================================

class SessionPlaybackRunner:
    """
    会话回放运行器。

    未来可扩展功能：
    1. 从实际会话文件加载事件序列
    2. 对比重构前后的执行结果
    3. 生成执行报告
    """

    def __init__(self, session_id: str, data_dir: Path):
        self.session_id = session_id
        self.data_dir = data_dir
        self.events: list[PlaybackEvent] = []
        self.results: list[dict] = []

    def load_events_from_session_file(self, path: Path) -> None:
        """从会话文件加载事件。"""
        # TODO: 实现从实际会话历史加载
        pass

    def run(self) -> dict[str, Any]:
        """运行回放。"""
        # TODO: 实现完整回放逻辑
        return {"success": True, "events_executed": 0, "failures": []}


# =============================================================================
# 标记：需要实际会话数据
# =============================================================================

# 注意：此测试文件使用模拟数据演示测试结构。
# 要进行完整回放测试，需要：
# 1. 会话 13839f39e762 的 memory.jsonl 文件
# 2. 原始上传的数据文件
# 3. 原始会话的执行历史
#
# 这些数据可从生产环境的 data/sessions/13839f39e762/ 目录获取。
# 获取后，可以实现 SessionPlaybackRunner.load_events_from_session_file() 方法
# 来加载实际事件序列。
#
# 当前使用模拟数据运行基础测试，完整回放测试需要实际会话数据。
