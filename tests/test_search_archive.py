"""归档检索工具测试。

测试 SearchMemoryArchiveTool 在不同场景下的检索行为。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.search_archive import SearchMemoryArchiveTool


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """将数据目录隔离到 tmp_path，避免影响真实数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    settings.ensure_dirs()


def _make_archive_file(session_id: str, messages: list[dict], filename: str = "compressed_20240101_120000.json") -> Path:
    """在测试 archive 目录下创建归档文件。"""
    archive_dir = settings.sessions_dir / session_id / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / filename
    archive_path.write_text(
        json.dumps(messages, ensure_ascii=False),
        encoding="utf-8",
    )
    return archive_path


class TestSearchMemoryArchiveTool:
    """SearchMemoryArchiveTool 功能测试。"""

    async def test_find_keyword_in_archive(self):
        """关键词命中时应返回相关消息片段。"""
        session = Session()
        messages = [
            {"role": "user", "content": "请分析 p 值显著性，p=0.023"},
            {"role": "assistant", "content": "p 值为 0.023，小于 0.05，结果显著"},
        ]
        _make_archive_file(session.id, messages)

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="p 值")

        assert result.success is True
        assert result.data["files_searched"] == 1
        assert len(result.data["results"]) == 2
        # 每条结果应含 snippet
        for r in result.data["results"]:
            assert "p 值" in r["snippet"]

    async def test_no_match_returns_empty(self):
        """无匹配时返回空结果列表。"""
        session = Session()
        messages = [{"role": "user", "content": "分析数据集"}]
        _make_archive_file(session.id, messages)

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="不存在的词")

        assert result.success is True
        assert result.data["results"] == []
        assert result.data["files_searched"] == 1

    async def test_empty_archive_dir(self):
        """archive 目录不存在时返回空结果。"""
        session = Session()  # 没有创建 archive 目录

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="任何词")

        assert result.success is True
        assert result.data["results"] == []
        assert result.data["files_searched"] == 0

    async def test_max_results_respected(self):
        """max_results 参数应限制返回结果数。"""
        session = Session()
        messages = [
            {"role": "user", "content": f"测试消息 {i} 包含关键词"}
            for i in range(10)
        ]
        _make_archive_file(session.id, messages)

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="关键词", max_results=3)

        assert result.success is True
        assert len(result.data["results"]) == 3

    async def test_corrupted_json_skipped(self):
        """损坏的归档文件应被跳过，不影响其他文件检索。"""
        session = Session()

        # 写入一个损坏的 JSON
        archive_dir = settings.sessions_dir / session.id / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "compressed_bad.json").write_text("不合法的 JSON {{{", encoding="utf-8")

        # 写入一个正常的归档
        good_messages = [{"role": "user", "content": "正常的关键词消息"}]
        _make_archive_file(session.id, good_messages, "compressed_good.json")

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="关键词")

        assert result.success is True
        assert len(result.data["results"]) == 1

    async def test_empty_keyword_returns_error(self):
        """空关键词应返回失败结果。"""
        session = Session()
        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="")

        assert result.success is False

    async def test_multifile_search(self):
        """多个归档文件时，结果来自不同文件。"""
        session = Session()
        _make_archive_file(
            session.id,
            [{"role": "user", "content": "第一批关键词数据"}],
            "compressed_001.json",
        )
        _make_archive_file(
            session.id,
            [{"role": "assistant", "content": "第二批关键词分析结果"}],
            "compressed_002.json",
        )

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="关键词", max_results=10)

        assert result.success is True
        assert result.data["files_searched"] == 2
        assert len(result.data["results"]) == 2

    async def test_snippet_length_limited(self):
        """长消息的摘要应被截断。"""
        session = Session()
        long_content = "关键词" + "x" * 500
        messages = [{"role": "user", "content": long_content}]
        _make_archive_file(session.id, messages)

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="关键词")

        assert result.success is True
        snippet = result.data["results"][0]["snippet"]
        assert len(snippet) <= 210  # 200 字 + 省略号
        assert snippet.endswith("…")
