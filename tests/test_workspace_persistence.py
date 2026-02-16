"""会话工作空间持久化测试。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.workspace import WorkspaceManager
from tests.client_utils import LocalASGIClient


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
    client = LocalASGIClient(app)
    yield client
    client.close()
    session_manager._sessions.clear()


def test_workspace_dataset_persist_and_reload(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    assert create_resp.status_code == 200
    session_id = create_resp.json()["data"]["session_id"]

    upload_resp = client.post(
        "/api/upload",
        data={"session_id": session_id},
        files={"file": ("exp.csv", "a,b\n1,2\n3,4\n", "text/csv")},
    )
    assert upload_resp.status_code == 200
    dataset = upload_resp.json()["dataset"]
    dataset_id = dataset["id"]
    assert dataset["name"] == "exp.csv"

    list_resp = client.get(f"/api/sessions/{session_id}/datasets")
    assert list_resp.status_code == 200
    datasets = list_resp.json()["data"]["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["id"] == dataset_id
    assert datasets[0]["loaded"] is True

    files_resp = client.get(f"/api/sessions/{session_id}/workspace/files")
    assert files_resp.status_code == 200
    files = files_resp.json()["data"]["files"]
    assert any(item["kind"] == "dataset" and item["name"] == "exp.csv" for item in files)

    # 模拟重启：清空内存会话
    session_manager._sessions.clear()

    load_resp = client.post(f"/api/sessions/{session_id}/datasets/{dataset_id}/load")
    assert load_resp.status_code == 200
    assert load_resp.json()["data"]["dataset"]["loaded"] is True

    restored = session_manager.get_session(session_id)
    assert restored is not None
    assert "exp.csv" in restored.datasets
    assert len(restored.datasets["exp.csv"]) == 2


def test_workspace_messages_endpoint_returns_empty_for_workspace_only_session(
    client: LocalASGIClient,
) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    upload_resp = client.post(
        "/api/upload",
        data={"session_id": session_id},
        files={"file": ("sample.csv", "x,y\n5,6\n", "text/csv")},
    )
    assert upload_resp.status_code == 200

    session_manager._sessions.clear()

    messages_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert messages_resp.status_code == 200
    assert messages_resp.json()["data"]["messages"] == []


def test_workspace_save_text_and_download_note(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    save_resp = client.post(
        f"/api/sessions/{session_id}/workspace/save_text",
        json={
            "content": "# 分析代码\nprint('hello')\n",
            "filename": "analysis_snippet.md",
        },
    )
    assert save_resp.status_code == 200
    note = save_resp.json()["data"]["file"]
    assert note["name"] == "analysis_snippet.md"

    files_resp = client.get(f"/api/sessions/{session_id}/workspace/files")
    files = files_resp.json()["data"]["files"]
    note_item = next((item for item in files if item["kind"] == "note"), None)
    assert note_item is not None
    assert note_item["name"] == "analysis_snippet.md"

    download_resp = client.get(f"/api/workspace/{session_id}/notes/analysis_snippet.md")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-disposition"].startswith("attachment;")
    assert "print('hello')" in download_resp.text


def test_download_artifact_supports_double_encoded_filename(
    client: LocalASGIClient,
) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    manager = WorkspaceManager(session_id)
    manager.ensure_dirs()
    filename = "血压日变化分析.png"
    artifact_path = manager.artifacts_dir / filename
    artifact_path.write_bytes(b"PNG")

    encoded_once = quote(filename, safe="")
    encoded_twice = quote(encoded_once, safe="")
    download_resp = client.get(f"/api/artifacts/{session_id}/{encoded_twice}")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-disposition"].startswith("attachment;")
    assert download_resp.content == b"PNG"


def test_download_artifact_supports_inline_disposition(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    manager = WorkspaceManager(session_id)
    manager.ensure_dirs()
    filename = "report.pdf"
    artifact_path = manager.artifacts_dir / filename
    artifact_path.write_bytes(b"%PDF-1.4")

    inline_resp = client.get(f"/api/artifacts/{session_id}/{filename}?inline=1")
    assert inline_resp.status_code == 200
    assert inline_resp.headers["content-disposition"].startswith("inline;")
    assert inline_resp.content == b"%PDF-1.4"


def test_workspace_artifact_download_url_not_double_encoded() -> None:
    session = session_manager.create_session()
    manager = WorkspaceManager(session.id)
    manager.ensure_dirs()
    filename = "血压日变化分析.png"
    artifact_path = manager.artifacts_dir / filename
    artifact_path.write_bytes(b"PNG")
    record = manager.add_artifact_record(
        name=filename,
        artifact_type="chart",
        file_path=artifact_path,
        format_hint="png",
    )

    # rename_file 会把 artifact 的 download_url 设为已编码形式，这里用于模拟历史索引数据。
    renamed = manager.rename_file(str(record["id"]), filename)
    assert renamed is not None

    files = manager.list_workspace_files()
    artifact = next((item for item in files if item.get("id") == record["id"]), None)
    assert artifact is not None
    url = str(artifact["download_url"])
    assert "%E8%A1%80" in url
    assert "%25E8%A1%80" not in url
