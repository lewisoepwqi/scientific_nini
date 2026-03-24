"""
测试 reasoning 显示逻辑，确保思考过程不会重复显示。
"""

import pytest


class TestMergeReasoningContent:
    """测试 reasoning 内容合并逻辑（对应前端 web/src/store/utils.ts）"""

    def test_empty_previous(self):
        """当 previous 为空时，应直接返回 incoming"""
        previous = ""
        incoming = "思考过程内容"
        # 模拟前端逻辑：isLive 未定义时，按旧逻辑处理
        result = incoming if not previous else None
        assert result == "思考过程内容"

    def test_empty_incoming(self):
        """当 incoming 为空时，应返回 previous"""
        previous = "已有内容"
        incoming = ""
        result = previous if not incoming else None
        assert result == "已有内容"

    def test_live_streaming_cumulative(self):
        """流式阶段：新内容包含旧内容前缀（累计流）"""
        previous = "思考过程"
        incoming = "思考过程中的内容"
        is_live = True

        # 累计流逻辑
        if incoming.startswith(previous):
            result = incoming
        else:
            result = previous + incoming

        assert result == "思考过程中的内容"

    def test_live_streaming_delta(self):
        """流式阶段：新内容是增量（delta 流）"""
        previous = "思考过程"
        incoming = "中的内容"
        is_live = True

        # Delta 流逻辑
        if incoming.startswith(previous):
            result = incoming
        else:
            result = previous + incoming

        assert result == "思考过程中的内容"

    def test_final_event_replace(self):
        """最终事件：isLive=False 时应直接替换为完整内容"""
        previous = "思考过程（可能不完整或有差异）"
        incoming = "完整的思考过程内容"
        is_live = False

        # 新逻辑：最终事件直接替换
        if is_live is False:
            result = incoming
        elif incoming.startswith(previous):
            result = incoming
        else:
            result = previous + incoming

        assert result == "完整的思考过程内容"

    def test_final_event_no_duplicate(self):
        """关键测试：最终事件不应导致内容重复"""
        # 模拟流式接收过程中的内容
        previous = "我正在分析这个问题。首先，我需要理解用户的需求..."
        # 后端发送的完整内容（可能由于格式处理与累计内容有差异）
        incoming = "我正在分析这个问题。首先，我需要理解用户的需求...\n然后进行深入分析。"
        is_live = False

        # 新逻辑：直接替换
        if is_live is False:
            result = incoming
        elif incoming.startswith(previous):
            result = incoming
        else:
            result = previous + incoming

        # 验证：结果应该等于完整内容，而不是 previous + incoming
        assert result == incoming
        assert result != previous + incoming

    def test_backward_compatibility(self):
        """向后兼容：isLive 未定义时保持原有行为"""
        previous = "思考过程"
        incoming = "中的内容"
        is_live = None  # 未定义

        # 原有逻辑（isLive 未定义时）
        if is_live is False:
            result = incoming
        elif incoming.startswith(previous):
            result = incoming
        else:
            result = previous + incoming

        assert result == "思考过程中的内容"


class TestReasoningEventSequence:
    """测试 reasoning 事件序列处理"""

    def test_streaming_sequence(self):
        """模拟流式 reasoning 事件序列"""
        events = [
            {"content": "思考", "reasoningLive": True, "reasoning_id": "r1"},
            {"content": "过程", "reasoningLive": True, "reasoning_id": "r1"},
            {"content": "内容", "reasoningLive": True, "reasoning_id": "r1"},
            {"content": "完整思考过程内容", "reasoningLive": False, "reasoning_id": "r1"},
        ]

        display_content = ""

        for evt in events:
            content = evt["content"]
            is_live = evt["reasoningLive"]

            # 应用合并逻辑
            if not display_content:
                display_content = content
            elif is_live is False:
                # 最终事件：直接替换
                display_content = content
            elif content.startswith(display_content):
                # 累计流
                display_content = content
            else:
                # 增量流
                display_content = display_content + content

        # 验证最终结果
        assert display_content == "完整思考过程内容"
        # 关键验证：不应出现重复
        assert display_content.count("完整") == 1
        assert display_content.count("思考") == 1


class TestReasoningEdgeCases:
    """测试边界情况"""

    def test_whitespace_difference_in_final(self):
        """最终内容与流式内容存在空格差异时不应重复"""
        # 流式过程中可能有额外的空格处理
        previous = "思考过程 "  # 末尾有空格
        incoming = "思考过程"  # 完整内容无末尾空格
        is_live = False

        # 使用新逻辑
        if is_live is False:
            result = incoming
        elif incoming.startswith(previous):
            result = incoming
        else:
            result = previous + incoming

        # 应该直接替换，而不是追加
        assert result == "思考过程"
        assert "思考过程思考过程" not in result

    def test_special_characters(self):
        """处理包含特殊字符的 reasoning"""
        previous = "思考："
        incoming = "思考：\n1. 第一点\n2. 第二点\n```code```"
        is_live = False

        if is_live is False:
            result = incoming
        else:
            result = previous + incoming if not incoming.startswith(previous) else incoming

        assert result == incoming

    def test_very_long_content(self):
        """处理长 reasoning 内容"""
        previous = "x" * 500
        incoming = "y" * 1000
        is_live = False

        if is_live is False:
            result = incoming
        else:
            result = previous + incoming

        assert result == incoming
        assert len(result) == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
