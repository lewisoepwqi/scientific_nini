"""混合技能体系（Function + Markdown）测试。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.skills.registry import create_default_registry


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


def _write_skill(path: Path, *, name: str, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n\n"
            "## 步骤\n"
            "1. 示例步骤\n"
        ),
        encoding="utf-8",
    )


def test_registry_scans_markdown_skills_and_writes_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir / "literature_search" / "SKILL.md",
        name="literature_search",
        description="检索文献摘要",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    registry = create_default_registry()
    catalog = registry.list_skill_catalog()
    markdown_items = [item for item in catalog if item.get("type") == "markdown"]

    assert markdown_items, "应扫描到 Markdown 技能"
    assert markdown_items[0]["name"] == "literature_search"

    snapshot_text = settings.skills_snapshot_path.read_text(encoding="utf-8")
    assert "literature_search" in snapshot_text
    assert "type: markdown" in snapshot_text


def test_markdown_skill_name_conflict_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir / "t_test" / "SKILL.md",
        name="t_test",
        description="与内置函数技能同名",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    registry = create_default_registry()
    markdown = [item for item in registry.list_markdown_skills() if item["name"] == "t_test"]
    assert markdown, "应存在同名 Markdown 技能"
    assert markdown[0]["enabled"] is False
    assert markdown[0]["metadata"]["conflict_with"] == "function"


def test_api_skills_returns_hybrid_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir / "report_polish" / "SKILL.md",
        name="report_polish",
        description="润色分析报告",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        skills = payload["data"]["skills"]
        assert any(item["type"] == "function" for item in skills)
        assert any(item["type"] == "markdown" for item in skills)

        markdown_resp = client.get("/api/skills", params={"skill_type": "markdown"})
        markdown_payload = markdown_resp.json()
        markdown_skills = markdown_payload["data"]["skills"]
        assert markdown_skills
        assert all(item["type"] == "markdown" for item in markdown_skills)
