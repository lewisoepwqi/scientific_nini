"""CompressionSegment 及相关行为测试。

覆盖范围：
5.1 CompressionSegment 序列化往返
5.2 set_compressed_context 追加新段
5.3 轻量路径超限直接丢弃
5.4 try_merge_oldest_segments LLM 成功
5.5 try_merge_oldest_segments LLM 失败
5.6 向后兼容旧格式加载
5.7 save_session_compression + create_session 往返
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.memory.compression import CompressionSegment, try_merge_oldest_segments


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离数据目录，避免影响真实数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()


# ---- 5.1 序列化往返 ----


class TestCompressionSegmentSerialization:
    """验证 CompressionSegment 序列化/反序列化正确，无 archive_path 字段。"""

    def test_to_dict_contains_expected_keys(self):
        seg = CompressionSegment(
            summary="测试摘要",
            archived_count=5,
            created_at="2026-01-01T00:00:00+00:00",
            depth=0,
        )
        d = seg.to_dict()
        assert set(d.keys()) == {"summary", "archived_count", "created_at", "depth"}
        assert "archive_path" not in d

    def test_roundtrip_depth0(self):
        seg = CompressionSegment(
            summary="摘要内容",
            archived_count=3,
            created_at="2026-01-01T00:00:00+00:00",
            depth=0,
        )
        restored = CompressionSegment.from_dict(seg.to_dict())
        assert restored.summary == seg.summary
        assert restored.archived_count == seg.archived_count
        assert restored.created_at == seg.created_at
        assert restored.depth == seg.depth

    def test_roundtrip_depth1(self):
        seg = CompressionSegment(
            summary="合并摘要",
            archived_count=10,
            created_at="2026-03-01T12:00:00+00:00",
            depth=1,
        )
        restored = CompressionSegment.from_dict(seg.to_dict())
        assert restored.depth == 1

    def test_to_dict_is_json_serializable(self):
        seg = CompressionSegment(summary="内容", archived_count=0, created_at="2026-01-01", depth=0)
        json.dumps(seg.to_dict())  # 不应抛出异常

    def test_from_dict_defaults_missing_fields(self):
        """from_dict 对缺失字段使用默认值。"""
        seg = CompressionSegment.from_dict({"summary": "只有摘要"})
        assert seg.archived_count == 0
        assert seg.depth == 0
        assert seg.created_at == ""


# ---- 5.2 set_compressed_context 追加新段 ----


class TestSetCompressedContextAppend:
    """验证 set_compressed_context 将新摘要封装为 depth=0 段追加到 compression_segments。"""

    def test_append_increases_segment_count(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 10)
        session = Session()
        assert len(session.compression_segments) == 0
        session.set_compressed_context("第一轮摘要")
        assert len(session.compression_segments) == 1

    def test_new_segment_is_depth_zero(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 10)
        session = Session()
        session.set_compressed_context("摘要内容")
        assert session.compression_segments[0]["depth"] == 0

    def test_compressed_context_matches_segments_join(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 10)
        session = Session()
        session.set_compressed_context("第一段")
        session.set_compressed_context("第二段")
        expected = "第一段\n\n---\n\n第二段"
        assert session.compressed_context == expected

    def test_empty_summary_ignored(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 10)
        session = Session()
        session.set_compressed_context("")
        session.set_compressed_context("   ")
        assert len(session.compression_segments) == 0
        assert session.compressed_context == ""

    def test_compressed_rounds_incremented(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 10)
        session = Session()
        session.set_compressed_context("摘要")
        assert session.compressed_rounds == 1


# ---- 5.3 轻量路径超限直接丢弃 ----


class TestLightweightPathOverflow:
    """验证 len > max_segments 时轻量路径直接 pop 最旧段，不调用 LLM。"""

    def test_overflow_pops_oldest(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 2)
        session = Session()
        session.set_compressed_context("段A")
        session.set_compressed_context("段B")
        assert len(session.compression_segments) == 2

        # 第三次调用触发超限 pop
        session.set_compressed_context("段C")
        assert len(session.compression_segments) == 2

    def test_oldest_segment_discarded(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 2)
        session = Session()
        session.set_compressed_context("段A")
        session.set_compressed_context("段B")
        session.set_compressed_context("段C")

        summaries = [s["summary"] for s in session.compression_segments]
        assert "段A" not in summaries
        assert "段B" in summaries
        assert "段C" in summaries

    def test_compressed_context_rebuilt_from_remaining(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 2)
        session = Session()
        session.set_compressed_context("段A")
        session.set_compressed_context("段B")
        session.set_compressed_context("段C")

        assert session.compressed_context == "段B\n\n---\n\n段C"


# ---- 5.4 try_merge_oldest_segments LLM 成功 ----


class TestTryMergeOldestSegmentsSuccess:
    """验证 LLM 合并成功时最旧两段被替换为 depth=1 段。"""

    async def test_llm_success_merges_two_into_one(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 2)
        session = Session()
        # 手动构造超限状态：3 段（超过 max=2）
        session.compression_segments = [
            CompressionSegment("段A", archived_count=2, created_at="2026-01-01", depth=0).to_dict(),
            CompressionSegment("段B", archived_count=3, created_at="2026-01-02", depth=0).to_dict(),
            CompressionSegment("段C", archived_count=1, created_at="2026-01-03", depth=0).to_dict(),
        ]

        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
            return_value="合并摘要AB",
        ):
            await try_merge_oldest_segments(session, max_segments=2)

        assert len(session.compression_segments) == 2
        merged = session.compression_segments[0]
        assert merged["depth"] == 1
        assert merged["summary"] == "合并摘要AB"
        assert merged["archived_count"] == 5  # 2 + 3
        # 第三段保留
        assert session.compression_segments[1]["summary"] == "段C"

    async def test_compressed_context_rebuilt_after_merge(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "compressed_context_max_segments", 2)
        session = Session()
        session.compression_segments = [
            CompressionSegment("段A", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段B", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段C", archived_count=1, created_at="", depth=0).to_dict(),
        ]

        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
            return_value="合并AB",
        ):
            await try_merge_oldest_segments(session, max_segments=2)

        assert session.compressed_context == "合并AB\n\n---\n\n段C"


# ---- 5.5 try_merge_oldest_segments LLM 失败 ----


class TestTryMergeOldestSegmentsFailure:
    """验证 LLM 失败时不抛出异常，compressed_context 由剩余 segments join 覆写。"""

    async def test_llm_failure_no_exception(self, monkeypatch: pytest.MonkeyPatch):
        session = Session()
        session.compression_segments = [
            CompressionSegment("段A", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段B", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段C", archived_count=1, created_at="", depth=0).to_dict(),
        ]
        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # 不应抛出任何异常
            await try_merge_oldest_segments(session, max_segments=2)

    async def test_llm_failure_segments_unchanged(self, monkeypatch: pytest.MonkeyPatch):
        session = Session()
        session.compression_segments = [
            CompressionSegment("段A", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段B", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段C", archived_count=1, created_at="", depth=0).to_dict(),
        ]
        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await try_merge_oldest_segments(session, max_segments=2)

        # LLM 失败时 segments 不变
        assert len(session.compression_segments) == 3

    async def test_compressed_context_rebuilt_on_failure(self):
        """LLM 失败时 compressed_context 从剩余 segments join 覆写。"""
        session = Session()
        session.compression_segments = [
            CompressionSegment("段A", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段B", archived_count=1, created_at="", depth=0).to_dict(),
            CompressionSegment("段C", archived_count=1, created_at="", depth=0).to_dict(),
        ]
        session.compressed_context = "旧值"

        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await try_merge_oldest_segments(session, max_segments=2)

        assert session.compressed_context == "段A\n\n---\n\n段B\n\n---\n\n段C"

    async def test_no_action_when_below_limit(self):
        """段数未超限时不调用 LLM，不修改 segments。"""
        session = Session()
        session.compression_segments = [
            CompressionSegment("段A", archived_count=1, created_at="", depth=0).to_dict(),
        ]
        session.compressed_context = "段A"

        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
        ) as mock_llm:
            await try_merge_oldest_segments(session, max_segments=2)
            mock_llm.assert_not_called()

        assert len(session.compression_segments) == 1
        assert session.compressed_context == "段A"


# ---- 5.6 向后兼容旧格式加载 ----


class TestBackwardCompatLoad:
    """验证旧格式 meta.json（无 compression_segments）加载后正确处理。"""

    def test_old_format_with_compressed_context_creates_one_segment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "test_compat_session"
        session_dir = settings.sessions_dir / sid
        session_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "title": "旧会话",
            "compressed_context": "这是旧格式的压缩上下文",
            "compressed_rounds": 2,
        }
        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        session = session_manager.create_session(sid, load_persisted_messages=True)
        assert len(session.compression_segments) == 1
        seg = session.compression_segments[0]
        assert seg["depth"] == 0
        assert seg["summary"] == "这是旧格式的压缩上下文"
        assert seg["archived_count"] == 0

    def test_old_format_without_compressed_context_creates_empty_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "test_compat_empty_session"
        session_dir = settings.sessions_dir / sid
        session_dir.mkdir(parents=True, exist_ok=True)

        meta = {"title": "空压缩旧会话", "compressed_context": "", "compressed_rounds": 0}
        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        session = session_manager.create_session(sid, load_persisted_messages=True)
        assert session.compression_segments == []

    def test_no_exception_when_loading_old_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "test_compat_no_exc"
        session_dir = settings.sessions_dir / sid
        session_dir.mkdir(parents=True, exist_ok=True)

        meta = {"title": "旧格式", "compressed_context": "内容", "compressed_rounds": 1}
        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        # 不应抛出任何异常
        session = session_manager.create_session(sid, load_persisted_messages=True)
        assert session is not None


# ---- 5.7 save + create 往返 ----


class TestPersistenceRoundtrip:
    """验证 save_session_compression + create_session 往返 compression_segments 内容一致。"""

    def test_roundtrip_preserves_segments(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "roundtrip_test"
        session_dir = settings.sessions_dir / sid
        session_dir.mkdir(parents=True, exist_ok=True)

        original_segs = [
            CompressionSegment(
                "第一段摘要", archived_count=5, created_at="2026-01-01", depth=0
            ).to_dict(),
            CompressionSegment(
                "第二段摘要", archived_count=3, created_at="2026-01-02", depth=1
            ).to_dict(),
        ]

        # 持久化
        session_manager.save_session_compression(
            sid,
            compressed_context="第一段摘要\n\n---\n\n第二段摘要",
            compressed_rounds=2,
            last_compressed_at="2026-01-02T00:00:00+00:00",
            compression_segments=original_segs,
        )

        # 重新加载
        loaded = session_manager.create_session(sid, load_persisted_messages=True)
        assert loaded.compression_segments == original_segs

    def test_roundtrip_compression_segments_field_in_meta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """meta.json 中实际写入了 compression_segments 字段。"""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "roundtrip_meta_check"
        session_dir = settings.sessions_dir / sid
        session_dir.mkdir(parents=True, exist_ok=True)

        segs = [
            CompressionSegment(
                "摘要X", archived_count=1, created_at="2026-01-01", depth=0
            ).to_dict()
        ]
        session_manager.save_session_compression(
            sid,
            compressed_context="摘要X",
            compressed_rounds=1,
            last_compressed_at=None,
            compression_segments=segs,
        )

        meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
        assert "compression_segments" in meta
        assert meta["compression_segments"] == segs

    def test_none_segments_not_written_to_meta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """compression_segments=None 时不写入 meta.json（向后兼容已有调用）。"""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "no_segs_test"
        session_dir = settings.sessions_dir / sid
        session_dir.mkdir(parents=True, exist_ok=True)

        session_manager.save_session_compression(
            sid,
            compressed_context="摘要",
            compressed_rounds=1,
            last_compressed_at=None,
            compression_segments=None,
        )

        meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
        assert "compression_segments" not in meta

    def test_pending_actions_roundtrip_in_meta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        settings.ensure_dirs()

        sid = "pending_actions_roundtrip"
        session = session_manager.create_session(sid)
        session.upsert_pending_action(
            action_type="script_not_run",
            key="script_demo",
            status="pending",
            summary="脚本 script_demo 已创建但尚未执行。",
            source_tool="code_session",
        )

        loaded = session_manager.create_session(sid, load_persisted_messages=True)
        pending = loaded.list_pending_actions(action_type="script_not_run")
        assert len(pending) == 1
        assert pending[0]["key"] == "script_demo"
