"""测试 SubSession 的隔离行为。"""

import uuid
from pathlib import Path

import pytest

from nini.agent.session import session_manager
from nini.agent.sub_session import SubSession
from nini.memory.conversation import InMemoryConversationMemory


def test_subsession_no_disk_writes(tmp_path, monkeypatch):
    """初始化 SubSession 不应在 data/sessions/ 创建任何文件。"""
    from nini.config import settings

    # sessions_dir 是 data_dir 的派生属性，需通过 data_dir 重定向
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session = SubSession(id=uuid.uuid4().hex[:12])
    # sessions_dir 下不应有任何新目录
    sessions_dir = tmp_path / "data" / "sessions"
    if sessions_dir.exists():
        assert list(sessions_dir.iterdir()) == []


def test_conversation_memory_is_in_memory():
    session = SubSession(id=uuid.uuid4().hex[:12])
    assert isinstance(session.conversation_memory, InMemoryConversationMemory)


def test_knowledge_memory_is_none():
    session = SubSession(id=uuid.uuid4().hex[:12])
    assert session.knowledge_memory is None


def test_add_message_writes_to_memory():
    session = SubSession(id=uuid.uuid4().hex[:12])
    session.add_message("user", "执行数据清洗")
    # messages 列表应包含该消息
    assert len(session.messages) == 1
    assert session.messages[0]["content"] == "执行数据清洗"
    # 内存记忆中也应有该消息
    mem_messages = session.conversation_memory.load_messages()
    assert len(mem_messages) == 1


def test_datasets_shared_reference():
    """datasets 应共享父会话的引用。"""
    import pandas as pd

    shared_datasets = {"raw_data": pd.DataFrame({"a": [1, 2, 3]})}
    session = SubSession(id=uuid.uuid4().hex[:12], datasets=shared_datasets)
    assert session.datasets is shared_datasets
    assert "raw_data" in session.datasets


def test_parent_session_id_field():
    session = SubSession(id=uuid.uuid4().hex[:12], parent_session_id="parent123")
    assert session.parent_session_id == "parent123"


@pytest.mark.asyncio
async def test_stat_model_does_not_crash_when_knowledge_memory_is_none():
    import pandas as pd

    from nini.tools.stat_model import StatModelTool

    session = SubSession(id=uuid.uuid4().hex[:12])
    session.datasets["demo"] = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    result = await StatModelTool().execute(
        session,
        method="correlation",
        dataset_name="demo",
        columns=["x", "y"],
    )

    assert result.success is True


@pytest.mark.asyncio
async def test_stat_test_does_not_crash_when_knowledge_memory_is_none():
    import pandas as pd

    from nini.tools.stat_test import StatTestTool

    session = SubSession(id=uuid.uuid4().hex[:12])
    session.datasets["demo"] = pd.DataFrame(
        {
            "value": [1.0, 2.0, 3.0, 10.0, 11.0, 12.0],
            "group": ["A", "A", "A", "B", "B", "B"],
        }
    )

    result = await StatTestTool().execute(
        session,
        method="independent_t",
        dataset_name="demo",
        value_column="value",
        group_column="group",
    )

    assert result.success is True


@pytest.mark.asyncio
async def test_subsession_stat_tools_do_not_persist_analysis_memory(tmp_path, monkeypatch):
    import pandas as pd

    from nini.memory.compression import (
        clear_session_analysis_memories,
        list_session_analysis_memories,
    )
    from nini.tools.stat_model import StatModelTool

    from nini.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session = SubSession(id=uuid.uuid4().hex[:12])
    session.datasets["demo"] = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    try:
        result = await StatModelTool().execute(
            session,
            method="correlation",
            dataset_name="demo",
            columns=["x", "y"],
        )

        assert result.success is True
        memories = list_session_analysis_memories(session.id)
        assert len(memories) == 1
        assert not (tmp_path / "data" / "sessions" / session.id / "analysis_memories").exists()
    finally:
        clear_session_analysis_memories(session.id)


def test_subsession_token_tracker_does_not_write_cost_file(tmp_path, monkeypatch):
    from nini.config import settings
    from nini.utils.token_counter import get_tracker, remove_tracker

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session = SubSession(id=uuid.uuid4().hex[:12])

    try:
        tracker = get_tracker(session.id)
        tracker.record(model="glm-5", input_tokens=10, output_tokens=5)
        assert not (tmp_path / "data" / "sessions" / session.id / "cost.jsonl").exists()
    finally:
        remove_tracker(session.id)


def test_session_manager_skips_meta_persistence_for_subsession(tmp_path, monkeypatch):
    from nini.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session = SubSession(id=uuid.uuid4().hex[:12])

    session_manager.save_session_pending_actions(
        session.id,
        [{"type": "tool_failure_unresolved", "key": "k", "summary": "s"}],
    )

    assert not (tmp_path / "data" / "sessions" / session.id / "meta.json").exists()


@pytest.mark.asyncio
async def test_subsession_analysis_memory_is_attributed_to_parent_session(tmp_path, monkeypatch):
    import pandas as pd

    from nini.config import settings
    from nini.memory.compression import (
        clear_session_analysis_memories,
        list_session_analysis_memories,
    )
    from nini.tools.stat_model import StatModelTool

    parent_session_id = "parent123"
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session = SubSession(id=uuid.uuid4().hex[:12], parent_session_id=parent_session_id)
    session.datasets["demo"] = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    try:
        result = await StatModelTool().execute(
            session,
            method="correlation",
            dataset_name="demo",
            columns=["x", "y"],
        )

        assert result.success is True
        parent_memories = list_session_analysis_memories(parent_session_id)
        assert len(parent_memories) == 1
        assert parent_memories[0].session_id == parent_session_id
        assert not (tmp_path / "data" / "sessions" / session.id / "analysis_memories").exists()
    finally:
        clear_session_analysis_memories(parent_session_id)
        clear_session_analysis_memories(session.id)


def test_subsession_workspace_and_artifacts_use_parent_session(tmp_path, monkeypatch):
    from nini.config import settings
    from nini.memory.storage import ArtifactStorage
    from nini.workspace import WorkspaceManager

    parent_session_id = "parent456"
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session = SubSession(id=uuid.uuid4().hex[:12], parent_session_id=parent_session_id)

    note_path = WorkspaceManager(session).save_text_file("notes/sub-agent.md", "hello")
    artifact_path = ArtifactStorage(session).save_text("artifact", "child.txt")

    assert str(note_path).startswith(str(tmp_path / "data" / "sessions" / parent_session_id))
    assert str(artifact_path).startswith(str(tmp_path / "data" / "sessions" / parent_session_id))
    assert not (tmp_path / "data" / "sessions" / session.id / "workspace").exists()


def test_agent_runner_accepts_subsession():
    """AgentRunner 实例化时传入 SubSession 不应抛出异常。"""
    from nini.agent.runner import AgentRunner

    session = SubSession(id=uuid.uuid4().hex[:12])
    runner = AgentRunner()
    # 仅验证实例化不报错，不执行 run()
    assert runner is not None
    assert session.task_manager is not None
    assert session.event_callback is None
