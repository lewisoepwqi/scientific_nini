"""混合技能体系（Function + Markdown）测试。"""

from __future__ import annotations

import io
from pathlib import Path
import zipfile

import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.api.websocket import set_skill_registry
from nini.tools.registry import create_default_registry
from tests.client_utils import LocalASGIClient


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
            "brief_description: 用于目录摘要\n"
            "research_domain: general\n"
            "difficulty_level: beginner\n"
            "typical_use_cases:\n"
            "  - 快速试用\n"
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


def test_api_skills_and_tools_split_catalog(
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
    set_skill_registry(create_default_registry())
    with LocalASGIClient(app) as client:
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        markdown_skills = payload["data"]["skills"]
        assert markdown_skills
        assert all(item["type"] == "markdown" for item in markdown_skills)
        assert all("brief_description" in item for item in markdown_skills)
        assert all("research_domain" in item for item in markdown_skills)
        assert all("difficulty_level" in item for item in markdown_skills)

        tools_resp = client.get("/api/tools")
        assert tools_resp.status_code == 200
        tools_payload = tools_resp.json()
        assert tools_payload["success"] is True
        tools = tools_payload["data"]["tools"]
        assert tools
        assert all(item["type"] == "function" for item in tools)
        assert all("brief_description" in item for item in tools)
        assert all("research_domain" in item for item in tools)
        assert all("difficulty_level" in item for item in tools)

        all_resp = client.get("/api/skills", params={"skill_type": "all"})
        all_payload = all_resp.json()
        all_items = all_payload["data"]["skills"]
        assert any(item["type"] == "function" for item in all_items)
        assert any(item["type"] == "markdown" for item in all_items)
        assert all("typical_use_cases" in item for item in all_items)

        semantic_resp = client.get("/api/skills/semantic-catalog", params={"skill_type": "markdown"})
        assert semantic_resp.status_code == 200
        semantic_items = semantic_resp.json()["data"]["skills"]
        assert semantic_items
        assert semantic_items[0]["type"] == "markdown"


def test_api_markdown_skill_progressive_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Markdown Skill API 应支持说明层与运行时资源层。"""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "report_polish"
    _write_skill(
        skill_dir / "SKILL.md",
        name="report_polish",
        description="润色分析报告",
    )
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references" / "style.md").write_text("参考风格\n", encoding="utf-8")
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    app = create_app()
    set_skill_registry(create_default_registry())
    with LocalASGIClient(app) as client:
        instruction_resp = client.get("/api/skills/markdown/report_polish/instruction")
        assert instruction_resp.status_code == 200
        instruction = instruction_resp.json()["data"]["instruction"]
        assert "示例步骤" in instruction
        assert "name:" not in instruction

        resources_resp = client.get("/api/skills/markdown/report_polish/runtime-resources")
        assert resources_resp.status_code == 200
        resources = resources_resp.json()["data"]["resources"]
        assert any(item["path"] == "references/style.md" for item in resources)


def test_api_markdown_skill_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    app = create_app()
    set_skill_registry(create_default_registry())
    upload_text = (
        "---\n"
        "name: custom_upload_skill\n"
        "description: 上传后的技能\n"
        "category: workflow\n"
        "---\n\n"
        "# custom_upload_skill\n\n"
        "用于上传测试。\n"
    )
    with LocalASGIClient(app) as client:
        resp = client.post(
            "/api/skills/markdown/upload",
            files={"file": ("custom_upload_skill.md", upload_text, "text/markdown")},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        skill = payload["data"]["skill"]
        assert skill["name"] == "custom_upload_skill"
        assert skill["type"] == "markdown"

    target = skills_dir / "custom_upload_skill" / "SKILL.md"
    assert target.exists()
    assert "上传后的技能" in target.read_text(encoding="utf-8")


def test_api_markdown_skill_upload_new_route_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """技能上传新路由 `/api/skills/upload` 应与旧别名保持一致。"""
    skills_dir = tmp_path / "skills"
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    app = create_app()
    set_skill_registry(create_default_registry())
    upload_text = (
        "---\n"
        "name: custom_upload_skill_v2\n"
        "description: 新路由上传后的技能\n"
        "category: workflow\n"
        "---\n\n"
        "# custom_upload_skill_v2\n\n"
        "用于上传测试。\n"
    )
    with LocalASGIClient(app) as client:
        resp = client.post(
            "/api/skills/upload",
            files={"file": ("custom_upload_skill_v2.md", upload_text, "text/markdown")},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        skill = payload["data"]["skill"]
        assert skill["name"] == "custom_upload_skill_v2"
        assert skill["type"] == "markdown"

    target = skills_dir / "custom_upload_skill_v2" / "SKILL.md"
    assert target.exists()
    assert "新路由上传后的技能" in target.read_text(encoding="utf-8")


def test_api_markdown_skill_manage_flow(
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
    set_skill_registry(create_default_registry())
    with LocalASGIClient(app) as client:
        disable_resp = client.patch(
            "/api/skills/markdown/report_polish/enabled",
            json={"enabled": False},
        )
        assert disable_resp.status_code == 200
        disable_payload = disable_resp.json()
        assert disable_payload["success"] is True
        assert disable_payload["data"]["skill"]["enabled"] is False

        detail_resp = client.get("/api/skills/markdown/report_polish")
        assert detail_resp.status_code == 200
        detail_payload = detail_resp.json()
        assert detail_payload["data"]["skill"]["content"]

        update_resp = client.request(
            "PUT",
            "/api/skills/markdown/report_polish",
            json={
                "description": "润色并补充参考文献",
                "category": "report",
                "content": "# report_polish\n\n更新后的内容。",
            },
        )
        assert update_resp.status_code == 200
        update_payload = update_resp.json()
        assert update_payload["success"] is True
        assert "更新后的内容" in update_payload["data"]["skill"]["content"]

        delete_resp = client.delete("/api/skills/markdown/report_polish")
        assert delete_resp.status_code == 200
        delete_payload = delete_resp.json()
        assert delete_payload["success"] is True
        assert delete_payload["data"]["deleted"] == "report_polish"

        list_resp = client.get("/api/skills", params={"skill_type": "markdown"})
        list_payload = list_resp.json()
        markdown_names = {item["name"] for item in list_payload["data"]["skills"]}
        assert "report_polish" not in markdown_names


def test_registry_markdown_skill_duplicate_prefers_higher_priority_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_dir = tmp_path / "primary"
    secondary_dir = tmp_path / "secondary"

    _write_skill(
        primary_dir / "dup_skill" / "SKILL.md",
        name="dup_skill",
        description="高优先级目录",
    )
    _write_skill(
        secondary_dir / "dup_skill" / "SKILL.md",
        name="dup_skill",
        description="低优先级目录",
    )

    monkeypatch.setattr(settings, "skills_dir_path", primary_dir)
    monkeypatch.setattr(settings, "skills_extra_dirs", str(secondary_dir))
    monkeypatch.setattr(settings, "skills_auto_discover_compat_dirs", False)

    registry = create_default_registry()
    markdown = registry.get_markdown_skill("dup_skill")
    assert markdown is not None
    assert markdown["description"] == "高优先级目录"


def test_api_markdown_skill_files_management(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir / "skill_with_files" / "SKILL.md",
        name="skill_with_files",
        description="带附属文件的技能",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    app = create_app()
    set_skill_registry(create_default_registry())
    with LocalASGIClient(app) as client:
        list_resp = client.get("/api/skills/markdown/skill_with_files/files")
        assert list_resp.status_code == 200
        list_payload = list_resp.json()
        paths = {item["path"] for item in list_payload["data"]["files"]}
        assert "SKILL.md" in paths

        create_dir_resp = client.post(
            "/api/skills/markdown/skill_with_files/directories",
            json={"path": "scripts"},
        )
        assert create_dir_resp.status_code == 200

        upload_resp = client.post(
            "/api/skills/markdown/skill_with_files/files/upload",
            data={"dir_path": "scripts"},
            files={"file": ("helper.py", "print('ok')\n", "text/plain")},
        )
        assert upload_resp.status_code == 200

        save_resp = client.request(
            "PUT",
            "/api/skills/markdown/skill_with_files/files/content",
            json={"path": "references/guide.md", "content": "# 引用文档\n"},
        )
        assert save_resp.status_code == 200

        read_resp = client.get(
            "/api/skills/markdown/skill_with_files/files/content",
            params={"path": "references/guide.md"},
        )
        assert read_resp.status_code == 200
        read_payload = read_resp.json()
        assert read_payload["data"]["is_text"] is True
        assert "# 引用文档" in read_payload["data"]["content"]

        bundle_resp = client.get("/api/skills/markdown/skill_with_files/bundle")
        assert bundle_resp.status_code == 200
        assert bundle_resp.headers.get("content-type", "").startswith("application/zip")
        with zipfile.ZipFile(io.BytesIO(bundle_resp.content), "r") as zf:
            names = set(zf.namelist())
            assert "skill_with_files/SKILL.md" in names
            assert "skill_with_files/scripts/helper.py" in names
            assert "skill_with_files/references/guide.md" in names

        delete_path_resp = client.request(
            "DELETE",
            "/api/skills/markdown/skill_with_files/paths",
            json={"path": "references/guide.md"},
        )
        assert delete_path_resp.status_code == 200

        list_after_delete = client.get("/api/skills/markdown/skill_with_files/files").json()
        paths_after_delete = {item["path"] for item in list_after_delete["data"]["files"]}
        assert "references/guide.md" not in paths_after_delete


def test_api_markdown_skill_dir_legacy_alias_still_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧别名 `/dirs` 仍应兼容，避免历史调用断裂。"""
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir / "legacy_dir_skill" / "SKILL.md",
        name="legacy_dir_skill",
        description="目录兼容测试技能",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    app = create_app()
    set_skill_registry(create_default_registry())
    with LocalASGIClient(app) as client:
        resp = client.post(
            "/api/skills/markdown/legacy_dir_skill/dirs",
            json={"path": "references"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["data"]["path"] == "references"

    assert (skills_dir / "legacy_dir_skill" / "references").is_dir()
