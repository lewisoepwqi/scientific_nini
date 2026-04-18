"""fallback_summary 兜底总结合成测试。"""

from __future__ import annotations

from nini.utils.fallback_summary import build_fallback_summary


def test_returns_none_when_no_tool_results() -> None:
    """没有任何 tool_result 时应返回 None。"""
    messages = [
        {"role": "user", "content": "画个图"},
        {"role": "assistant", "content": "好的"},
    ]
    assert build_fallback_summary(messages, user_request="画个图") is None


def test_collects_chart_artifact_urls() -> None:
    """从 artifact 事件抽取 chart 类型产物并用 Markdown 图片语法引用。"""
    messages = [
        {"role": "user", "content": "画柱状图"},
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {
                    "name": "bar_chart.png",
                    "type": "chart",
                    "download_url": "/api/artifacts/session/bar_chart.png",
                },
                {
                    "name": "bar_chart.pdf",
                    "type": "chart",
                    "download_url": "/api/artifacts/session/bar_chart.pdf",
                },
            ],
        },
    ]
    out = build_fallback_summary(messages, user_request="画柱状图")
    assert out is not None
    assert "![bar_chart.png](/api/artifacts/session/bar_chart.png)" in out
    assert "兜底" in out or "系统终止" in out


def test_extracts_tool_stdout_stats() -> None:
    """tool_result 中的 stdout 若含统计数字应被纳入总结。"""
    messages = [
        {"role": "user", "content": "分析数据"},
        {
            "role": "tool",
            "tool_name": "code_session",
            "content": (
                '{"success": true, '
                '"message": "脚本执行成功\\nstdout:\\n'
                "Col-0: Mean=9.13%, SEM=0.19%, n=3\\n"
                'ANAC017: Mean=6.85%, SEM=0.20%, n=3"}'
            ),
        },
    ]
    out = build_fallback_summary(messages, user_request="分析数据")
    assert out is not None
    assert "Mean=9.13%" in out
    assert "Mean=6.85%" in out


def test_output_is_plain_markdown() -> None:
    """输出不能含 HTML；应是纯 Markdown 可渲染。"""
    messages = [
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {"name": "x.png", "type": "chart", "download_url": "/a/x.png"},
            ],
        }
    ]
    out = build_fallback_summary(messages, user_request="test")
    assert out is not None
    assert "<" not in out.replace("<br>", "").replace("<unknown>", "")


def test_multiple_artifacts_each_referenced_once() -> None:
    """多个 chart artifact 时，同名图表的不同格式只引用一次（优先 png）。"""
    messages = [
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {"name": "c.pdf", "type": "chart", "download_url": "/a/c.pdf"},
                {"name": "c.png", "type": "chart", "download_url": "/a/c.png"},
                {"name": "c.svg", "type": "chart", "download_url": "/a/c.svg"},
            ],
        }
    ]
    out = build_fallback_summary(messages, user_request="test")
    assert out is not None
    assert "/a/c.png" in out
    assert "/a/c.pdf" not in out
    assert "/a/c.svg" not in out
