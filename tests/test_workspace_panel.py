"""工作区面板后端新增功能测试（Phase 1.1）。

覆盖：delete_file、rename_file、get_file_preview、search_files 以及对应 API 端点。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    app = create_app()
    with TestClient(app) as c:
        yield c
    session_manager._sessions.clear()


def _create_session_and_upload(client: TestClient) -> tuple[str, str]:
    """创建会话并上传一个 CSV 文件，返回 (session_id, dataset_id)。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]
    upload = client.post(
        "/api/upload",
        data={"session_id": session_id},
        files={"file": ("test.csv", "a,b\n1,2\n3,4\n", "text/csv")},
    )
    dataset_id = upload.json()["dataset"]["id"]
    return session_id, dataset_id


# ---- WorkspaceManager 单元测试 ----


class TestWorkspaceManagerDeleteFile:
    """测试 delete_file 方法。"""

    def test_delete_dataset(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)

        # 确认文件存在
        assert manager.get_dataset_by_id(dataset_id) is not None

        # 删除文件
        deleted = manager.delete_file(dataset_id)
        assert deleted is not None
        assert deleted["id"] == dataset_id

        # 确认已从索引移除
        assert manager.get_dataset_by_id(dataset_id) is None

    def test_delete_nonexistent_returns_none(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)
        assert manager.delete_file("nonexistent_id") is None

    def test_delete_note(self, client: TestClient):
        resp = client.post("/api/sessions")
        session_id = resp.json()["data"]["session_id"]
        manager = WorkspaceManager(session_id)
        note = manager.save_text_note("测试笔记内容", "test_note.md")
        note_id = note["id"]

        # 确认笔记文件存在
        assert Path(note["path"]).exists()

        deleted = manager.delete_file(note_id)
        assert deleted is not None
        assert deleted["id"] == note_id
        # 磁盘文件应已删除
        assert not Path(note["path"]).exists()


class TestWorkspaceManagerRenameFile:
    """测试 rename_file 方法。"""

    def test_rename_dataset(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)

        updated = manager.rename_file(dataset_id, "renamed.csv")
        assert updated is not None
        assert updated["name"] == "renamed.csv"

        # 磁盘文件应已重命名
        new_path = Path(updated["file_path"])
        assert new_path.exists()
        assert "renamed.csv" in new_path.name

    def test_rename_nonexistent_returns_none(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)
        assert manager.rename_file("nonexistent_id", "whatever.csv") is None


class TestWorkspaceManagerSearchFiles:
    """测试 search_files 方法。"""

    def test_search_by_name(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)

        results = manager.search_files("test")
        assert len(results) == 1
        assert results[0]["name"] == "test.csv"

    def test_search_no_match(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)

        results = manager.search_files("不存在的文件")
        assert len(results) == 0

    def test_search_empty_returns_all(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)

        results = manager.search_files("")
        assert len(results) >= 1


class TestWorkspaceManagerFilePreview:
    """测试 get_file_preview 方法。"""

    def test_preview_csv(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)

        preview = manager.get_file_preview(dataset_id)
        assert preview is not None
        assert preview["preview_type"] == "text"
        assert "a,b" in preview["content"]

    def test_preview_note(self, client: TestClient):
        resp = client.post("/api/sessions")
        session_id = resp.json()["data"]["session_id"]
        manager = WorkspaceManager(session_id)
        note = manager.save_text_note("# 标题\n内容正文", "readme.md")

        preview = manager.get_file_preview(note["id"])
        assert preview is not None
        assert preview["preview_type"] == "text"
        assert "# 标题" in preview["content"]

    def test_preview_nonexistent(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        manager = WorkspaceManager(session_id)
        assert manager.get_file_preview("nonexistent_id") is None


# ---- API 端点测试 ----


class TestDeleteAPI:
    """测试 DELETE /api/sessions/{sid}/workspace/files/{fid}。"""

    def test_delete_file(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        resp = client.delete(f"/api/sessions/{session_id}/workspace/files/{dataset_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == dataset_id

        # 确认文件列表中已移除
        files_resp = client.get(f"/api/sessions/{session_id}/workspace/files")
        files = files_resp.json()["data"]["files"]
        assert all(f["id"] != dataset_id for f in files)

    def test_delete_nonexistent_404(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        resp = client.delete(f"/api/sessions/{session_id}/workspace/files/no_such_id")
        assert resp.status_code == 404

    def test_delete_removes_from_session_memory(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        # 确认数据集在内存中
        session = session_manager.get_session(session_id)
        assert session is not None
        assert "test.csv" in session.datasets

        client.delete(f"/api/sessions/{session_id}/workspace/files/{dataset_id}")
        assert "test.csv" not in session.datasets


class TestRenameAPI:
    """测试 PATCH /api/sessions/{sid}/workspace/files/{fid}。"""

    def test_rename_file(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        resp = client.patch(
            f"/api/sessions/{session_id}/workspace/files/{dataset_id}",
            json={"name": "data_v2.csv"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["file"]["name"] == "data_v2.csv"

    def test_rename_empty_name_400(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        resp = client.patch(
            f"/api/sessions/{session_id}/workspace/files/{dataset_id}",
            json={"name": "   "},
        )
        assert resp.status_code == 400

    def test_rename_updates_session_memory(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        session = session_manager.get_session(session_id)
        assert "test.csv" in session.datasets

        client.patch(
            f"/api/sessions/{session_id}/workspace/files/{dataset_id}",
            json={"name": "renamed.csv"},
        )
        assert "test.csv" not in session.datasets
        assert "renamed.csv" in session.datasets


class TestPreviewAPI:
    """测试 GET /api/sessions/{sid}/workspace/files/{fid}/preview。"""

    def test_preview_csv(self, client: TestClient):
        session_id, dataset_id = _create_session_and_upload(client)
        resp = client.get(f"/api/sessions/{session_id}/workspace/files/{dataset_id}/preview")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["preview_type"] == "text"

    def test_preview_nonexistent_404(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        resp = client.get(f"/api/sessions/{session_id}/workspace/files/no_id/preview")
        assert resp.status_code == 404


class TestSearchAPI:
    """测试 GET /api/sessions/{sid}/workspace/files?q= 搜索。"""

    def test_search_with_query(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        resp = client.get(f"/api/sessions/{session_id}/workspace/files?q=test")
        assert resp.status_code == 200
        files = resp.json()["data"]["files"]
        assert len(files) == 1
        assert files[0]["name"] == "test.csv"

    def test_search_no_match(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        resp = client.get(f"/api/sessions/{session_id}/workspace/files?q=不存在")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["files"]) == 0

    def test_search_without_query_returns_all(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        resp = client.get(f"/api/sessions/{session_id}/workspace/files")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["files"]) >= 1


class TestBatchDownloadAPI:
    """测试 POST /api/sessions/{sid}/workspace/batch-download。"""

    def test_batch_download_zip_success(self, client: TestClient):
        resp = client.post("/api/sessions")
        session_id = resp.json()["data"]["session_id"]
        manager = WorkspaceManager(session_id)
        note = manager.save_text_note("批量下载内容", "batch_note.md")

        download = client.post(
            f"/api/sessions/{session_id}/workspace/batch-download",
            json={"file_ids": [note["id"]]},
        )
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
            names = zf.namelist()
            assert "batch_note.md" in names
            assert zf.read("batch_note.md").decode("utf-8") == "批量下载内容"

    def test_batch_download_empty_file_ids_400(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        download = client.post(
            f"/api/sessions/{session_id}/workspace/batch-download",
            json={"file_ids": []},
        )
        assert download.status_code == 400

    def test_batch_download_missing_files_404(self, client: TestClient):
        session_id, _ = _create_session_and_upload(client)
        download = client.post(
            f"/api/sessions/{session_id}/workspace/batch-download",
            json={"file_ids": ["no_such_file"]},
        )
        assert download.status_code == 404
