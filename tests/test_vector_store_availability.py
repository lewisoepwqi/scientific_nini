"""向量知识库 availability 字段测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from nini.knowledge.vector_store import VectorKnowledgeStore


def test_availability_not_ready_when_llama_index_unavailable(tmp_path: Path) -> None:
    """llama-index 未安装时 availability 应为 not_ready。"""
    store = VectorKnowledgeStore(
        knowledge_dir=tmp_path / "knowledge",
        storage_dir=tmp_path / "storage",
    )
    assert store._index is None

    _, _, availability = store.query("test query")
    assert availability == "not_ready"


def test_availability_empty_when_no_knowledge_files(tmp_path: Path) -> None:
    """知识目录为空时 availability 应为 empty。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    store = VectorKnowledgeStore(
        knowledge_dir=knowledge_dir,
        storage_dir=tmp_path / "storage",
    )
    store._index = "fake_index"  # type: ignore[assignment]

    with patch("nini.knowledge.vector_store._check_llama_index", return_value=True):
        _, _, availability = store.query("")
        assert availability == "empty"


def test_availability_available_with_knowledge_files(tmp_path: Path) -> None:
    """知识目录有文件且索引已加载时 availability 应为 available。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "test.md").write_text("# 测试知识", encoding="utf-8")

    store = VectorKnowledgeStore(
        knowledge_dir=knowledge_dir,
        storage_dir=tmp_path / "storage",
    )
    store._index = "fake_index"  # type: ignore[assignment]

    with patch("nini.knowledge.vector_store._check_llama_index", return_value=True):
        _, _, availability = store.query("")
        assert availability == "available"
