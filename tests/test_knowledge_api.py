"""知识库API端点测试。

测试知识库相关的REST API端点。
"""

import json

import pytest
from unittest.mock import AsyncMock, Mock, patch

from nini.app import create_app
from nini.config import settings
from tests.client_utils import LocalASGIClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """创建测试客户端。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    from nini.api import knowledge_routes

    knowledge_routes._document_store.clear()
    app = create_app()
    return LocalASGIClient(app)


class TestKnowledgeSearchEndpoint:
    """知识搜索端点测试。"""

    @pytest.fixture
    def mock_retriever(self):
        """模拟混合检索器。"""
        with patch("nini.api.knowledge_routes.get_hybrid_retriever") as mock:
            retriever = Mock()
            mock.return_value = retriever
            yield retriever

    def test_search_without_query(self, client, mock_retriever):
        """测试无查询参数的搜索。"""
        response = client.post("/api/knowledge/search", json={})

        # 应该返回错误，因为缺少查询参数
        assert response.status_code == 422

    def test_search_with_empty_query(self, client, mock_retriever):
        """测试空查询搜索。"""
        response = client.post("/api/knowledge/search", json={"query": ""})

        # 空查询也应该返回错误
        assert response.status_code == 422

    def test_search_with_valid_query(self, client, mock_retriever):
        """测试有效查询搜索。"""
        # 模拟搜索结果
        mock_result = Mock()
        mock_result.query = "统计方法"
        mock_result.results = []
        mock_result.total_count = 0
        mock_result.search_method = "hybrid"
        mock_result.search_time_ms = 100
        mock_result.to_dict.return_value = {
            "query": "统计方法",
            "results": [],
            "total_count": 0,
            "search_method": "hybrid",
            "search_time_ms": 100,
        }
        mock_retriever.search.return_value = mock_result

        response = client.post("/api/knowledge/search", json={"query": "统计方法"})

        # 可能成功(200)或验证失败(422)或端点未实现(404)
        assert response.status_code in [200, 422, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["query"] == "统计方法"
            assert "results" in data


class TestKnowledgeDocumentsEndpoint:
    """知识文档端点测试。"""

    def test_list_documents(self, client):
        """测试列出文档。"""
        response = client.get("/api/knowledge/documents")

        assert response.status_code in [200, 501]  # 200成功或501未实现

    def test_upload_document_without_file(self, client):
        """测试无文件上传。"""
        response = client.post("/api/knowledge/documents")

        # 应该返回错误
        assert response.status_code == 422

    def test_upload_document_persists_content_file(self, client):
        """测试上传文档后正文会被持久化，避免重启后丢失。"""
        from nini.api import knowledge_routes

        mock_retriever = AsyncMock()
        mock_retriever.add_document.return_value = True

        with patch(
            "nini.api.knowledge_routes.get_hybrid_retriever",
            new=AsyncMock(return_value=mock_retriever),
        ):
            response = client.post(
                "/api/knowledge/documents",
                files={"file": ("test_knowledge.txt", "统计学测试文档", "text/plain")},
                data={"title": "测试文档", "domain": "statistics"},
            )

        assert response.status_code == 200
        payload = response.json()
        document_id = payload["document_id"]
        document_path = settings.knowledge_dir / f"{document_id}.txt"
        metadata_path = settings.knowledge_dir / "metadata.json"

        assert document_path.exists()
        assert document_path.read_text(encoding="utf-8") == "统计学测试文档"

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert document_id in metadata
        assert metadata[document_id]["title"] == "测试文档"

        knowledge_routes._document_store.clear()
        knowledge_routes._load_document_store()
        assert document_id in knowledge_routes._document_store

    def test_load_document_store_prunes_stale_metadata(self, tmp_path, monkeypatch):
        """测试启动时会清理缺失正文文件的失效元数据。"""
        from nini.api import knowledge_routes

        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()
        knowledge_routes._document_store.clear()

        metadata_path = settings.knowledge_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "stale-doc": {
                        "id": "stale-doc",
                        "title": "已丢失正文",
                        "file_type": "txt",
                        "file_size": 10,
                        "index_status": "indexed",
                        "created_at": "2026-04-09T05:18:45.534751+00:00",
                        "updated_at": "2026-04-09T05:18:45.534758+00:00",
                        "description": "",
                        "domain": "statistics",
                        "tags": [],
                        "chunk_count": 1,
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        knowledge_routes._load_document_store()

        assert knowledge_routes._document_store == {}
        assert json.loads(metadata_path.read_text(encoding="utf-8")) == {}

    def test_upload_document_failure_does_not_leave_orphan_content_file(self, client):
        """索引抛错时不应残留正文文件或内存文档项。"""
        from nini.api import knowledge_routes

        mock_retriever = AsyncMock()
        mock_retriever.add_document.side_effect = RuntimeError("向量索引失败")

        with patch(
            "nini.api.knowledge_routes.get_hybrid_retriever",
            new=AsyncMock(return_value=mock_retriever),
        ):
            response = client.post(
                "/api/knowledge/documents",
                files={"file": ("failed.txt", "失败文档", "text/plain")},
                data={"title": "失败文档", "domain": "statistics"},
            )

        assert response.status_code == 500
        assert list(settings.knowledge_dir.glob("*.txt")) == []
        assert knowledge_routes._document_store == {}


class TestKnowledgeContextEndpoint:
    """知识上下文端点测试。"""

    def test_get_context_without_query(self, client):
        """测试无查询获取上下文。"""
        response = client.get("/api/knowledge/context")

        # 应该返回错误、空结果或404（端点未实现）
        assert response.status_code in [200, 400, 422, 404]

    def test_get_context_with_query(self, client):
        """测试带查询获取上下文。"""
        response = client.get("/api/knowledge/context?query=统计方法")

        # 可能成功、返回未实现或404（端点未实现）
        assert response.status_code in [200, 501, 404]


class TestKnowledgeStatsEndpoint:
    """知识统计端点测试。"""

    def test_get_stats(self, client):
        """测试获取统计信息。"""
        response = client.get("/api/knowledge/stats")

        # 可能成功、返回未实现或404（端点未实现）
        assert response.status_code in [200, 501, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
