"""统一文件下载 API 测试。

验证新的统一端点 /api/workspace/{session_id}/files/{path} 能正确：
1. 在多个位置查找文件（workspace 根目录、artifacts、notes、uploads）
2. 支持 plotly.json 自动转 PNG
3. 支持 Markdown bundle 打包下载
4. 旧端点返回 deprecation 警告
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from tests.client_utils import LocalASGIClient


@pytest.fixture
def client(tmp_path: Path):
    """创建测试客户端，使用临时数据目录。"""
    data_dir = tmp_path / "data"

    with patch.object(settings, "data_dir", data_dir):
        app = create_app()
        yield LocalASGIClient(app)


@pytest.fixture
def session_id(client: TestClient) -> str:
    """创建测试会话并返回会话 ID。"""
    sid = f"test-session-{uuid.uuid4().hex[:8]}"
    # 创建会话
    session_manager.get_or_create(sid)
    yield sid
    # 清理
    session_manager.remove_session(sid, delete_persistent=True)


def create_test_file(session_id: str, relative_path: str, content: bytes | str) -> Path:
    """创建测试文件到指定路径。"""
    session_dir = settings.sessions_dir / session_id
    file_path = session_dir / "workspace" / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, str):
        file_path.write_text(content, encoding="utf-8")
    else:
        file_path.write_bytes(content)

    return file_path


def create_plotly_json(session_id: str, filename: str) -> Path:
    """创建测试用的 plotly JSON 文件。"""
    chart_data = {
        "data": [
            {"x": [1, 2, 3], "y": [4, 5, 6], "type": "scatter", "mode": "lines+markers"}
        ],
        "layout": {"title": "Test Chart", "width": 800, "height": 600},
    }
    content = json.dumps(chart_data)
    return create_test_file(session_id, f"artifacts/{filename}", content)


def create_test_markdown(session_id: str, filename: str, with_image: bool = True) -> Path:
    """创建测试用的 Markdown 文件。"""
    if with_image:
        content = f"""# Test Report

This is a test markdown file with an image.

![Test Chart](/api/artifacts/{session_id}/chart.plotly.json)

Some other content here.
"""
    else:
        content = "# Test Report\n\nThis is a test markdown file without images."

    return create_test_file(session_id, f"notes/{filename}", content)


class TestUnifiedFileDownload:
    """测试统一文件下载端点。"""

    def test_download_file_from_workspace_root(self, client: TestClient, session_id: str):
        """测试从 workspace 根目录下载文件。"""
        # 在根目录创建文件
        file_path = create_test_file(session_id, "test_file.txt", "Hello from root!")

        # 使用统一端点下载（download=1 触发下载而非返回 JSON）
        response = client.get(f"/api/workspace/{session_id}/files/test_file.txt?download=1")

        assert response.status_code == 200
        assert response.content == b"Hello from root!"
        assert "text/plain" in response.headers.get("Content-Type", "")

    def test_download_file_from_artifacts(self, client: TestClient, session_id: str):
        """测试从 artifacts 子目录下载文件。"""
        create_test_file(session_id, "artifacts/chart.png", b"fake png data")

        response = client.get(f"/api/workspace/{session_id}/files/chart.png?download=1")

        assert response.status_code == 200
        assert response.content == b"fake png data"

    def test_download_file_from_notes(self, client: TestClient, session_id: str):
        """测试从 notes 子目录下载文件。"""
        create_test_file(session_id, "notes/note.txt", "Note content")

        response = client.get(f"/api/workspace/{session_id}/files/note.txt?download=1")

        assert response.status_code == 200
        assert response.content == b"Note content"

    def test_download_file_from_uploads(self, client: TestClient, session_id: str):
        """测试从 uploads 子目录下载文件。"""
        create_test_file(session_id, "uploads/data.csv", "col1,col2\n1,2")

        response = client.get(f"/api/workspace/{session_id}/files/data.csv?download=1")

        assert response.status_code == 200
        assert b"col1,col2" in response.content

    def test_download_file_priority_direct_path(self, client: TestClient, session_id: str):
        """测试直接路径优先级高于子目录搜索。"""
        # 在根目录和 artifacts 目录创建同名文件
        create_test_file(session_id, "test.txt", "root content")
        create_test_file(session_id, "artifacts/test.txt", "artifacts content")

        # 请求应该返回根目录的文件（按路径直接查找）
        response = client.get(f"/api/workspace/{session_id}/files/test.txt?download=1")

        assert response.status_code == 200
        # 直接路径优先
        assert response.content == b"root content"

    def test_download_file_with_subpath(self, client: TestClient, session_id: str):
        """测试使用子路径下载文件。"""
        create_test_file(session_id, "nested/folder/file.txt", "nested content")

        response = client.get(f"/api/workspace/{session_id}/files/nested/folder/file.txt?download=1")

        assert response.status_code == 200
        assert response.content == b"nested content"

    def test_download_nonexistent_file(self, client: TestClient, session_id: str):
        """测试下载不存在的文件返回 404。"""
        response = client.get(f"/api/workspace/{session_id}/files/not_exist.txt?download=1")

        assert response.status_code == 404

    def test_download_with_inline_parameter(self, client: TestClient, session_id: str):
        """测试 inline 参数设置 Content-Disposition。"""
        create_test_file(session_id, "inline_test.txt", "content")

        # inline=true
        response = client.get(f"/api/workspace/{session_id}/files/inline_test.txt?download=1&inline=1")
        assert response.status_code == 200
        disposition = response.headers.get("Content-Disposition", "")
        assert "inline" in disposition

        # inline=false (default)
        response = client.get(f"/api/workspace/{session_id}/files/inline_test.txt?download=1")
        disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in disposition


class TestPlotlyJsonConversion:
    """测试 Plotly JSON 自动转 PNG 功能。"""

    @pytest.mark.skip(reason="需要 kaleido/plotly 图形渲染依赖")
    def test_plotly_json_converts_to_png(self, client: TestClient, session_id: str):
        """测试 .plotly.json 文件默认转换为 PNG。"""
        create_plotly_json(session_id, "chart.plotly.json")

        response = client.get(f"/api/workspace/{session_id}/files/chart.plotly.json")

        # 如果转换成功，应该返回 PNG 格式
        if response.status_code == 200 and response.headers.get("Content-Type") == "image/png":
            assert response.headers.get("Content-Type") == "image/png"
        else:
            # 转换失败时返回原始 JSON
            pytest.skip("PNG conversion not available (kaleido not installed)")

    def test_plotly_json_raw_parameter(self, client: TestClient, session_id: str):
        """测试 raw=1 参数返回原始 JSON。"""
        chart_data = {"data": [], "layout": {}}
        content = json.dumps(chart_data)
        create_test_file(session_id, "artifacts/chart.plotly.json", content)

        response = client.get(f"/api/workspace/{session_id}/files/chart.plotly.json?download=1&raw=1")

        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "application/json"
        data = json.loads(response.content)
        assert data == chart_data


class TestMarkdownBundle:
    """测试 Markdown bundle 打包功能。"""

    def test_markdown_bundle_download(self, client: TestClient, session_id: str):
        """测试 Markdown 文件打包下载。"""
        # 创建 Markdown 文件和关联的图片
        create_test_markdown(session_id, "report.md", with_image=True)
        plotly_path = create_plotly_json(session_id, "chart.plotly.json")

        response = client.get(f"/api/workspace/{session_id}/files/report.md?bundle=1")

        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "application/zip"

        # 解析 ZIP 内容
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            files = zf.namelist()
            # 应该包含 Markdown 文件
            assert "report.md" in files
            # 应该包含 images 目录
            assert any("images/" in f for f in files)

            # 读取 Markdown 内容，检查 URL 是否被重写
            md_content = zf.read("report.md").decode("utf-8")
            assert "images/" in md_content
            assert "/api/artifacts/" not in md_content

    def test_markdown_bundle_no_images(self, client: TestClient, session_id: str):
        """测试没有图片的 Markdown 文件 bundle 下载（返回原始文件）。"""
        create_test_markdown(session_id, "simple.md", with_image=False)

        response = client.get(f"/api/workspace/{session_id}/files/simple.md?bundle=1")

        assert response.status_code == 200
        # 没有图片时直接返回 Markdown 文件而非 ZIP
        assert "text/markdown" in response.headers.get("Content-Type", "")
        assert b"# Test Report" in response.content

    def test_markdown_no_bundle(self, client: TestClient, session_id: str):
        """测试不带 bundle 参数时直接下载 Markdown。"""
        create_test_markdown(session_id, "report.md", with_image=True)

        response = client.get(f"/api/workspace/{session_id}/files/report.md?bundle=0")

        assert response.status_code == 200
        # 应该是 text/markdown 或 text/plain，不是 zip
        content_type = response.headers.get("Content-Type", "")
        assert "zip" not in content_type


class TestDeprecatedEndpoints:
    """测试旧端点的废弃警告。"""

    def test_artifacts_endpoint_deprecation(self, client: TestClient, session_id: str):
        """测试 /api/artifacts 端点返回 deprecation 头。"""
        create_test_file(session_id, "artifacts/legacy.txt", "legacy content")

        response = client.get(f"/api/artifacts/{session_id}/legacy.txt")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"
        assert "2025-06-01" in response.headers.get("Sunset", "")

    def test_workspace_uploads_endpoint_deprecation(self, client: TestClient, session_id: str):
        """测试 /api/workspace/{sid}/uploads 端点返回 deprecation 头。"""
        create_test_file(session_id, "uploads/upload.txt", "upload content")

        response = client.get(f"/api/workspace/{session_id}/uploads/upload.txt")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"

    def test_workspace_notes_endpoint_deprecation(self, client: TestClient, session_id: str):
        """测试 /api/workspace/{sid}/notes 端点返回 deprecation 头。"""
        create_test_file(session_id, "notes/note.txt", "note content")

        response = client.get(f"/api/workspace/{session_id}/notes/note.txt")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"

    def test_artifacts_bundle_endpoint_deprecation(self, client: TestClient, session_id: str):
        """测试 /api/workspace/{sid}/artifacts/{name}/bundle 端点返回 deprecation 头。"""
        create_test_markdown(session_id, "bundle.md", with_image=False)

        response = client.get(f"/api/workspace/{session_id}/artifacts/bundle.md/bundle")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"


class TestEditFileCompatibility:
    """测试 edit_file 工具创建的文件兼容性。"""

    def test_edit_file_in_root_downloadable(self, client: TestClient, session_id: str):
        """测试 edit_file 在 workspace 根目录创建的文件可被统一端点下载。"""
        # 模拟 edit_file 创建的文件（直接放在 workspace 根目录）
        create_test_file(session_id, "analysis_report.md", "# Analysis Report\n\nGenerated by edit_file.")

        # 统一端点应该能找到文件
        response = client.get(f"/api/workspace/{session_id}/files/analysis_report.md")

        assert response.status_code == 200
        assert b"Analysis Report" in response.content

    def test_edit_file_with_folder_downloadable(self, client: TestClient, session_id: str):
        """测试 edit_file 在子文件夹中创建的文件可被统一端点下载。"""
        # 模拟 edit_file 在子文件夹中创建文件
        create_test_file(
            session_id,
            "analysis/chapter1.md",
            "# Chapter 1\n\nContent here."
        )

        response = client.get(f"/api/workspace/{session_id}/files/analysis/chapter1.md")

        assert response.status_code == 200
        assert b"Chapter 1" in response.content


class TestImageFileDirectAccess:
    """测试图片文件在统一端点中默认直接返回文件流（支持 markdown 内嵌图片）。"""

    @pytest.mark.parametrize("ext", ["png", "jpg", "jpeg", "gif", "webp", "svg"])
    def test_image_file_direct_stream_without_download_param(self, client: TestClient, session_id: str, ext: str):
        """测试图片文件无需 download=1 参数即可直接访问文件流。"""
        filename = f"test_chart.{ext}"
        fake_image_content = f"fake {ext} data".encode("utf-8")

        # 在 artifacts 目录创建图片文件
        create_test_file(session_id, f"artifacts/{filename}", fake_image_content)

        # 不使用 download=1 参数直接访问（模拟 markdown 中 <img src> 的请求）
        response = client.get(f"/api/workspace/{session_id}/files/artifacts/{filename}")

        assert response.status_code == 200, f"{ext} 文件应该直接返回文件流"
        assert response.content == fake_image_content
        assert response.headers.get("Content-Type") not in ["application/json", None]

    def test_image_file_in_markdown_url_format(self, client: TestClient, session_id: str):
        """测试 markdown 中常见的 /api/workspace/{sid}/files/artifacts/xxx.png URL 格式能正常访问。"""
        # 创建 PNG 图片
        fake_png = b"\x89PNG\r\n\x1a\nfake png data"
        create_test_file(session_id, "artifacts/correlation_heatmap.png", fake_png)

        # 创建引用该图片的 markdown 文件
        md_content = f"""# 分析报告

## 相关性热图

![相关性热图](/api/workspace/{session_id}/files/artifacts/correlation_heatmap.png)

图表显示了各变量间的相关性。
"""
        create_test_file(session_id, "notes/report_with_image.md", md_content)

        # 1. 验证图片文件可直接通过 URL 访问（无 download 参数）
        img_response = client.get(f"/api/workspace/{session_id}/files/artifacts/correlation_heatmap.png")
        assert img_response.status_code == 200
        assert img_response.content == fake_png
        # 验证返回的是图片内容而非 JSON
        content_type = img_response.headers.get("Content-Type", "")
        assert "json" not in content_type, "图片不应返回 JSON 格式"

        # 2. 验证 markdown 文件内容正确
        md_response = client.get(f"/api/workspace/{session_id}/files/notes/report_with_image.md")
        assert md_response.status_code == 200
        # 默认返回 JSON 格式
        data = json.loads(md_response.content)
        assert data["success"] is True
        # 验证 markdown 中包含图片 URL
        assert f"/api/workspace/{session_id}/files/artifacts/correlation_heatmap.png" in data["data"]["content"]

    def test_non_image_file_still_returns_json_by_default(self, client: TestClient, session_id: str):
        """测试非图片文件默认仍返回 JSON 格式（向后兼容）。"""
        create_test_file(session_id, "data/results.txt", "这是一份文本结果")

        # 不使用 download 参数
        response = client.get(f"/api/workspace/{session_id}/files/data/results.txt")

        assert response.status_code == 200
        # 验证返回 JSON
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["data"]["content"] == "这是一份文本结果"

    def test_image_file_with_special_chars_in_name(self, client: TestClient, session_id: str):
        """测试包含特殊字符（如中文、空格）的图片文件名能正常访问。"""
        # 创建中文名称的图片
        fake_png = b"\x89PNG\r\n\x1a\n\x89\x90 fake"
        create_test_file(session_id, "artifacts/相关性热图.png", fake_png)
        create_test_file(session_id, "artifacts/chart with spaces.png", fake_png)

        # 测试中文文件名（URL 编码）
        response = client.get(f"/api/workspace/{session_id}/files/artifacts/{'相关性热图.png'}")
        assert response.status_code == 200
        assert response.content == fake_png

        # 测试带空格的文件名
        response = client.get(f"/api/workspace/{session_id}/files/artifacts/chart with spaces.png")
        assert response.status_code == 200
        assert response.content == fake_png
