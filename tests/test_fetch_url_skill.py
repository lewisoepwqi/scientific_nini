"""fetch_url 技能测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.fetch_url import FetchURLSkill


@pytest.fixture(autouse=True)
def isolate_data_and_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "skills")
    monkeypatch.setattr(settings, "skills_extra_dirs", "")
    monkeypatch.setattr(settings, "skills_auto_discover_compat_dirs", False)
    yield


def test_fetch_url_allows_skill_file_uri() -> None:
    skill_file = settings.skills_dir / "demo_skill" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("# demo\n\n这是测试技能。", encoding="utf-8")

    skill = FetchURLSkill()
    session = Session()
    result = asyncio.run(skill.execute(session=session, url=skill_file.as_uri()))
    payload = result.to_dict()

    assert payload["success"] is True, payload
    assert "这是测试技能" in payload["data"]["content"]


def test_fetch_url_blocks_file_outside_skills_root() -> None:
    outside_file = settings.data_dir / "outside.md"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("outside", encoding="utf-8")

    skill = FetchURLSkill()
    session = Session()
    result = asyncio.run(skill.execute(session=session, url=outside_file.as_uri()))
    payload = result.to_dict()

    assert payload["success"] is False, payload
    assert "技能目录之外" in payload["message"]


def test_fetch_url_blocks_unsupported_local_file_type() -> None:
    binary_file = settings.skills_dir / "demo_skill" / "logo.png"
    binary_file.parent.mkdir(parents=True, exist_ok=True)
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    skill = FetchURLSkill()
    session = Session()
    result = asyncio.run(skill.execute(session=session, url=binary_file.as_uri()))
    payload = result.to_dict()

    assert payload["success"] is False, payload
    assert "不支持读取该文件类型" in payload["message"]
