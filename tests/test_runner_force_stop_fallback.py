"""Runner FORCE_STOP 分支应在有产物时 yield 兜底总结。"""

from __future__ import annotations


def test_force_stop_emits_fallback_summary_when_artifacts_present() -> None:
    """若 session.messages 含 chart artifact，FORCE_STOP 应先 yield 兜底总结。"""
    from nini.agent.runner import AgentRunner
    from nini.agent.session import Session

    session = Session()
    session.messages = [
        {"role": "user", "content": "画柱状图"},
        {
            "role": "assistant",
            "event_type": "artifact",
            "artifacts": [
                {"name": "c.png", "type": "chart", "download_url": "/a/c.png"},
            ],
        },
    ]

    runner = AgentRunner()
    texts = list(runner._build_force_stop_texts(session))

    # 至少 2 段：兜底总结 + 原警告
    assert len(texts) >= 2
    assert "![c.png](/a/c.png)" in texts[0]
    assert "检测到工具调用死循环" in texts[-1]


def test_force_stop_falls_back_to_warning_only_when_no_artifacts() -> None:
    """session 里没可用产物时，仍只 yield 原警告文本。"""
    from nini.agent.runner import AgentRunner
    from nini.agent.session import Session

    session = Session()
    session.messages = [{"role": "user", "content": "test"}]

    runner = AgentRunner()
    texts = list(runner._build_force_stop_texts(session))

    assert len(texts) == 1
    assert "检测到工具调用死循环" in texts[0]
