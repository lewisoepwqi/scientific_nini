"""EditFile 工具单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nini.tools.edit_file import EditFile
from nini.workspace import WorkspaceManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def skill() -> EditFile:
    return EditFile()


@pytest.fixture()
def mock_session() -> MagicMock:
    session = MagicMock()
    session.id = "test-session-edit-file"
    return session


@pytest.fixture()
def workspace(tmp_path: Path, mock_session: MagicMock):
    """创建临时工作区目录，并 patch settings.sessions_dir。"""
    ws = tmp_path / "sessions" / mock_session.id / "workspace"
    ws.mkdir(parents=True)
    with (
        patch("nini.tools.edit_file.settings") as mock_settings,
        patch("nini.workspace.manager.settings") as manager_settings,
    ):
        sessions_dir = tmp_path / "sessions"
        mock_settings.sessions_dir = sessions_dir
        manager_settings.sessions_dir = sessions_dir
        yield ws


# ---------------------------------------------------------------------------
# 属性测试
# ---------------------------------------------------------------------------


def test_name(skill: EditFile):
    assert skill.name == "edit_file"


def test_description_not_empty(skill: EditFile):
    assert len(skill.description) > 0


def test_parameters_schema(skill: EditFile):
    params = skill.parameters
    assert params["type"] == "object"
    assert "file_path" in params["properties"]
    assert "operation" in params["properties"]
    assert "file_path" in params["required"]
    assert "operation" in params["required"]


# ---------------------------------------------------------------------------
# 参数验证
# ---------------------------------------------------------------------------


async def test_empty_file_path_returns_error(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(mock_session, file_path="", operation="read")
    assert not result.success
    assert "不能为空" in result.message


async def test_unknown_operation_returns_error(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(mock_session, file_path="test.txt", operation="delete")
    assert not result.success
    assert "不支持的操作" in result.message


# ---------------------------------------------------------------------------
# 路径安全测试
# ---------------------------------------------------------------------------


async def test_path_traversal_rejected(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(mock_session, file_path="../outside.txt", operation="read")
    assert not result.success
    assert "无效" in result.message or "超出工作区" in result.message


async def test_absolute_path_rejected(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(mock_session, file_path="/etc/passwd", operation="read")
    assert not result.success
    assert "无效" in result.message or "超出工作区" in result.message


async def test_workspace_prefix_bypass_rejected(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    """防止通过同级目录前缀伪造绕过工作区校验。"""
    result = await skill.execute(
        mock_session,
        file_path="../workspace_evil/pwn.txt",
        operation="write",
        content="blocked",
    )
    assert not result.success
    assert "无效" in result.message or "超出工作区" in result.message

    outside_path = workspace.parent / "workspace_evil" / "pwn.txt"
    assert not outside_path.exists()


# ---------------------------------------------------------------------------
# read 操作
# ---------------------------------------------------------------------------


async def test_read_existing_file(skill: EditFile, mock_session: MagicMock, workspace: Path):
    test_file = workspace / "hello.txt"
    test_file.write_text("第一行\n第二行\n第三行\n", encoding="utf-8")

    result = await skill.execute(mock_session, file_path="hello.txt", operation="read")

    assert result.success
    assert result.data["content"] == "第一行\n第二行\n第三行\n"
    assert result.data["line_count"] == 4  # 末尾 \n 后有空行


async def test_read_nonexistent_file_returns_error(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(mock_session, file_path="no_such_file.txt", operation="read")
    assert not result.success
    assert "不存在" in result.message


# ---------------------------------------------------------------------------
# write 操作
# ---------------------------------------------------------------------------


async def test_write_creates_new_file(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(
        mock_session, file_path="new_file.txt", operation="write", content="Hello World"
    )

    assert result.success
    assert (workspace / "new_file.txt").read_text(encoding="utf-8") == "Hello World"
    assert result.data["action"] == "创建"
    manager = WorkspaceManager(mock_session.id)
    index = manager._load_index()
    assert any(item["name"] == "new_file.txt" for item in index["notes"])
    assert not any(item["name"] == "new_file.txt" for item in index["artifacts"])


async def test_write_overwrites_existing_file(skill: EditFile, mock_session: MagicMock, workspace: Path):
    test_file = workspace / "existing.txt"
    test_file.write_text("旧内容", encoding="utf-8")

    result = await skill.execute(
        mock_session, file_path="existing.txt", operation="write", content="新内容"
    )

    assert result.success
    assert test_file.read_text(encoding="utf-8") == "新内容"
    assert result.data["action"] == "更新"


async def test_write_creates_subdirectory(skill: EditFile, mock_session: MagicMock, workspace: Path):
    result = await skill.execute(
        mock_session, file_path="subdir/nested.txt", operation="write", content="嵌套文件"
    )

    assert result.success
    assert (workspace / "subdir" / "nested.txt").read_text(encoding="utf-8") == "嵌套文件"


# ---------------------------------------------------------------------------
# append 操作
# ---------------------------------------------------------------------------


async def test_append_to_existing_file_with_newline(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    test_file = workspace / "append_target.txt"
    test_file.write_text("第一行\n", encoding="utf-8")

    result = await skill.execute(
        mock_session, file_path="append_target.txt", operation="append", content="第二行"
    )

    assert result.success
    content = test_file.read_text(encoding="utf-8")
    assert content == "第一行\n第二行"


async def test_append_to_existing_file_without_trailing_newline(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    test_file = workspace / "no_newline.txt"
    test_file.write_text("第一行", encoding="utf-8")  # 无末尾换行

    result = await skill.execute(
        mock_session, file_path="no_newline.txt", operation="append", content="第二行"
    )

    assert result.success
    content = test_file.read_text(encoding="utf-8")
    # 应自动补换行再追加
    assert content == "第一行\n第二行"


async def test_append_creates_file_when_missing(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    result = await skill.execute(
        mock_session,
        file_path="brand_new.txt",
        operation="append",
        content="初始内容",
        create_if_missing=True,
    )

    assert result.success
    assert (workspace / "brand_new.txt").read_text(encoding="utf-8") == "初始内容"
    manager = WorkspaceManager(mock_session.id)
    files = manager.list_workspace_files_with_paths()
    created = next(item for item in files if item["name"] == "brand_new.txt")
    assert created["kind"] == "document"
    assert created["path"] == "brand_new.txt"


async def test_append_fails_when_missing_and_create_disabled(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    result = await skill.execute(
        mock_session,
        file_path="missing.txt",
        operation="append",
        content="内容",
        create_if_missing=False,
    )

    assert not result.success
    assert "不存在" in result.message


# ---------------------------------------------------------------------------
# edit 操作 — 文本匹配替换
# ---------------------------------------------------------------------------


async def test_edit_text_replace_found(skill: EditFile, mock_session: MagicMock, workspace: Path):
    test_file = workspace / "edit_me.txt"
    test_file.write_text("Hello World\nSecond Line\n", encoding="utf-8")

    result = await skill.execute(
        mock_session,
        file_path="edit_me.txt",
        operation="edit",
        old_string="Hello World",
        new_string="你好世界",
    )

    assert result.success
    assert test_file.read_text(encoding="utf-8") == "你好世界\nSecond Line\n"
    assert result.data["method"] == "text_replace"


async def test_edit_text_replace_not_found(skill: EditFile, mock_session: MagicMock, workspace: Path):
    test_file = workspace / "edit_me.txt"
    test_file.write_text("原始内容\n", encoding="utf-8")

    result = await skill.execute(
        mock_session,
        file_path="edit_me.txt",
        operation="edit",
        old_string="不存在的文本",
        new_string="替换内容",
    )

    assert not result.success
    assert "未找到" in result.message


async def test_edit_no_params_returns_error(skill: EditFile, mock_session: MagicMock, workspace: Path):
    test_file = workspace / "edit_me.txt"
    test_file.write_text("内容\n", encoding="utf-8")

    result = await skill.execute(
        mock_session,
        file_path="edit_me.txt",
        operation="edit",
    )

    assert not result.success
    assert "old_string" in result.message or "start_line" in result.message


# ---------------------------------------------------------------------------
# edit 操作 — 行号范围替换
# ---------------------------------------------------------------------------


async def test_edit_line_range_replace(skill: EditFile, mock_session: MagicMock, workspace: Path):
    test_file = workspace / "lines.txt"
    test_file.write_text("行1\n行2\n行3\n行4\n", encoding="utf-8")

    result = await skill.execute(
        mock_session,
        file_path="lines.txt",
        operation="edit",
        start_line=2,
        end_line=3,
        new_string="新行2\n新行3",
    )

    assert result.success
    content = test_file.read_text(encoding="utf-8")
    assert "新行2" in content
    assert "新行3" in content
    assert result.data["method"] == "line_range"


async def test_edit_updates_workspace_index_without_session_name_error(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    """edit 操作应能同步工作区索引，不再触发 session 未定义警告。"""
    test_file = workspace / "edit_indexed.md"
    test_file.write_text("旧标题\n正文\n", encoding="utf-8")

    result = await skill.execute(
        mock_session,
        file_path="edit_indexed.md",
        operation="edit",
        old_string="旧标题",
        new_string="新标题",
    )

    assert result.success
    manager = WorkspaceManager(mock_session.id)
    notes = manager.list_notes()
    note_names = [item.get("name") for item in notes]
    assert "edit_indexed.md" in note_names


async def test_edit_nonexistent_file_returns_error(
    skill: EditFile, mock_session: MagicMock, workspace: Path
):
    result = await skill.execute(
        mock_session,
        file_path="ghost.txt",
        operation="edit",
        old_string="something",
        new_string="other",
    )

    assert not result.success
    assert "不存在" in result.message


# ---------------------------------------------------------------------------
# 索引更新测试 - 验证文件写入后在工作区索引中可见
# ---------------------------------------------------------------------------


async def test_write_adds_file_to_workspace_index(skill: EditFile, mock_session: MagicMock, workspace: Path):
    """测试 write 操作将文件添加到文稿索引。"""
    from nini.workspace import WorkspaceManager

    result = await skill.execute(
        mock_session, file_path="indexed_file.md", operation="write", content="# Test Content"
    )

    assert result.success

    # 验证文件在索引中
    manager = WorkspaceManager(mock_session.id)
    notes = manager.list_notes()
    note_names = [item.get("name") for item in notes]
    assert "indexed_file.md" in note_names


async def test_append_creates_file_in_workspace_index(skill: EditFile, mock_session: MagicMock, workspace: Path):
    """测试 append 操作创建新文件时添加到文稿索引。"""
    from nini.workspace import WorkspaceManager

    result = await skill.execute(
        mock_session,
        file_path="appended_file.txt",
        operation="append",
        content="Initial content",
        create_if_missing=True,
    )

    assert result.success

    # 验证文件在索引中
    manager = WorkspaceManager(mock_session.id)
    notes = manager.list_notes()
    note_names = [item.get("name") for item in notes]
    assert "appended_file.txt" in note_names
