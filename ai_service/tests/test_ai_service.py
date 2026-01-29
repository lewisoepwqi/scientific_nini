"""
AI服务测试
使用 pytest 运行: pytest tests/test_ai_service.py -v
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

# 跳过需要真实API的测试
pytestmark = pytest.mark.skipif(
    not pytest.config.getoption("--run-api-tests", default=False),
    reason="需要真实API调用，使用 --run-api-tests 启用"
)


class TestLLMClient:
    """测试LLM客户端"""
    
    @pytest.fixture
    def mock_llm_client(self):
        """创建模拟的LLM客户端"""
        from ai_service.core.llm_client import LLMClient, LLMConfig
        
        config = LLMConfig(
            model="gpt-3.5-turbo",
            api_key="test_key"
        )
        client = LLMClient(config)
        
        # 模拟API调用
        client.client = Mock()
        
        return client
    
    @pytest.mark.asyncio
    async def test_chat_completion(self, mock_llm_client):
        """测试聊天完成"""
        # 模拟响应
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test response"))]
        mock_response.usage = Mock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        
        mock_llm_client.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        
        messages = [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Hello"}
        ]
        
        result = await mock_llm_client.chat_completion(messages)
        
        assert result["content"] == "Test response"
        assert result["usage"]["total_tokens"] == 150
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self, mock_llm_client):
        """测试重试机制"""
        from openai import RateLimitError
        
        # 前两次调用失败，第三次成功
        mock_llm_client.client.chat.completions.create = AsyncMock(
            side_effect=[
                RateLimitError("Rate limit exceeded"),
                RateLimitError("Rate limit exceeded"),
                Mock(
                    choices=[Mock(message=Mock(content="Success"))],
                    usage=Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
                )
            ]
        )
        
        messages = [{"role": "user", "content": "Test"}]
        
        result = await mock_llm_client.chat_completion(messages)
        
        assert result["content"] == "Success"
        assert mock_llm_client.client.chat.completions.create.call_count == 3


class TestPromptManager:
    """测试Prompt管理器"""
    
    @pytest.fixture
    def prompt_manager(self):
        from ai_service.core.prompts import PromptManager
        return PromptManager()
    
    def test_chart_recommendation_prompt(self, prompt_manager):
        """测试图表推荐Prompt"""
        prompts = prompt_manager.get_chart_recommendation_prompt(
            data_description="Test data",
            data_sample="col1,col2\n1,2\n3,4",
            data_types={"col1": "int", "col2": "float"},
            statistics={"row_count": 100},
            user_requirement="Compare groups"
        )
        
        assert "system" in prompts
        assert "user" in prompts
        assert "Test data" in prompts["user"]
        assert "Compare groups" in prompts["user"]
    
    def test_data_analysis_prompt(self, prompt_manager):
        """测试数据分析Prompt"""
        prompts = prompt_manager.get_data_analysis_prompt(
            context="Research context",
            data_description="Test data",
            statistics={"mean": 10, "std": 2},
            question="What does this mean?"
        )
        
        assert "system" in prompts
        assert "user" in prompts
        assert "Research context" in prompts["user"]
        assert "What does this mean?" in prompts["user"]


class TestAIAnalysisService:
    """测试AI分析服务"""
    
    @pytest.fixture
    def mock_service(self):
        """创建模拟的AI服务"""
        from ai_service.services.ai_analysis_service import AIAnalysisService
        
        service = AIAnalysisService()
        service.llm = Mock()
        
        return service
    
    @pytest.mark.asyncio
    async def test_recommend_chart(self, mock_service):
        """测试图表推荐"""
        # 模拟LLM响应
        mock_response = {
            "content": '''```json
            {
                "primary_recommendation": {
                    "chart_type": "bar",
                    "chart_name_cn": "条形图",
                    "confidence": "high",
                    "reasoning": "适合比较分类数据"
                },
                "alternative_options": [],
                "visualization_tips": [],
                "pitfalls_to_avoid": [],
                "interactive_suggestions": []
            }
            ```''',
            "cost_usd": 0.05,
            "usage": {"total_tokens": 500}
        }
        
        mock_service.llm.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await mock_service.recommend_chart(
            data_description="Test data",
            data_sample="A,B\n1,2",
            data_types={"A": "int"},
            statistics={},
            user_requirement=""
        )
        
        assert result["primary_recommendation"]["chart_type"] == "bar"
        assert result["cost_usd"] == 0.05
    
    @pytest.mark.asyncio
    async def test_analyze_data(self, mock_service):
        """测试数据分析"""
        mock_response = {
            "content": "This is an analysis result.",
            "cost_usd": 0.10,
            "usage": {"total_tokens": 1000}
        }
        
        mock_service.llm.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await mock_service.analyze_data(
            context="Test context",
            data_description="Test data",
            statistics={"mean": 10},
            question="Analyze this"
        )
        
        assert result["analysis"] == "This is an analysis result."
        assert result["cost_usd"] == 0.10


class TestEndpoints:
    """测试API端点"""
    
    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from fastapi.testclient import TestClient
        from ai_service.main import app
        
        return TestClient(app)
    
    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client):
        """测试根端点"""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "service" in response.json()


class TestCostTracking:
    """测试成本追踪"""
    
    def test_cost_calculation(self):
        """测试成本计算"""
        from ai_service.core.llm_client import CostInfo
        
        cost_info = CostInfo(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500
        )
        
        cost = cost_info.calculate_cost("gpt-4")
        
        # GPT-4: input $0.03/1K, output $0.06/1K
        expected = (1000/1000 * 0.03) + (500/1000 * 0.06)
        assert cost == expected
    
    def test_cost_summary(self):
        """测试成本摘要"""
        from ai_service.core.llm_client import LLMClient, LLMConfig
        
        config = LLMConfig(api_key="test")
        client = LLMClient(config)
        
        # 添加一些成本记录
        from ai_service.core.llm_client import CostInfo
        
        cost1 = CostInfo(input_tokens=1000, output_tokens=500, total_tokens=1500)
        cost1.calculate_cost("gpt-4")
        client.cost_history.append(cost1)
        client.total_cost += cost1.cost_usd
        client.total_calls += 1
        
        summary = client.get_cost_summary()
        
        assert summary["total_calls"] == 1
        assert summary["total_cost_usd"] > 0


# 集成测试（需要真实API）
@pytest.mark.integration
class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_chart_recommendation(self):
        """端到端图表推荐测试"""
        from ai_service import get_ai_service
        
        service = get_ai_service()
        
        result = await service.recommend_chart(
            data_description="Gene expression data with 100 samples",
            data_sample="Sample,GeneA,Group\nS1,2.5,Control\nS2,3.1,Treatment",
            data_types={"Sample": "string", "GeneA": "float", "Group": "categorical"},
            statistics={"row_count": 100, "column_count": 3},
            user_requirement="Compare gene expression between groups"
        )
        
        assert "primary_recommendation" in result
        assert "chart_type" in result["primary_recommendation"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
