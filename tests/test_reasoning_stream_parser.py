"""ReasoningStreamParser 测试。

测试 reasoning 内容提取和流式解析功能。
"""

from __future__ import annotations

import pytest

from nini.agent.providers.base import ReasoningStreamParser


class TestExtractReasoningFromDelta:
    """测试 extract_reasoning_from_delta 方法。"""

    def test_extract_reasoning_content(self):
        """应能提取 reasoning_content 字段。"""
        class MockDelta:
            reasoning_content = "Let me think about this..."
            content = "Final answer"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        assert result == "Let me think about this..."

    def test_extract_reasoning(self):
        """应能提取 reasoning 字段（OpenAI o1 风格）。"""
        class MockDelta:
            reasoning = "Thinking step by step..."
            content = "Answer"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        assert result == "Thinking step by step..."

    def test_extract_thinking(self):
        """应能提取 thinking 字段。"""
        class MockDelta:
            thinking = "Analyzing the problem..."
            content = "Result"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        assert result == "Analyzing the problem..."

    def test_priority_reasoning_content_over_reasoning(self):
        """reasoning_content 优先级高于 reasoning。"""
        class MockDelta:
            reasoning_content = "Primary reasoning"
            reasoning = "Secondary reasoning"
            content = "Answer"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        # 应该返回第一个找到的字段（reasoning_content）
        assert result == "Primary reasoning"

    def test_empty_when_no_reasoning_fields(self):
        """没有 reasoning 字段时返回空字符串。"""
        class MockDelta:
            content = "Just regular content"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        assert result == ""

    def test_empty_when_delta_is_none(self):
        """delta 为 None 时返回空字符串。"""
        result = ReasoningStreamParser.extract_reasoning_from_delta(None)
        assert result == ""

    def test_empty_when_reasoning_is_empty_string(self):
        """reasoning 字段为空字符串时返回空字符串。"""
        class MockDelta:
            reasoning_content = ""
            content = "Answer"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        assert result == ""

    def test_empty_when_reasoning_is_whitespace(self):
        """reasoning 字段为空白时返回该空白（保留原始值）。"""
        class MockDelta:
            reasoning_content = "   "
            content = "Answer"

        delta = MockDelta()
        result = ReasoningStreamParser.extract_reasoning_from_delta(delta)
        # 空白字符串也是 truthy，但通常不会遇到这种情况
        assert result == "   "


class TestReasoningStreamParserConsume:
    """测试 consume 方法。"""

    def test_consume_plain_text(self):
        """处理普通文本。"""
        parser = ReasoningStreamParser()

        text, reasoning, raw = parser.consume(raw_piece="Hello world")

        assert text == "Hello world"
        assert reasoning == ""
        assert raw == "Hello world"

    def test_consume_with_explicit_reasoning(self):
        """处理带 explicit reasoning 的文本。"""
        parser = ReasoningStreamParser()

        text, reasoning, raw = parser.consume(
            raw_piece="Answer",
            explicit_reasoning_piece="Let me think..."
        )

        assert text == "Answer"
        assert reasoning == "Let me think..."

    def test_consume_with_think_tags(self):
        """处理带 <think> 标签的文本。"""
        parser = ReasoningStreamParser(enable_tag_split=True)

        text, reasoning, raw = parser.consume(
            raw_piece="<think>This is reasoning</think>Final answer"
        )

        assert "Final answer" in text
        assert "This is reasoning" in reasoning

    def test_consume_cumulative_stream(self):
        """处理累计流（某些 API 返回完整历史而非增量）。"""
        parser = ReasoningStreamParser()

        # 第一块
        text1, _, _ = parser.consume(raw_piece="Hello")
        assert text1 == "Hello"

        # 第二块（累计格式：包含历史）
        text2, _, _ = parser.consume(raw_piece="Hello world")
        assert text2 == " world"  # 只返回增量


class TestStripReasoningMarkers:
    """测试 strip_reasoning_markers 方法。"""

    def test_strip_think_tags(self):
        """去除 <think> 标签。"""
        text = "<think>reasoning</think>answer"
        result = ReasoningStreamParser.strip_reasoning_markers(text)
        assert result == "reasoninganswer"

    def test_strip_thinking_tags(self):
        """去除 <thinking> 标签。"""
        text = "<thinking>reasoning</thinking>answer"
        result = ReasoningStreamParser.strip_reasoning_markers(text)
        assert result == "reasoninganswer"

    def test_strip_unicode_tags(self):
        """去除 Unicode think 标签。"""
        text = "◁think▷reasoning◁/think▷answer"
        result = ReasoningStreamParser.strip_reasoning_markers(text)
        assert result == "reasoninganswer"

    def test_strip_case_insensitive(self):
        """大小写不敏感地去除标签。"""
        text = "<THINK>reasoning</Think>answer"
        result = ReasoningStreamParser.strip_reasoning_markers(text)
        assert result == "reasoninganswer"

    def test_no_change_when_no_tags(self):
        """没有标签时保持不变。"""
        text = "Plain text without markers"
        result = ReasoningStreamParser.strip_reasoning_markers(text)
        assert result == text


class TestNormalizeStreamPiece:
    """测试 _normalize_stream_piece 静态方法。"""

    def test_incremental_piece(self):
        """处理增量分片。"""
        piece, snapshot = ReasoningStreamParser._normalize_stream_piece(
            " world", "Hello"
        )
        assert piece == " world"
        assert snapshot == "Hello world"

    def test_cumulative_piece(self):
        """处理累计分片。"""
        piece, snapshot = ReasoningStreamParser._normalize_stream_piece(
            "Hello world", "Hello"
        )
        assert piece == " world"  # 返回增量部分
        assert snapshot == "Hello world"

    def test_empty_piece(self):
        """处理空分片。"""
        piece, snapshot = ReasoningStreamParser._normalize_stream_piece(
            "", "Hello"
        )
        assert piece == ""
        assert snapshot == "Hello"


class TestIntegration:
    """集成测试。"""

    def test_full_reasoning_pipeline(self):
        """测试完整的 reasoning 处理流程。"""
        parser = ReasoningStreamParser(enable_tag_split=True)

        # 模拟流式响应
        chunks = [
            ("<think>", ""),  # 开始 thinking
            ("Let me analyze...", "Let me analyze..."),
            ("</think>", ""),  # 结束 thinking
            ("The answer is 42", ""),
        ]

        all_text = []
        all_reasoning = []

        for raw_piece, explicit in chunks:
            text, reasoning, _ = parser.consume(
                raw_piece=raw_piece,
                explicit_reasoning_piece=explicit
            )
            all_text.append(text)
            all_reasoning.append(reasoning)

        final_text = "".join(all_text)
        final_reasoning = "".join(all_reasoning)

        # 验证结果
        assert "The answer is 42" in final_text
        assert "Let me analyze..." in final_reasoning
