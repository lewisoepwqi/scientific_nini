"""旧数据迁移测试。"""
import json
from pathlib import Path

import pytest

from nini.memory.memory_store import MemoryStore

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test.db")


def test_migrate_from_jsonl_imports_entries(store: MemoryStore):
    """JSONL 迁移应写入正确条数。"""
    count = store.migrate_from_jsonl(FIXTURES / "sample_entries.jsonl")
    assert count == 2


def test_migrate_from_jsonl_is_idempotent(store: MemoryStore):
    """重复迁移不应写入重复条目。"""
    jsonl = FIXTURES / "sample_entries.jsonl"
    count1 = store.migrate_from_jsonl(jsonl)
    count2 = store.migrate_from_jsonl(jsonl)
    assert count1 == 2
    assert count2 == 0


def test_migrate_from_jsonl_maps_source_dataset(store: MemoryStore):
    """source_dataset 应映射到 sci_metadata.dataset_name。"""
    store.migrate_from_jsonl(FIXTURES / "sample_entries.jsonl")
    results = store.filter_by_sci(dataset_name="survey_2024.csv")
    assert len(results) == 2


def test_migrate_from_jsonl_missing_file_returns_zero(store: MemoryStore, tmp_path: Path):
    """文件不存在时静默返回 0。"""
    count = store.migrate_from_jsonl(tmp_path / "nonexistent.jsonl")
    assert count == 0


def test_migrate_profile_json(store: MemoryStore, tmp_path: Path):
    """JSON profile 迁移。"""
    profile_data = {"user_id": "default", "domain": "psychology", "significance_level": 0.05}
    json_path = tmp_path / "default.json"
    json_path.write_text(json.dumps(profile_data), encoding="utf-8")

    store.migrate_profile_json(json_path)

    profile = store.get_profile("default")
    assert profile is not None
    assert profile["data_json"]["domain"] == "psychology"


def test_migrate_profile_json_with_narrative(store: MemoryStore, tmp_path: Path):
    """JSON profile + Markdown narrative 迁移。"""
    json_path = tmp_path / "default.json"
    json_path.write_text(json.dumps({"user_id": "default"}), encoding="utf-8")
    md_path = tmp_path / "default_profile.md"
    md_path.write_text("## 研究偏好摘要\n- α=0.05", encoding="utf-8")

    store.migrate_profile_json(json_path, narrative_path=md_path)

    profile = store.get_profile("default")
    assert "α=0.05" in profile["narrative_md"]


def test_migrate_profile_json_does_not_overwrite_existing(store: MemoryStore, tmp_path: Path):
    """已存在 profile 时，migrate 不覆盖（保护新数据）。"""
    store.upsert_profile("default", data_json={"domain": "new"}, narrative_md="")
    json_path = tmp_path / "default.json"
    json_path.write_text(
        json.dumps({"user_id": "default", "domain": "old"}), encoding="utf-8"
    )

    store.migrate_profile_json(json_path)

    profile = store.get_profile("default")
    assert profile["data_json"]["domain"] == "new"
