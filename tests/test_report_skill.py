"""报告生成技能测试 — 去噪、图表预览、双轨输出。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nini.skills.report import (
    _build_markdown,
    _chart_preview_markdown,
    _make_downloadable_markdown,
    _strip_tool_mentions,
)

# ---------------------------------------------------------------------------
# _strip_tool_mentions
# ---------------------------------------------------------------------------


class TestStripToolMentions:
    def test_removes_single_tool_mention(self):
        text = "使用 data_summary 工具进行系统性评估"
        result = _strip_tool_mentions(text)
        assert "data_summary" not in result
        assert "工具" not in result

    def test_removes_multiple_tools(self):
        text = "使用 data_summary 和 recommend_cleaning_strategy 工具进行分析"
        result = _strip_tool_mentions(text)
        assert "data_summary" not in result
        assert "recommend_cleaning_strategy" not in result

    def test_removes_backtick_tool_names(self):
        text = "调用 `create_chart` 工具绘制图表"
        result = _strip_tool_mentions(text)
        assert "create_chart" not in result

    def test_preserves_normal_text(self):
        text = "采用独立样本 t 检验分析两组差异"
        result = _strip_tool_mentions(text)
        assert result == text

    def test_empty_input(self):
        assert _strip_tool_mentions("") == ""
        assert _strip_tool_mentions("   ") == ""

    def test_removes_through_tool(self):
        text = "通过 run_code 工具执行自定义分析"
        result = _strip_tool_mentions(text)
        assert "run_code" not in result

    def test_mixed_content(self):
        text = "先使用 load_dataset 工具加载数据，然后进行 Pearson 相关性分析"
        result = _strip_tool_mentions(text)
        assert "load_dataset" not in result
        assert "Pearson 相关性分析" in result


# ---------------------------------------------------------------------------
# _make_downloadable_markdown
# ---------------------------------------------------------------------------


class TestMakeDownloadableMarkdown:
    def test_replaces_plotly_with_png_when_exists(self, tmp_path: Path):
        session_id = "test-session"
        md = "![scatter](/api/artifacts/test-session/scatter.plotly.json)"

        with patch("nini.skills.report.ArtifactStorage") as MockStorage:
            mock_storage = MockStorage.return_value
            png_path = tmp_path / "scatter.png"
            png_path.write_bytes(b"fake png")
            mock_storage.get_path.side_effect = lambda name: (
                png_path if name == "scatter.png" else tmp_path / name
            )

            result = _make_downloadable_markdown(md, session_id)
            assert "scatter.png" in result
            assert "plotly.json" not in result

    def test_adds_comment_when_no_png(self, tmp_path: Path):
        session_id = "test-session"
        md = "![chart](/api/artifacts/test-session/chart.plotly.json)"

        with patch("nini.skills.report.ArtifactStorage") as MockStorage:
            mock_storage = MockStorage.return_value
            # get_path returns non-existent paths
            mock_storage.get_path.return_value = tmp_path / "nonexistent"

            with patch("nini.skills.report._try_export_plotly_to_png", return_value=None):
                result = _make_downloadable_markdown(md, session_id)
                assert "<!-- 图表 chart 需在应用内查看" in result
                assert "plotly.json" not in result

    def test_converts_api_paths_to_relative(self, tmp_path: Path):
        session_id = "test-session"
        md = "![boxplot](/api/artifacts/test-session/boxplot.png)"

        with patch("nini.skills.report.ArtifactStorage") as MockStorage:
            mock_storage = MockStorage.return_value
            mock_storage.get_path.return_value = tmp_path / "nonexistent"

            result = _make_downloadable_markdown(md, session_id)
            assert result == "![boxplot](./boxplot.png)"

    def test_empty_input(self):
        assert _make_downloadable_markdown("", "s") == ""


# ---------------------------------------------------------------------------
# _build_markdown (no chart list)
# ---------------------------------------------------------------------------


class TestBuildMarkdownNoChartList:
    def _make_session(self) -> MagicMock:
        session = MagicMock()
        session.id = "test-session"
        session.datasets = {}
        session.messages = []
        return session

    @patch(
        "nini.skills.report._chart_preview_markdown",
        return_value="### 图 1：scatter\n![scatter](/url)",
    )
    @patch("nini.skills.report._chart_artifacts_markdown", return_value="| 图表文件 | ... |")
    def test_no_chart_list_section(self, mock_chart_list, mock_preview):
        session = self._make_session()
        md = _build_markdown(
            session,
            title="测试报告",
            dataset_names=None,
            summary_text="摘要",
            methods="方法",
            conclusions="结论",
            include_recent_messages=False,
            include_charts=True,
            include_session_stats=False,
        )
        assert "## 图表" in md
        assert "## 图表清单" not in md
        # _chart_artifacts_markdown should NOT be called
        mock_chart_list.assert_not_called()

    def test_no_charts_when_disabled(self):
        session = self._make_session()
        md = _build_markdown(
            session,
            title="测试报告",
            dataset_names=None,
            summary_text="",
            methods="",
            conclusions="",
            include_recent_messages=False,
            include_charts=False,
            include_session_stats=False,
        )
        assert "## 图表" not in md


# ---------------------------------------------------------------------------
# execute() dual-track output
# ---------------------------------------------------------------------------


class TestExecuteDualTrack:
    @pytest.mark.asyncio
    async def test_preview_vs_download_differ(self, tmp_path: Path):
        """execute() 返回的 preview_md 保留 plotly.json，保存的文件使用 PNG/相对路径。"""
        session = MagicMock()
        session.id = "dual-track-test"
        session.datasets = {}
        session.messages = []
        session.artifacts = {}
        session.knowledge_memory = MagicMock()

        from nini.skills.report import GenerateReportSkill

        skill = GenerateReportSkill()

        # 模拟图表产物
        charts = [
            {
                "name": "scatter.plotly.json",
                "type": "chart",
                "format": "json",
                "download_url": "/api/artifacts/dual-track-test/scatter.plotly.json",
            }
        ]

        png_path = tmp_path / "scatter.png"
        png_path.write_bytes(b"fake png data")

        with (
            patch("nini.skills.report._collect_chart_artifacts", return_value=charts),
            patch("nini.skills.report.ArtifactStorage") as MockStorage,
            patch("nini.skills.report.WorkspaceManager"),
        ):
            mock_storage = MockStorage.return_value
            mock_storage.get_path.side_effect = lambda name: (
                png_path if name == "scatter.png" else tmp_path / name
            )
            mock_storage.save_text.return_value = tmp_path / "report.md"

            result = await skill.execute(
                session,
                title="双轨测试",
                methods="独立样本 t 检验",
                include_charts=True,
                include_session_stats=False,
                save_to_knowledge=False,
            )

            assert result.success
            preview_md = result.data["report_markdown"]
            # 预览版保留 plotly.json
            assert "plotly.json" in preview_md

            # 保存版使用 PNG
            saved_content = mock_storage.save_text.call_args[0][0]
            assert "scatter.png" in saved_content
            assert "plotly.json" not in saved_content
