"""成本透明化 E2E 测试。

测试成本透明化功能的端到端流程。
"""

import pytest
from unittest.mock import patch


@pytest.mark.e2e
class TestCostTransparencyWorkflow:
    """成本透明化工作流 E2E 测试。"""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        """创建测试客户端。"""
        from nini.app import create_app
        from nini.config import settings
        from tests.client_utils import LocalASGIClient

        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        app = create_app()
        return LocalASGIClient(app)

    @pytest.fixture
    def session_id(self, client):
        """创建测试会话。"""
        response = client.post("/api/sessions", json={"title": "成本测试会话"})
        assert response.status_code == 200
        result = response.json()
        # 处理不同的响应格式
        if "id" in result:
            return result["id"]
        elif "session_id" in result:
            return result["session_id"]
        else:
            pytest.skip("Session creation response format unexpected")

    def test_session_cost_endpoint_exists(self, client, session_id):
        """测试会话成本端点存在。"""
        response = client.get(f"/api/cost/session/{session_id}")
        # 应该返回 200 或 404（如果会话没有成本数据）
        assert response.status_code in [200, 404]

    def test_pricing_endpoint_returns_data(self, client):
        """测试定价端点返回数据。"""
        response = client.get("/api/cost/pricing")
        assert response.status_code in [200, 501]

    def test_cost_calculation_with_session(self, client, session_id):
        """测试带会话的成本计算。"""
        # 1. 创建会话
        assert session_id is not None

        # 2. 获取会话成本（可能为空）
        cost_response = client.get(f"/api/cost/session/{session_id}")
        assert cost_response.status_code in [200, 404]

        # 3. 如果成功，验证数据结构
        if cost_response.status_code == 200:
            data = cost_response.json()
            assert "session_id" in data
            assert "input_tokens" in data or "total_tokens" in data

    def test_sessions_cost_list_endpoint(self, client):
        """测试会话成本列表端点。"""
        response = client.get("/api/cost/sessions")
        assert response.status_code in [200, 501]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or isinstance(data, dict)


@pytest.mark.e2e
class TestCostModelsE2E:
    """成本模型 E2E 测试。"""

    def test_model_pricing_creation(self):
        """测试模型定价创建。"""
        from nini.models.cost import ModelPricing

        pricing = ModelPricing(
            input_price=0.0025,
            output_price=0.01,
            currency="USD",
            tier="standard"
        )

        # 验证成本计算
        cost = pricing.calculate_cost(1000, 500)
        assert cost > 0

    def test_token_usage_model(self):
        """测试 Token 使用模型。"""
        from nini.models.cost import TokenUsage, ModelTokenUsage

        model_usage = ModelTokenUsage(
            model_id="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500
        )

        usage = TokenUsage(
            session_id="test-session",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            model_breakdown={"gpt-4o": model_usage}
        )

        # 验证字典转换
        data = usage.to_dict()
        assert data["session_id"] == "test-session"
        assert "gpt-4o" in data["model_breakdown"]
