"""对话可观测性与压缩能力测试。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from nini.agent.runner import AgentRunner, EventType
from nini.agent.session import Session, session_manager
from nini.app import create_app
from nini.config import settings
from nini.memory.compression import compress_session_history


class _DummyResolver:
    async def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        class _Chunk:
            text = "已完成分析。"
            tool_calls = []
            usage = None

        yield _Chunk()


class _DummyKnowledgeLoader:
    def select_with_hits(self, *args, **kwargs):
        return (
            "这是检索命中的知识内容",
            [
                {
                    "source": "demo.md",
                    "score": 2.0,
                    "hits": 1,
                    "snippet": "这是检索命中的知识内容",
                }
            ],
        )


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.mark.asyncio
async def test_runner_emits_retrieval_event_before_text() -> None:
    session = Session()
    session.add_message("user", "请给我 t 检验建议")

    runner = AgentRunner(
        resolver=_DummyResolver(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )
    events = []
    async for event in runner.run(session, "继续", append_user_message=False):
        events.append(event)
        if event.type == EventType.DONE:
            break

    event_types = [e.type.value for e in events]
    assert "retrieval" in event_types
    assert "text" in event_types
    retrieval_idx = event_types.index("retrieval")
    text_idx = event_types.index("text")
    assert retrieval_idx < text_idx

    retrieval_event = next(e for e in events if e.type == EventType.RETRIEVAL)
    assert retrieval_event.data["query"] == "请给我 t 检验建议"
    assert len(retrieval_event.data["results"]) == 1


def test_compress_session_history_archives_and_updates_context() -> None:
    session = Session()
    for i in range(8):
        role = "user" if i % 2 == 0 else "assistant"
        session.add_message(role, f"消息-{i}")

    result = compress_session_history(session)

    assert result["success"] is True, result
    assert result["archived_count"] >= 4
    assert result["remaining_count"] >= 1
    assert "消息-0" in session.compressed_context
    archive_path = Path(result["archive_path"])
    assert archive_path.exists()


def test_api_compress_session_endpoint() -> None:
    app = create_app()
    with TestClient(app) as client:
        create_resp = client.post("/api/sessions")
        session_id = create_resp.json()["data"]["session_id"]

        session = session_manager.get_session(session_id)
        assert session is not None
        for i in range(6):
            session.add_message("user" if i % 2 == 0 else "assistant", f"历史-{i}")

        resp = client.post(f"/api/sessions/{session_id}/compress")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["data"]["archived_count"] >= 4
        assert payload["data"]["remaining_count"] >= 1

