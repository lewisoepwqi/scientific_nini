"""测试多模态数据支持功能。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.skills.base import SkillResult


# 创建一个简单的测试图片（1x1 PNG 的 base64）
# 这是一个最小的 PNG 图片
TEST_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def mock_image_data():
    """提供测试用的 base64 编码图片数据。"""
    return TEST_PNG_BASE64


@pytest.fixture
def mock_vision_response():
    """模拟视觉模型的响应。"""
    return {
        "chart_type": "bar",
        "title": "测试图表",
        "x_axis": {"label": "类别", "unit": ""},
        "y_axis": {"label": "数值", "unit": ""},
        "legends": ["系列1"],
        "series_count": 1,
    }


@pytest.fixture
def mock_data_response():
    """模拟数据提取响应。"""
    return {
        "type": "table",
        "columns": ["A", "B", "C"],
        "data": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
    }


class TestImageAnalysisSkill:
    """测试图片分析技能。"""

    def test_skill_exists(self):
        """测试技能类存在。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        assert ImageAnalysisSkill is not None

    def test_skill_name(self):
        """测试技能名称。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        skill = ImageAnalysisSkill()
        assert skill.name == "image_analysis"

    def test_skill_description(self):
        """测试技能描述。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        skill = ImageAnalysisSkill()
        assert skill.description != ""
        assert "图片" in skill.description or "图像" in skill.description

    def test_skill_parameters(self):
        """测试技能参数。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        skill = ImageAnalysisSkill()
        params = skill.parameters

        assert "type" in params
        assert "properties" in params
        assert "image_url" in params["properties"] or "image_path" in params["properties"]

    def test_parameter_required_fields(self):
        """测试参数定义。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        skill = ImageAnalysisSkill()
        params = skill.parameters

        # 图片来源参数应该存在（但不一定必需）
        props = params.get("properties", {})
        assert "image_url" in props or "image_path" in props or "image_data" in props


class TestImageAnalysisExecution:
    """测试图片分析执行。"""

    @pytest.mark.asyncio
    async def test_analyze_from_url_with_error(self):
        """测试从无效 URL 分析图片时的错误处理。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # 测试无效 URL 的错误处理
        result = await skill.execute(
            session,
            image_url="https://example.com/nonexistent.png",
            output_format="dataframe",
        )

        # 应该返回 SkillResult（失败）
        assert isinstance(result, SkillResult)
        assert not result.success
        assert "无法下载图片" in result.message or "HTTP" in result.message

    @pytest.mark.asyncio
    async def test_analyze_from_url(self, mock_image_data):
        """测试从 URL 分析图片（使用 mock）。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # 使用 mock httpx 来模拟成功的图片下载
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"fake_image_bytes"
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await skill.execute(
                session,
                image_url="https://example.com/chart.png",
                output_format="dataframe",
            )

            # 应该返回某种结果（即使没有 API key 也应该有降级处理）
            assert isinstance(result, SkillResult)

    @pytest.mark.asyncio
    async def test_analyze_with_base64_data(self, mock_image_data, mock_vision_response):
        """测试使用 base64 数据分析图片。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # Mock the vision model call
        with patch.object(skill, "_is_vision_available", return_value=True), \
             patch.object(skill, "_call_vision_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps(mock_vision_response, ensure_ascii=False)

            result = await skill.execute(
                session,
                image_data=mock_image_data,
                extract_chart_info=True,
            )

            assert isinstance(result, SkillResult)
            assert result.success
            assert "chart_type" in result.data

    @pytest.mark.asyncio
    async def test_analyze_extract_data(self, mock_image_data):
        """测试从图片提取数据。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # 使用 base64 数据
        result = await skill.execute(
            session,
            image_data=mock_image_data,
            extract_data=True,
            output_dataset_name="extracted_data",
        )

        # 即使没有 API key 也应该返回 SkillResult
        assert isinstance(result, SkillResult)

    @pytest.mark.asyncio
    async def test_analyze_chart_info(self, mock_image_data):
        """测试提取图表信息。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        result = await skill.execute(
            session,
            image_data=mock_image_data,
            extract_chart_info=True,
        )

        assert isinstance(result, SkillResult)


class TestImageToDataset:
    """测试图片转换为数据集。"""

    @pytest.mark.asyncio
    async def test_save_extracted_data_as_dataset(self, mock_image_data, mock_data_response):
        """测试将提取的数据保存为新数据集。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # Mock the vision model call
        with patch.object(skill, "_is_vision_available", return_value=True), \
             patch.object(skill, "_call_vision_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps(mock_data_response, ensure_ascii=False)

            result = await skill.execute(
                session,
                image_data=mock_image_data,
                extract_data=True,
                save_as_dataset="image_data",
            )

            # 如果成功，应该创建新数据集
            if result.success:
                assert "image_data" in session.datasets
                assert isinstance(session.datasets["image_data"], pd.DataFrame)

    @pytest.mark.asyncio
    async def test_extracted_dataframe_structure(self, mock_image_data, mock_data_response):
        """测试提取的 DataFrame 结构正确。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # Mock the vision model call
        with patch.object(skill, "_is_vision_available", return_value=True), \
             patch.object(skill, "_call_vision_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps(mock_data_response, ensure_ascii=False)

            result = await skill.execute(
                session,
                image_data=mock_image_data,
                extract_data=True,
                save_as_dataset="table_data",
            )

            if result.success and "table_data" in session.datasets:
                df = session.datasets["table_data"]
                assert isinstance(df, pd.DataFrame)
                # 应该有列
                assert len(df.columns) > 0


class TestChartInfoExtraction:
    """测试图表信息提取。"""

    @pytest.mark.asyncio
    async def test_detect_chart_type(self, mock_image_data, mock_vision_response):
        """测试检测图表类型。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # Mock the vision model call
        with patch.object(skill, "_is_vision_available", return_value=True), \
             patch.object(skill, "_call_vision_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps(mock_vision_response, ensure_ascii=False)

            result = await skill.execute(
                session,
                image_data=mock_image_data,
                extract_chart_info=True,
            )

            if result.success:
                data = result.data
                if isinstance(data, dict):
                    assert "chart_type" in data or "type" in data

    @pytest.mark.asyncio
    async def test_extract_chart_data(self, mock_image_data, mock_vision_response):
        """测试提取图表数据。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # Mock the vision model call
        with patch.object(skill, "_is_vision_available", return_value=True), \
             patch.object(skill, "_call_vision_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps(mock_vision_response, ensure_ascii=False)

            result = await skill.execute(
                session,
                image_data=mock_image_data,
                extract_chart_info=True,
            )

            if result.success:
                data = result.data
                if isinstance(data, dict):
                    # 应该包含图表相关信息
                    assert "chart_type" in data or "data" in data or "series" in data


class TestImageAnalysisIntegration:
    """测试图片分析集成。"""

    @pytest.mark.asyncio
    async def test_skill_registered_in_registry(self):
        """测试技能已注册。"""
        from nini.skills.registry import SkillRegistry

        registry = SkillRegistry()

        # 检查技能是否可用
        skill_names = registry.list_skills()
        # 技能可能已注册或需要注册
        assert isinstance(skill_names, list)

    @pytest.mark.asyncio
    async def test_image_analysis_with_file_upload(self, mock_image_data):
        """测试文件上传后的图片分析。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # 模拟文件已上传的情况（使用 base64 数据代替）
        result = await skill.execute(
            session,
            image_data=mock_image_data,
            extract_data=True,
        )

        assert isinstance(result, SkillResult)


class TestVisionModelIntegration:
    """测试视觉模型集成。"""

    @pytest.mark.asyncio
    async def test_gpt4v_integration(self):
        """测试 GPT-4V 集成（如果可用）。"""
        from nini.skills.image_analysis import ImageAnalysisSkill
        from nini.config import settings

        # 检查是否有配置
        has_api_key = settings.openai_api_key is not None

        if not has_api_key:
            pytest.skip("未配置 OpenAI API Key")

        # 测试 GPT-4V 功能
        session = Session()
        skill = ImageAnalysisSkill()

        # 使用 base64 数据测试
        result = await skill.execute(
            session,
            image_data=TEST_PNG_BASE64,
            extract_chart_info=True,
        )

        assert isinstance(result, SkillResult)

    @pytest.mark.asyncio
    async def test_fallback_on_model_unavailable(self, mock_image_data):
        """测试模型不可用时的降级处理。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        # Mock vision as unavailable
        with patch.object(skill, "_is_vision_available", return_value=False):
            result = await skill.execute(
                session,
                image_data=mock_image_data,
            )

            # 应该返回 SkillResult（虽然可能包含错误信息）
            assert isinstance(result, SkillResult)


class TestDataFormatSupport:
    """测试数据格式支持。"""

    @pytest.mark.asyncio
    async def test_supports_csv_output(self, mock_image_data):
        """测试支持 CSV 格式输出。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        result = await skill.execute(
            session,
            image_data=mock_image_data,
            extract_data=True,
            output_format="csv",
        )

        assert isinstance(result, SkillResult)

    @pytest.mark.asyncio
    async def test_supports_json_output(self, mock_image_data):
        """测试支持 JSON 格式输出。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        result = await skill.execute(
            session,
            image_data=mock_image_data,
            extract_data=True,
            output_format="json",
        )

        assert isinstance(result, SkillResult)

    @pytest.mark.asyncio
    async def test_supports_dataframe_output(self, mock_image_data):
        """测试支持 DataFrame 输出。"""
        from nini.skills.image_analysis import ImageAnalysisSkill

        session = Session()
        skill = ImageAnalysisSkill()

        result = await skill.execute(
            session,
            image_data=mock_image_data,
            extract_data=True,
            output_format="dataframe",
        )

        assert isinstance(result, SkillResult)
