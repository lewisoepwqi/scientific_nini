"""ExportReportSkill 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from nini.tools.export_report import (
    ExportReportSkill,
    _md_to_html,
    _normalize_plotly_figure_payload,
    _resolve_images_to_base64,
    _resolve_images_to_base64_with_stats,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def skill() -> ExportReportSkill:
    return ExportReportSkill()


@pytest.fixture()
def mock_session(tmp_path: Path) -> MagicMock:
    session = MagicMock()
    session.id = "test-session-001"
    session.artifacts = {}
    session.datasets = {}
    session.messages = []
    return session


@pytest.fixture()
def setup_report(tmp_path: Path, mock_session: MagicMock) -> Path:
    """在临时目录中创建报告文件，并 patch settings.sessions_dir。"""
    sessions_dir = tmp_path / "sessions"
    artifacts_dir = sessions_dir / mock_session.id / "workspace" / "artifacts"
    artifacts_dir.mkdir(parents=True)

    md_content = "# 测试报告\n\n## 数据集概览\n\n这是一份测试报告。\n"
    report_path = artifacts_dir / "test_report.md"
    report_path.write_text(md_content, encoding="utf-8")

    mock_session.artifacts["latest_report"] = {
        "name": "test_report.md",
        "type": "report",
        "path": str(report_path),
    }
    return sessions_dir


# ---------------------------------------------------------------------------
# Tests: _md_to_html
# ---------------------------------------------------------------------------


def test_md_to_html_basic():
    html = _md_to_html("# Hello\n\nWorld", "Test Title")
    assert "<html" in html
    assert "<title>Test Title</title>" in html
    assert "<h1" in html
    assert "World" in html


def test_md_to_html_includes_cjk_fonts():
    html = _md_to_html("# 中文测试", "中文标题")
    assert "Noto Sans CJK SC" in html
    assert "Microsoft YaHei" in html
    assert "SimHei" in html


def test_md_to_html_embeds_local_cjk_font(tmp_path: Path):
    data_dir = tmp_path / "data"
    font_dir = data_dir / "fonts"
    font_dir.mkdir(parents=True)
    font_path = font_dir / "NotoSansCJKsc-Regular.otf"
    font_path.write_bytes(b"fake-font-bytes")

    with patch("nini.tools.export_report.settings") as mock_settings:
        mock_settings.data_dir = data_dir
        html = _md_to_html("# 中文测试", "中文标题")

    assert "@font-face" in html
    assert "Nini CJK" in html
    assert font_path.resolve().as_uri() in html


def test_md_to_html_tables():
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    html = _md_to_html(md, "Table Test")
    assert "<table>" in html
    assert "<th>" in html


def test_md_to_html_fenced_code():
    md = "```python\nprint('hello')\n```"
    html = _md_to_html(md, "Code Test")
    assert "<code" in html


# ---------------------------------------------------------------------------
# Tests: Plotly payload normalize
# ---------------------------------------------------------------------------


def test_normalize_plotly_payload_supports_wrapper():
    payload = {
        "figure": {
            "data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}],
            "layout": {"title": {"text": "demo"}},
            "frames": [],
        },
        "config": {"responsive": True},
        "schema_version": "1.0",
    }
    normalized = _normalize_plotly_figure_payload(payload)
    assert isinstance(normalized, dict)
    assert "data" in normalized
    assert "layout" in normalized
    assert "frames" in normalized


def test_normalize_plotly_payload_rejects_invalid():
    assert _normalize_plotly_figure_payload("invalid") is None
    assert _normalize_plotly_figure_payload({"config": {"responsive": True}}) is None


# ---------------------------------------------------------------------------
# Tests: _resolve_images_to_base64
# ---------------------------------------------------------------------------


def test_resolve_images_base64(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    artifacts_dir = sessions_dir / "sess-123" / "workspace" / "artifacts"
    artifacts_dir.mkdir(parents=True)

    # 创建一个 1x1 像素的 PNG
    import base64

    # 最小合法 PNG（1x1 透明像素）
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
        "nGNgYPgPAAEDAQAIicLsAAAABJRU5ErkJggg=="
    )
    (artifacts_dir / "chart.png").write_bytes(png_bytes)

    html = '<img src="/api/artifacts/sess-123/chart.png" alt="chart">'
    with patch("nini.tools.export_report.settings") as mock_settings:
        mock_settings.sessions_dir = sessions_dir
        result = _resolve_images_to_base64(html, "sess-123")

    assert "data:image/png;base64," in result
    assert "/api/artifacts/" not in result


def test_resolve_images_missing_file(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    artifacts_dir = sessions_dir / "sess-123" / "workspace" / "artifacts"
    artifacts_dir.mkdir(parents=True)

    html = '<img src="/api/artifacts/sess-123/missing.png" alt="missing">'
    with patch("nini.tools.export_report.settings") as mock_settings:
        mock_settings.sessions_dir = sessions_dir
        result = _resolve_images_to_base64(html, "sess-123")

    # 文件不存在时保留原路径
    assert "/api/artifacts/sess-123/missing.png" in result


def test_resolve_images_url_encoded_filename(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    artifacts_dir = sessions_dir / "sess-123" / "workspace" / "artifacts"
    artifacts_dir.mkdir(parents=True)

    import base64

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
        "nGNgYPgPAAEDAQAIicLsAAAABJRU5ErkJggg=="
    )
    (artifacts_dir / "中文图表.png").write_bytes(png_bytes)

    html = (
        '<img src="/api/artifacts/sess-123/%E4%B8%AD%E6%96%87%E5%9B%BE%E8%A1%A8.png" alt="chart">'
    )
    with patch("nini.tools.export_report.settings") as mock_settings:
        mock_settings.sessions_dir = sessions_dir
        result = _resolve_images_to_base64(html, "sess-123")

    assert "data:image/png;base64," in result
    assert "/api/artifacts/" not in result


def test_resolve_plotly_json_url_with_query_and_single_quote(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    artifacts_dir = sessions_dir / "sess-123" / "workspace" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "chart.plotly.json").write_text("{}", encoding="utf-8")

    html = "<img src='/api/artifacts/sess-123/chart.plotly.json?raw=1' alt='chart'>"
    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch(
            "nini.tools.export_report._plotly_json_to_png_bytes", return_value=(b"fake-png", None)
        ),
    ):
        mock_settings.sessions_dir = sessions_dir
        result = _resolve_images_to_base64(html, "sess-123")

    assert "data:image/png;base64," in result
    assert "/api/artifacts/" not in result


def test_resolve_plotly_json_collects_failure_reason(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    artifacts_dir = sessions_dir / "sess-123" / "workspace" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "chart.plotly.json").write_text("{}", encoding="utf-8")

    html = '<img src="/api/artifacts/sess-123/chart.plotly.json" alt="chart">'
    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch(
            "nini.tools.export_report._plotly_json_to_png_bytes",
            return_value=(None, "Kaleido requires Google Chrome to be installed."),
        ),
    ):
        mock_settings.sessions_dir = sessions_dir
        resolved_html, stats = _resolve_images_to_base64_with_stats(html, "sess-123")

    assert "/api/artifacts/sess-123/chart.plotly.json" in resolved_html
    assert stats["plotly_total"] == 1
    assert stats["plotly_converted"] == 0
    failed = stats["plotly_failed"]
    assert isinstance(failed, list) and failed
    assert failed[0]["name"] == "chart.plotly.json"
    assert "Chrome" in failed[0]["error"]


# ---------------------------------------------------------------------------
# Tests: ExportReportSkill.execute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_report_without_weasyprint(
    skill: ExportReportSkill,
    mock_session: MagicMock,
    setup_report: Path,
):
    """weasyprint 不可用时，返回友好错误。"""
    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch("nini.tools.export_report.ArtifactStorage") as MockStorage,
        patch.dict("sys.modules", {"weasyprint": None}),
        patch("builtins.__import__", side_effect=_import_without_weasyprint),
    ):
        mock_settings.sessions_dir = setup_report
        storage_inst = MagicMock()
        report_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.md"
        storage_inst.get_path.return_value = report_path
        MockStorage.return_value = storage_inst

        result = await skill.execute(session=mock_session)

    assert not result.success
    assert "weasyprint" in result.message.lower()
    assert "pip install" in result.message
    assert "pip install -e .[pdf]" in result.message
    assert "pip install nini[pdf]" in result.message


def _import_without_weasyprint(name: str, *args: Any, **kwargs: Any) -> Any:
    if name == "weasyprint":
        raise ImportError("No module named 'weasyprint'")
    return original_import(name, *args, **kwargs)


import builtins

original_import = builtins.__import__


@pytest.mark.asyncio
async def test_export_report_with_mock_weasyprint(
    skill: ExportReportSkill,
    mock_session: MagicMock,
    setup_report: Path,
):
    """mock weasyprint，验证完整流程。"""
    fake_pdf = b"%PDF-1.4 fake content"

    mock_weasyprint = MagicMock()
    mock_html_inst = MagicMock()
    mock_html_inst.write_pdf.return_value = fake_pdf
    mock_weasyprint.HTML.return_value = mock_html_inst

    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch("nini.tools.export_report.ArtifactStorage") as MockStorage,
        patch("nini.tools.export_report.WorkspaceManager") as MockWM,
        patch.dict("sys.modules", {"weasyprint": mock_weasyprint}),
    ):
        mock_settings.sessions_dir = setup_report
        storage_inst = MagicMock()
        report_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.md"
        pdf_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.pdf"
        storage_inst.get_path.side_effect = lambda name: (
            report_path if name.endswith(".md") else pdf_path
        )
        MockStorage.return_value = storage_inst

        wm_inst = MagicMock()
        MockWM.return_value = wm_inst

        result = await skill.execute(session=mock_session)

    assert result.success
    assert "test_report.pdf" in result.message
    assert result.artifacts
    assert result.artifacts[0]["format"] == "pdf"
    # PDF 应写入文件
    assert pdf_path.read_bytes() == fake_pdf
    # 应注册到工作区
    wm_inst.add_artifact_record.assert_called_once()


@pytest.mark.asyncio
async def test_export_report_no_latest_report(
    skill: ExportReportSkill,
    mock_session: MagicMock,
):
    """没有 latest_report 且未指定 report_name 时应报错。"""
    result = await skill.execute(session=mock_session)
    assert not result.success
    assert "generate_report" in result.message


@pytest.mark.asyncio
async def test_export_report_uses_latest_report(
    skill: ExportReportSkill,
    mock_session: MagicMock,
    setup_report: Path,
):
    """未指定 report_name 时自动取 latest_report。"""
    fake_pdf = b"%PDF-1.4 fake"
    mock_weasyprint = MagicMock()
    mock_html_inst = MagicMock()
    mock_html_inst.write_pdf.return_value = fake_pdf
    mock_weasyprint.HTML.return_value = mock_html_inst

    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch("nini.tools.export_report.ArtifactStorage") as MockStorage,
        patch("nini.tools.export_report.WorkspaceManager"),
        patch.dict("sys.modules", {"weasyprint": mock_weasyprint}),
    ):
        mock_settings.sessions_dir = setup_report
        storage_inst = MagicMock()
        report_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.md"
        pdf_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.pdf"
        storage_inst.get_path.side_effect = lambda name: (
            report_path if name.endswith(".md") else pdf_path
        )
        MockStorage.return_value = storage_inst

        # latest_report 已由 setup_report fixture 设置
        result = await skill.execute(session=mock_session)

    assert result.success
    assert result.data["source_report"] == "test_report.md"


@pytest.mark.asyncio
async def test_export_report_custom_filename(
    skill: ExportReportSkill,
    mock_session: MagicMock,
    setup_report: Path,
):
    """自定义输出文件名。"""
    fake_pdf = b"%PDF-1.4 custom"
    mock_weasyprint = MagicMock()
    mock_html_inst = MagicMock()
    mock_html_inst.write_pdf.return_value = fake_pdf
    mock_weasyprint.HTML.return_value = mock_html_inst

    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch("nini.tools.export_report.ArtifactStorage") as MockStorage,
        patch("nini.tools.export_report.WorkspaceManager"),
        patch.dict("sys.modules", {"weasyprint": mock_weasyprint}),
    ):
        mock_settings.sessions_dir = setup_report
        storage_inst = MagicMock()
        report_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.md"
        pdf_path = setup_report / mock_session.id / "workspace" / "artifacts" / "my_output.pdf"
        storage_inst.get_path.side_effect = lambda name: (
            report_path if name.endswith(".md") else pdf_path
        )
        MockStorage.return_value = storage_inst

        result = await skill.execute(
            session=mock_session,
            filename="my_output",
        )

    assert result.success
    assert "my_output.pdf" in result.message


@pytest.mark.asyncio
async def test_export_report_fail_fast_when_plotly_chrome_missing(
    skill: ExportReportSkill,
    mock_session: MagicMock,
    setup_report: Path,
):
    """存在 plotly 图表但无法转 PNG（缺少 Chrome）时，应显式失败并给出修复指引。"""
    with (
        patch("nini.tools.export_report.settings") as mock_settings,
        patch("nini.tools.export_report.ArtifactStorage") as MockStorage,
        patch(
            "nini.tools.export_report._resolve_images_to_base64_with_stats",
            return_value=(
                "<html><body>demo</body></html>",
                {
                    "plotly_total": 1,
                    "plotly_converted": 0,
                    "plotly_failed": [
                        {
                            "name": "chart.plotly.json",
                            "error": "Kaleido requires Google Chrome to be installed.",
                        }
                    ],
                },
            ),
        ),
    ):
        mock_settings.sessions_dir = setup_report
        storage_inst = MagicMock()
        report_path = setup_report / mock_session.id / "workspace" / "artifacts" / "test_report.md"
        storage_inst.get_path.return_value = report_path
        MockStorage.return_value = storage_inst

        result = await skill.execute(session=mock_session)

    assert not result.success
    assert ".plotly.json" in result.message
    assert "Chrome" in result.message
    assert "plotly_get_chrome -y" in result.message


# ---------------------------------------------------------------------------
# Tests: Skill metadata
# ---------------------------------------------------------------------------


def test_skill_metadata(skill: ExportReportSkill):
    assert skill.name == "export_report"
    assert skill.category == "export"
    assert not skill.is_idempotent
    assert "PDF" in skill.description or "pdf" in skill.description.lower()

    tool_def = skill.get_tool_definition()
    assert tool_def["function"]["name"] == "export_report"
    params = tool_def["function"]["parameters"]
    assert "report_name" in params["properties"]
    assert "filename" in params["properties"]
