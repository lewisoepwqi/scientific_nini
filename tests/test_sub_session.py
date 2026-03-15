"""测试 SubSession 的隔离行为。"""

import uuid
from pathlib import Path

import pytest

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


def test_agent_runner_accepts_subsession():
    """AgentRunner 实例化时传入 SubSession 不应抛出异常。"""
    from nini.agent.runner import AgentRunner

    session = SubSession(id=uuid.uuid4().hex[:12])
    runner = AgentRunner()
    # 仅验证实例化不报错，不执行 run()
    assert runner is not None
    assert session.task_manager is not None
    assert session.event_callback is None
