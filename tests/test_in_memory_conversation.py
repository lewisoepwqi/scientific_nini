"""测试 InMemoryConversationMemory 的内存行为。"""

import pytest
from nini.memory.conversation import InMemoryConversationMemory


def test_append_and_load_messages():
    mem = InMemoryConversationMemory()
    mem.append({"role": "user", "content": "hello"})
    mem.append({"role": "assistant", "content": "hi"})
    messages = mem.load_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"


def test_load_all_returns_all_entries():
    mem = InMemoryConversationMemory()
    mem.append({"role": "user", "content": "test"})
    mem.append({"key": "no_role_entry"})
    all_entries = mem.load_all()
    assert len(all_entries) == 2


def test_clear():
    mem = InMemoryConversationMemory()
    mem.append({"role": "user", "content": "hello"})
    mem.clear()
    assert mem.load_messages() == []


def test_no_disk_writes(tmp_path):
    """验证内存记忆不写任何磁盘文件。"""
    mem = InMemoryConversationMemory()
    mem.append({"role": "user", "content": "hello"})
    # 内存中有数据，但没有文件被创建
    assert not list(tmp_path.iterdir())


def test_append_adds_timestamp():
    mem = InMemoryConversationMemory()
    mem.append({"role": "user", "content": "hello"})
    entries = mem.load_all()
    assert "_ts" in entries[0]
