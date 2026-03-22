"""归档检索工具测试。

测试 SearchMemoryArchiveTool 在不同场景下的检索行为，包含：
- 全量扫描（无索引）
- 索引命中路径
- 索引+未索引混合路径
- 索引损坏 fallback
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.memory.compression import _append_to_search_index
from nini.tools.search_archive import SearchMemoryArchiveTool


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """将数据目录隔离到 tmp_path，避免影响真实数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    settings.ensure_dirs()


def _make_archive_file(
    session_id: str, messages: list[dict], filename: str = "compressed_20240101_120000.json"
) -> Path:
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
        messages = [{"role": "user", "content": f"测试消息 {i} 包含关键词"} for i in range(10)]
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


class TestSearchIndexIntegration:
    """测试增量索引写入与基于索引的检索。"""

    def _write_index(self, session_id: str, filename: str, messages: list[dict]) -> Path:
        """辅助：通过 _append_to_search_index 写入索引，返回 session.db 路径。"""
        archive_dir = settings.sessions_dir / session_id / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        _append_to_search_index(archive_dir, filename, messages)
        # SQLite 路径：session.db 在 session_dir 下
        return settings.sessions_dir / session_id / settings.session_db_filename

    async def test_index_built_on_archive(self):
        """_append_to_search_index 应正确写入 SQLite archived_messages 表。"""
        import sqlite3

        session = Session()
        messages = [
            {"role": "user", "content": "索引测试内容"},
            {"role": "assistant", "content": "索引回复"},
        ]
        _make_archive_file(session.id, messages, "compressed_idx.json")
        db_path = self._write_index(session.id, "compressed_idx.json", messages)

        assert db_path.exists(), "session.db 应在 _append_to_search_index 后创建"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT archive_file, role, content FROM archived_messages ORDER BY id ASC"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == "compressed_idx.json"
        assert rows[0][1] == "user"
        assert "索引测试内容" in rows[0][2]

    async def test_index_search_finds_match(self):
        """索引存在时应通过索引找到匹配记录。"""
        session = Session()
        messages = [{"role": "user", "content": "p值显著性分析结果"}]
        _make_archive_file(session.id, messages, "compressed_p.json")
        self._write_index(session.id, "compressed_p.json", messages)

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="p值")

        assert result.success is True
        assert len(result.data["results"]) == 1
        assert result.data["used_index"] is True
        assert result.data["indexed_files"] == 1
        # 索引已覆盖该文件，files_searched（全量扫描数）应为 0
        assert result.data["files_searched"] == 0

    async def test_unindexed_file_also_searched(self):
        """未建立索引的旧归档文件仍应被全量扫描。"""
        session = Session()
        # 文件1：有索引
        indexed_msgs = [{"role": "user", "content": "索引中的关键词"}]
        _make_archive_file(session.id, indexed_msgs, "compressed_new.json")
        self._write_index(session.id, "compressed_new.json", indexed_msgs)

        # 文件2：无索引（旧文件，用 _make_archive_file 直接写）
        unindexed_msgs = [{"role": "assistant", "content": "未索引的关键词内容"}]
        _make_archive_file(session.id, unindexed_msgs, "compressed_old.json")

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="关键词", max_results=10)

        assert result.success is True
        assert len(result.data["results"]) == 2
        assert result.data["indexed_files"] == 1
        assert result.data["files_searched"] == 1  # 1 个未索引文件被全量扫描

    async def test_corrupted_index_falls_back_to_full_scan(self):
        """损坏的索引文件应 fallback 到全量扫描，不影响结果。"""
        session = Session()
        messages = [{"role": "user", "content": "全量扫描关键词"}]
        _make_archive_file(session.id, messages, "compressed_fb.json")

        # 写入损坏的索引
        archive_dir = settings.sessions_dir / session.id / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "search_index.jsonl").write_text("损坏的 JSON {{{", encoding="utf-8")

        tool = SearchMemoryArchiveTool()
        result = await tool.execute(session, keyword="关键词")

        assert result.success is True
        assert len(result.data["results"]) == 1
        # fallback 后走全量扫描
        assert result.data["files_searched"] >= 1

    async def test_index_and_full_scan_same_results(self):
        """索引结果与全量扫描结果应一致（相同消息）。"""
        session1 = Session()
        session2 = Session()
        messages = [
            {"role": "user", "content": "一致性测试关键词 A"},
            {"role": "assistant", "content": "一致性测试关键词 B"},
        ]

        # session1：有索引
        _make_archive_file(session1.id, messages, "compressed_x.json")
        self._write_index(session1.id, "compressed_x.json", messages)

        # session2：无索引（全量扫描）
        _make_archive_file(session2.id, messages, "compressed_x.json")

        tool = SearchMemoryArchiveTool()
        r1 = await tool.execute(session1, keyword="关键词", max_results=10)
        r2 = await tool.execute(session2, keyword="关键词", max_results=10)

        assert r1.success and r2.success
        assert len(r1.data["results"]) == len(r2.data["results"])
        snippets1 = {r["snippet"] for r in r1.data["results"]}
        snippets2 = {r["snippet"] for r in r2.data["results"]}
        assert snippets1 == snippets2
