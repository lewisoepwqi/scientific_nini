"""Memory 优化功能测试。

测试大型数据引用化、DataFrame 预览限制和自动压缩机制。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.memory.conversation import ConversationMemory
from nini.skills.data_ops import PreviewDataSkill


class TestDataframePreviewLimit:
    """测试 DataFrame 预览行数限制。"""

    @pytest.mark.asyncio
    async def test_small_dataset_full_preview(self):
        """小数据集应该完整预览。"""
        session = Session()
        df = pd.DataFrame({"A": range(50), "B": range(50)})
        session.datasets["small"] = df

        skill = PreviewDataSkill()
        result = await skill.execute(session, dataset_name="small", n_rows=100)

        assert result.success
        assert result.data["total_rows"] == 50
        assert result.data["preview_rows"] == 50
        assert result.data["preview_strategy"] == "full"

    @pytest.mark.asyncio
    async def test_large_dataset_head_tail_preview(self):
        """大数据集应该使用 head+tail 策略。"""
        session = Session()
        df = pd.DataFrame({"A": range(1000), "B": range(1000)})
        session.datasets["large"] = df

        skill = PreviewDataSkill()
        result = await skill.execute(session, dataset_name="large", n_rows=100)

        assert result.success
        assert result.data["total_rows"] == 1000
        assert result.data["preview_rows"] == 100  # 前 50 + 后 50
        assert result.data["preview_strategy"] == "head_tail"

        # 验证数据包含头尾
        data = result.data["data"]
        assert len(data) == 100
        assert data[0]["A"] == 0  # 第一行
        assert data[-1]["A"] == 999  # 最后一行

    @pytest.mark.asyncio
    async def test_preview_respects_max_limit(self):
        """预览行数应该受 MAX_PREVIEW_ROWS 限制。"""
        session = Session()
        df = pd.DataFrame({"A": range(500), "B": range(500)})
        session.datasets["test"] = df

        skill = PreviewDataSkill()
        # 请求 200 行，但应该被限制为 MAX_PREVIEW_ROWS (100)
        result = await skill.execute(session, dataset_name="test", n_rows=200)

        assert result.success
        assert result.data["preview_rows"] == 100


class TestLargePayloadReference:
    """测试大型数据引用化。"""

    def test_small_data_not_referenced(self, tmp_path):
        """小数据不应该被引用化。"""
        # 使用临时目录
        session_id = "test_small"
        settings.data_dir = tmp_path

        memory = ConversationMemory(session_id)
        entry = {
            "role": "assistant",
            "content": "小数据",
            "chart_data": {"x": [1, 2, 3], "y": [4, 5, 6]},
        }

        memory.append(entry)

        # 读取并验证
        loaded = memory.load_all()
        assert len(loaded) == 1
        assert "chart_data" in loaded[0]
        # 应该直接包含数据，而不是引用
        assert "_ref" not in str(loaded[0]["chart_data"])

    def test_large_data_referenced(self, tmp_path):
        """大数据应该被引用化。"""
        # 使用临时目录
        session_id = "test_large"
        settings.data_dir = tmp_path

        memory = ConversationMemory(session_id)

        # 创建一个大型图表数据（超过 10KB）
        large_chart = {
            "data": [{"x": list(range(1000)), "y": list(range(1000))} for _ in range(10)],
            "layout": {"title": "Big Chart" * 100},
        }

        entry = {
            "role": "assistant",
            "content": "大数据",
            "chart_data": large_chart,
        }

        memory.append(entry)

        # 读取并验证
        loaded = memory.load_all(resolve_refs=False)
        assert len(loaded) == 1

        # chart_data 应该被替换为引用
        chart_field = loaded[0]["chart_data"]
        assert isinstance(chart_field, dict)
        assert "_ref" in chart_field
        assert "memory-payloads/" in chart_field["_ref"]
        assert "_size_bytes" in chart_field

        # 验证引用文件存在
        ref_path = chart_field["_ref"]
        payload_file = settings.sessions_dir / session_id / "workspace" / "artifacts" / ref_path
        assert payload_file.exists()

        # 验证引用文件内容
        payload_data = json.loads(payload_file.read_text())
        assert payload_data == large_chart

    def test_resolve_references(self, tmp_path):
        """测试引用解析。"""
        session_id = "test_resolve"
        settings.data_dir = tmp_path

        memory = ConversationMemory(session_id)

        # 创建大型数据
        large_data = {"preview": [{"row": i} for i in range(1000)]}
        entry = {
            "role": "assistant",
            "content": "数据预览",
            "dataframe_preview": large_data,
        }

        memory.append(entry)

        # 不解析引用
        loaded_with_refs = memory.load_all(resolve_refs=False)
        assert "_ref" in loaded_with_refs[0]["dataframe_preview"]

        # 解析引用
        loaded_resolved = memory.load_all(resolve_refs=True)
        assert "_ref" not in str(loaded_resolved[0]["dataframe_preview"])
        assert loaded_resolved[0]["dataframe_preview"] == large_data


class TestAutoCompression:
    """测试自动压缩机制。"""

    def test_auto_compress_triggered(self, tmp_path, monkeypatch):
        """测试当文件超过阈值时自动触发压缩。"""
        # 设置较小的阈值用于测试
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        monkeypatch.setattr(settings, "memory_auto_compress", True)
        monkeypatch.setattr(settings, "memory_compress_threshold_kb", 1)  # 1 KB
        monkeypatch.setattr(settings, "memory_keep_recent_messages", 5)

        session = Session()

        # 添加足够多的消息触发压缩
        for i in range(20):
            session.add_message(
                "user", f"这是一条很长的消息，用于测试自动压缩功能。消息编号: {i}" * 10
            )
            session.add_message("assistant", f"收到消息 {i}，正在处理。" * 10)

        # 验证压缩已触发（消息数量应该减少）
        # 注意：由于 _check_auto_compress 只在 add_message 时调用，
        # 实际压缩可能在多次添加后才触发
        assert len(session.messages) < 40  # 原本有 40 条消息

    def test_auto_compress_disabled(self, tmp_path, monkeypatch):
        """测试禁用自动压缩时不触发。"""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        monkeypatch.setattr(settings, "memory_auto_compress", False)

        session = Session()
        initial_count = len(session.messages)

        # 添加大量消息
        for i in range(20):
            session.add_message("user", f"消息 {i}" * 50)
            session.add_message("assistant", f"回复 {i}" * 50)

        # 消息应该全部保留（不压缩）
        assert len(session.messages) == initial_count + 40


class TestMemoryFileSize:
    """测试 memory.jsonl 文件大小优化效果。"""

    def test_memory_size_with_large_payloads(self, tmp_path):
        """验证大型数据引用化后文件大小减少。"""
        session_id = "test_size"
        settings.data_dir = tmp_path

        memory = ConversationMemory(session_id)

        # 创建多个大型图表
        for i in range(4):
            large_chart = {
                "data": [{"x": list(range(1000)), "y": list(range(1000))} for _ in range(5)],
                "layout": {"title": f"Chart {i}" * 50},
            }
            entry = {
                "role": "assistant",
                "content": f"图表 {i}",
                "chart_data": large_chart,
            }
            memory.append(entry)

        # 获取 memory.jsonl 文件大小
        memory_path = settings.sessions_dir / session_id / "memory.jsonl"
        memory_size = memory_path.stat().st_size

        # 验证文件大小远小于原始数据大小
        # 原始数据约 4 * (5 * 1000 * 2 * 8 + title) ≈ 300+ KB
        # 引用化后应该只有几 KB
        assert memory_size < 10 * 1024  # 小于 10 KB

        # 验证 payloads 目录存在且包含文件
        payloads_dir = (
            settings.sessions_dir / session_id / "workspace" / "artifacts" / "memory-payloads"
        )
        assert payloads_dir.exists()
        payload_files = list(payloads_dir.glob("*.json"))
        assert len(payload_files) == 4  # 4 个图表文件


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
