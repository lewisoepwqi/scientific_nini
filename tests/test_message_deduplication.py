"""
消息去重架构测试

测试 WebSocket 事件的 message_id 和 operation 字段
"""

import pytest
from nini.models.schemas import WSEvent


class TestMessageDeduplication:
    """测试消息去重功能"""

    def test_ws_event_with_metadata(self):
        """测试 WSEvent 支持 metadata 字段"""
        event = WSEvent(
            type="text",
            data="测试内容",
            session_id="session-123",
            turn_id="turn-456",
            metadata={
                "message_id": "turn-456-0",
                "operation": "append",
            },
        )
        assert event.metadata is not None
        assert event.metadata.get("message_id") == "turn-456-0"
        assert event.metadata.get("operation") == "append"

    def test_ws_event_without_metadata(self):
        """测试无 metadata 的 WSEvent（向后兼容）"""
        event = WSEvent(
            type="text",
            data="测试内容",
            session_id="session-123",
            turn_id="turn-456",
        )
        # metadata 默认为空字典
        assert event.metadata == {}

    def test_message_id_format(self):
        """测试 message_id 格式"""
        turn_id = "turn-abc123"
        sequence = 0
        message_id = f"{turn_id}-{sequence}"
        assert message_id == "turn-abc123-0"

    def test_operation_types(self):
        """测试 operation 类型"""
        operations = ["append", "replace", "complete"]
        for op in operations:
            event = WSEvent(
                type="text",
                data="测试",
                metadata={"operation": op},
            )
            assert event.metadata.get("operation") == op

    def test_multiple_messages_same_turn(self):
        """测试同轮对话多个消息的唯一ID"""
        turn_id = "turn-xyz789"
        message_ids = []

        for seq in range(3):
            message_id = f"{turn_id}-{seq}"
            message_ids.append(message_id)

        # 验证每个消息ID都是唯一的
        assert len(set(message_ids)) == 3
        assert message_ids == [
            "turn-xyz789-0",
            "turn-xyz789-1",
            "turn-xyz789-2",
        ]


class TestGenerateReportMessageHandling:
    """测试 generate_report 工具的消息处理"""

    def test_replace_operation_for_report(self):
        """测试报告生成使用 replace 操作"""
        # 模拟流式预览
        preview_event = WSEvent(
            type="text",
            data="正在生成报告...",
            turn_id="turn-123",
            metadata={
                "message_id": "turn-123-0",
                "operation": "append",
            },
        )

        # 模拟最终报告（替换预览）
        report_event = WSEvent(
            type="text",
            data="# 完整报告内容",
            turn_id="turn-123",
            metadata={
                "message_id": "turn-123-0",
                "operation": "replace",
            },
        )

        assert preview_event.metadata.get("operation") == "append"
        assert report_event.metadata.get("operation") == "replace"
        # 同一 message_id
        assert preview_event.metadata.get("message_id") == report_event.metadata.get("message_id")


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_legacy_event_without_message_id(self):
        """测试无 message_id 的旧事件仍能正常处理"""
        legacy_event = WSEvent(
            type="text",
            data="旧格式消息",
            turn_id="turn-123",
            # 无 metadata
        )

        # 前端应回退到传统追加逻辑
        message_id = legacy_event.metadata.get("message_id") if legacy_event.metadata else None
        assert message_id is None

    def test_legacy_event_handling(self):
        """测试旧事件处理逻辑"""
        event = WSEvent(
            type="text",
            data="内容",
        )

        # 默认 operation 为 append
        operation = event.metadata.get("operation") if event.metadata else "append"
        assert operation == "append"
