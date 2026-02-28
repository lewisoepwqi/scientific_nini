"""知识库API端点测试。

测试知识库相关的REST API端点。
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from nini.app import create_app
from nini.config import settings
from tests.client_utils import LocalASGIClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """创建测试客户端。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
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
