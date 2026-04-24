"""批次完成摘要单元测试（方案 4 预防层）。

仅覆盖 summarizer 纯函数逻辑；runner 注入路径由集成测试覆盖。
"""

from __future__ import annotations

from nini.agent.completion_summarizers import (
    MAX_SUMMARY_LINES,
    format_summary_prompt,
    summarize_completion,
)


class TestSummarizeDatasetCatalog:
    def test_profile_full_with_shape(self) -> None:
        line = summarize_completion(
            "dataset_catalog",
            {"operation": "profile", "dataset_name": "血压心率.xlsx", "view": "full"},
            {"data_summary": {"rows": 2627, "columns": 8}},
        )
        assert line == "dataset_catalog(profile, 血压心率.xlsx, full) — 2627 行 × 8 列"

    def test_profile_default_view(self) -> None:
        line = summarize_completion(
            "dataset_catalog",
            {"operation": "profile", "dataset_name": "a.csv"},
            {"data_summary": {"rows": 10, "columns": 3}},
        )
        assert line is not None
        assert "summary" in line  # view 缺省回填

    def test_non_profile_operation_returns_none(self) -> None:
        assert (
            summarize_completion(
                "dataset_catalog",
                {"operation": "list"},
                {"data_summary": {}},
            )
            is None
        )

    def test_missing_dataset_name_returns_none(self) -> None:
        assert (
            summarize_completion(
                "dataset_catalog",
                {"operation": "profile"},
                {"data_summary": {}},
            )
            is None
        )

    def test_dataset_name_fallback_from_result(self) -> None:
        line = summarize_completion(
            "dataset_catalog",
            {"operation": "profile", "view": "quality"},
            {"data_summary": {"dataset_name": "fallback.xlsx", "rows": 5, "columns": 2}},
        )
        assert line == "dataset_catalog(profile, fallback.xlsx, quality) — 5 行 × 2 列"

    def test_missing_shape_uses_placeholder(self) -> None:
        line = summarize_completion(
            "dataset_catalog",
            {"operation": "profile", "dataset_name": "b.xlsx", "view": "summary"},
            {"data_summary": {}},
        )
        assert line == "dataset_catalog(profile, b.xlsx, summary) — 已完成"


class TestSummarizeCompletionDispatch:
    def test_unregistered_tool_returns_none(self) -> None:
        assert summarize_completion("run_code", {}, {"success": True}) is None

    def test_summarizer_exception_is_swallowed(self) -> None:
        # 传入非 dict 参数类型，summarizer 应吞异常返回 None
        assert summarize_completion("dataset_catalog", {}, "not-a-dict") is None  # type: ignore[arg-type]


class TestFormatSummaryPrompt:
    def test_empty_list_returns_empty_string(self) -> None:
        assert format_summary_prompt([]) == ""

    def test_single_line(self) -> None:
        text = format_summary_prompt(["dataset_catalog(profile, a.xlsx, full) — 10 行 × 2 列"])
        assert "本轮已完成的分析工具" in text
        assert "请勿重复调用" in text
        assert "- dataset_catalog(profile, a.xlsx, full) — 10 行 × 2 列" in text
        assert "仅显示最近" not in text

    def test_truncates_when_exceeds_max(self) -> None:
        many_lines = [f"line-{i}" for i in range(MAX_SUMMARY_LINES + 3)]
        text = format_summary_prompt(many_lines)
        assert "仅显示最近" in text
        # 最早 3 条应被截断，最新一条应保留
        assert "line-0" not in text
        assert f"line-{MAX_SUMMARY_LINES + 2}" in text
