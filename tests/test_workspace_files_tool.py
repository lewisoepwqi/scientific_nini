"""工作区文件浏览工具测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.workspace_files import ListWorkspaceFilesSkill
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    yield


def test_list_workspace_files_returns_download_urls() -> None:
    skill = ListWorkspaceFilesSkill()
    session = Session()
    manager = WorkspaceManager(session.id)

    note_path = manager.save_text_file("notes/research.md", "# note")
    artifact_path = manager.artifacts_dir / "chart.plotly.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("{}", encoding="utf-8")
    manager.add_artifact_record(
        name="chart.plotly.json",
        artifact_type="chart",
        file_path=artifact_path,
        format_hint="json",
    )

    result = asyncio.run(
        skill.execute(
            session=session,
            kinds=["result", "document"],
        )
    ).to_dict()

    assert result["success"] is True, result
    files = result["data"]["files"]
    assert any(file["name"] == "research.md" for file in files)
    chart = next(file for file in files if file["name"] == "chart.plotly.json")
    assert chart["kind"] == "result"
    assert chart["download_url"].endswith(
        "/api/workspace/" + session.id + "/files/artifacts/chart.plotly.json"
    )
    assert "url=" in result["data"]["content"]
    assert note_path.exists()


def test_list_workspace_files_supports_query_and_limit() -> None:
    skill = ListWorkspaceFilesSkill()
    session = Session()
    manager = WorkspaceManager(session.id)
    manager.save_text_file("notes/alpha.md", "A")
    manager.save_text_file("notes/beta.md", "B")

    result = asyncio.run(
        skill.execute(
            session=session,
            query="a",
            kinds=["document"],
            limit=1,
        )
    ).to_dict()

    assert result["success"] is True, result
    assert result["data"]["matched_count"] >= 1
    assert result["data"]["returned_count"] == 1
