"""会话工作空间持久化测试。"""

from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import quote
import zipfile

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

    list_resp = client.get(f"/api/datasets/{session_id}")
    assert list_resp.status_code == 200
    datasets = list_resp.json()["data"]["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["id"] == dataset_id
    assert datasets[0]["loaded"] is True

    files_resp = client.get(f"/api/workspace/{session_id}/files")
    assert files_resp.status_code == 200
    files = files_resp.json()["data"]["files"]
    assert any(item["kind"] == "dataset" and item["name"] == "exp.csv" for item in files)

    # 模拟重启：清空内存会话
    session_manager._sessions.clear()

    load_resp = client.post(f"/api/datasets/{session_id}/{dataset_id}/load")
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
        f"/api/workspace/{session_id}/files/notes/analysis_snippet.md",
        json={"content": "# 分析代码\nprint('hello')\n"},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["data"]["path"] == "notes/analysis_snippet.md"

    files_resp = client.get(f"/api/workspace/{session_id}/files")
    files = files_resp.json()["data"]["files"]
    note_item = next((item for item in files if item["kind"] == "note"), None)
    assert note_item is not None
    assert note_item["name"] == "analysis_snippet.md"

    download_resp = client.get(f"/api/workspace/{session_id}/notes/analysis_snippet.md")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-disposition"].startswith("attachment;")
    assert "print('hello')" in download_resp.text


def test_new_workspace_file_api_supports_tree_read_rename_delete(
    client: LocalASGIClient,
) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    save_resp = client.post(
        f"/api/workspace/{session_id}/files/notes/research.md",
        json={"content": "# 研究记录\n\n初始内容。\n"},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["data"]["path"] == "notes/research.md"

    read_resp = client.get(f"/api/workspace/{session_id}/files/notes/research.md")
    assert read_resp.status_code == 200
    assert "初始内容" in read_resp.json()["data"]["content"]

    tree_resp = client.get(f"/api/workspace/{session_id}/tree")
    assert tree_resp.status_code == 200
    tree = tree_resp.json()["data"]
    assert tree["type"] == "dir"
    notes_dir = next((item for item in tree["children"] if item["name"] == "notes"), None)
    assert notes_dir is not None
    assert any(child["path"] == "notes/research.md" for child in notes_dir["children"])

    rename_resp = client.post(
        f"/api/workspace/{session_id}/files/notes/research.md/rename",
        json={"name": "research-renamed.md"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["data"]["path"] == "notes/research-renamed.md"

    files_resp = client.get(f"/api/workspace/{session_id}/files")
    assert files_resp.status_code == 200
    file_names = {item["name"] for item in files_resp.json()["data"]["files"]}
    assert "research-renamed.md" in file_names
    assert "research.md" not in file_names

    delete_resp = client.delete(f"/api/workspace/{session_id}/files/notes/research-renamed.md")
    assert delete_resp.status_code == 200

    files_after_delete = client.get(f"/api/workspace/{session_id}/files").json()
    file_names_after_delete = {item["name"] for item in files_after_delete["data"]["files"]}
    assert "research-renamed.md" not in file_names_after_delete


def test_new_workspace_zip_download_supports_paths(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    client.post(
        f"/api/workspace/{session_id}/files/notes/a.md",
        json={"content": "# A\n"},
    )
    client.post(
        f"/api/workspace/{session_id}/files/notes/b.md",
        json={"content": "# B\n"},
    )

    zip_resp = client.post(
        f"/api/workspace/{session_id}/download-zip",
        json=["notes/a.md", "notes/b.md"],
    )
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-disposition"].startswith("attachment;")
    assert zip_resp.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(zip_resp.content), "r") as zf:
        names = set(zf.namelist())
        assert "a.md" in names
        assert "b.md" in names


def test_new_workspace_files_list_search_and_preview_support_paths(
    client: LocalASGIClient,
) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    save_resp = client.post(
        f"/api/workspace/{session_id}/files/notes/preview-target.md",
        json={"content": "# 预览目标\n\n用于新版接口测试。\n"},
    )
    assert save_resp.status_code == 200

    list_resp = client.get(f"/api/workspace/{session_id}/files")
    assert list_resp.status_code == 200
    files = list_resp.json()["data"]["files"]
    target = next((item for item in files if item["name"] == "preview-target.md"), None)
    assert target is not None
    assert target["path"] == "notes/preview-target.md"

    search_resp = client.get(
        f"/api/workspace/{session_id}/files?q={quote('preview-target', safe='')}"
    )
    assert search_resp.status_code == 200
    search_files = search_resp.json()["data"]["files"]
    assert len(search_files) == 1
    assert search_files[0]["path"] == "notes/preview-target.md"

    preview_resp = client.get(
        f"/api/workspace/{session_id}/files/notes/preview-target.md/preview"
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()["data"]
    assert preview["preview_type"] == "text"
    assert "用于新版接口测试" in preview["content"]


def test_new_workspace_dataset_path_api_syncs_session_and_index(
    client: LocalASGIClient,
) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    upload_resp = client.post(
        "/api/upload",
        data={"session_id": session_id},
        files={"file": ("exp.csv", "a,b\n1,2\n3,4\n", "text/csv")},
    )
    assert upload_resp.status_code == 200
    dataset = upload_resp.json()["dataset"]

    session = session_manager.get_session(session_id)
    assert session is not None
    assert "exp.csv" in session.datasets

    manager = WorkspaceManager(session_id)
    dataset_path = Path(dataset["file_path"]).relative_to(manager.workspace_dir).as_posix()

    rename_resp = client.post(
        f"/api/workspace/{session_id}/files/{dataset_path}/rename",
        json={"name": "renamed.csv"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["data"]["path"].endswith("renamed.csv")
    assert "renamed.csv" in session.datasets
    assert "exp.csv" not in session.datasets

    datasets_resp = client.get(f"/api/datasets/{session_id}")
    assert datasets_resp.status_code == 200
    dataset_names = {item["name"] for item in datasets_resp.json()["data"]["datasets"]}
    assert "renamed.csv" in dataset_names

    renamed_path = rename_resp.json()["data"]["path"]
    delete_resp = client.delete(f"/api/workspace/{session_id}/files/{renamed_path}")
    assert delete_resp.status_code == 200
    assert "renamed.csv" not in session.datasets

    files_resp = client.get(f"/api/workspace/{session_id}/files")
    files = files_resp.json()["data"]["files"]
    assert not any(item["kind"] == "dataset" and item["name"] == "renamed.csv" for item in files)


def test_new_workspace_folders_move_and_executions_routes(
    client: LocalASGIClient,
) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    create_folder_resp = client.post(
        f"/api/workspace/{session_id}/folders",
        json={"name": "分析结果", "parent": None},
    )
    assert create_folder_resp.status_code == 200
    folder = create_folder_resp.json()["data"]["folder"]

    save_resp = client.post(
        f"/api/workspace/{session_id}/files/notes/movable.md",
        json={"content": "# move\n"},
    )
    assert save_resp.status_code == 200

    move_resp = client.post(
        f"/api/workspace/{session_id}/files/notes/movable.md/move",
        json={"folder_id": folder["id"]},
    )
    assert move_resp.status_code == 200
    moved_file = move_resp.json()["data"]["file"]
    assert moved_file["folder"] == folder["id"]

    folders_resp = client.get(f"/api/workspace/{session_id}/folders")
    assert folders_resp.status_code == 200
    folders = folders_resp.json()["data"]["folders"]
    assert any(item["id"] == folder["id"] for item in folders)

    manager = WorkspaceManager(session_id)
    manager.save_code_execution(
        code="print('ok')",
        output="ok",
        status="success",
        intent="验证新版执行历史接口",
    )

    executions_resp = client.get(f"/api/workspace/{session_id}/executions")
    assert executions_resp.status_code == 200
    executions = executions_resp.json()["data"]["executions"]
    assert len(executions) == 1
    assert executions[0]["intent"] == "验证新版执行历史接口"


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


def test_download_plotly_artifact_supports_raw_json(client: LocalASGIClient) -> None:
    create_resp = client.post("/api/sessions")
    session_id = create_resp.json()["data"]["session_id"]

    manager = WorkspaceManager(session_id)
    manager.ensure_dirs()
    filename = "带 空格.plotly.json"
    artifact_path = manager.artifacts_dir / filename
    artifact_path.write_text('{"data":[{"type":"bar","x":["A"],"y":[1]}]}', encoding="utf-8")

    encoded = quote(filename, safe="")
    raw_resp = client.get(f"/api/artifacts/{session_id}/{encoded}?raw=1")
    assert raw_resp.status_code == 200
    assert raw_resp.headers["content-disposition"].startswith("attachment;")
    assert raw_resp.text == '{"data":[{"type":"bar","x":["A"],"y":[1]}]}'


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


def test_workspace_artifact_download_url_encodes_spaces() -> None:
    session = session_manager.create_session()
    manager = WorkspaceManager(session.id)
    manager.ensure_dirs()
    filename = "chart with 空格.plotly.json"
    artifact_path = manager.artifacts_dir / filename
    artifact_path.write_text("{}", encoding="utf-8")
    record = manager.add_artifact_record(
        name=filename,
        artifact_type="chart",
        file_path=artifact_path,
        format_hint="json",
    )

    url = str(record["download_url"])
    assert "/api/artifacts/" in url
    assert "%20" in url
    assert " " not in url


def test_workspace_artifact_record_upsert_by_path_and_identity() -> None:
    session = session_manager.create_session()
    manager = WorkspaceManager(session.id)
    manager.ensure_dirs()

    filename = "重复产物.py"
    artifact_path = manager.artifacts_dir / filename
    artifact_path.write_text("print('v1')\n", encoding="utf-8")

    first = manager.add_artifact_record(
        name=filename,
        artifact_type="code",
        file_path=artifact_path,
        format_hint="py",
    )
    second = manager.add_artifact_record(
        name=filename,
        artifact_type="code",
        file_path=artifact_path,
        format_hint="py",
    )

    # 同一路径重复写入应复用同一条记录（upsert），避免工作区列表重复。
    assert second["id"] == first["id"]
    artifacts = manager.list_artifacts()
    matched = [item for item in artifacts if item.get("path") == str(artifact_path)]
    assert len(matched) == 1

    files = manager.list_workspace_files()
    # list_workspace_files 不包含 path 字段，按名称统计重复项即可。
    same_name = [
        item for item in files if item.get("kind") == "artifact" and item.get("name") == filename
    ]
    assert len(same_name) == 1
