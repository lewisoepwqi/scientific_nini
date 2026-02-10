"""图片分析技能：支持从图片中提取数据和图表信息。"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from openai import AsyncOpenAI

from nini.agent.session import Session
from nini.config import settings
from nini.skills.base import Skill, SkillResult


class ImageAnalysisSkill(Skill):
    """图片分析技能，支持从图片中提取数据和图表信息。"""

    _chart_types = [
        "scatter",
        "line",
        "bar",
        "box",
        "violin",
        "histogram",
        "heatmap",
        "pie",
        "unknown",
    ]

    _output_formats = ["dataframe", "csv", "json", "text"]

    def __init__(self) -> None:
        """初始化图片分析技能。"""
        self._client: AsyncOpenAI | None = None
        self._vision_available: bool | None = None  # None 表示未检测

    @property
    def name(self) -> str:
        return "image_analysis"

    @property
    def description(self) -> str:
        return (
            "从图片中提取数据或分析图表。"
            "支持识别图表类型、提取数据点、解析表格数据。"
            "可处理散点图、折线图、柱状图、箱线图、小提琴图、直方图、热力图等。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "图片 URL（支持 http/https）",
                },
                "image_path": {
                    "type": "string",
                    "description": "本地图片文件路径",
                },
                "image_data": {
                    "type": "string",
                    "description": "base64 编码的图片数据",
                },
                "extract_data": {
                    "type": "boolean",
                    "description": "是否提取数据（表格或图表数据）",
                    "default": False,
                },
                "extract_chart_info": {
                    "type": "boolean",
                    "description": "是否提取图表信息（类型、标题、坐标轴等）",
                    "default": False,
                },
                "save_as_dataset": {
                    "type": "string",
                    "description": "将提取的数据保存为指定名称的数据集",
                },
                "output_format": {
                    "type": "string",
                    "enum": self._output_formats,
                    "description": "输出格式",
                    "default": "dataframe",
                },
                "output_dataset_name": {
                    "type": "string",
                    "description": "输出数据集名称（已废弃，使用 save_as_dataset）",
                },
            },
            "required": [],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行图片分析。"""
        # 获取图片来源
        try:
            image_source = await self._get_image_source(session, kwargs)
        except ValueError as exc:
            return SkillResult(
                success=False,
                message=str(exc),
            )

        if image_source is None:
            return SkillResult(
                success=False,
                message="请提供图片 URL、本地路径或上传文件",
            )

        extract_data = kwargs.get("extract_data", False)
        extract_chart_info = kwargs.get("extract_chart_info", False)
        save_as_dataset = kwargs.get("save_as_dataset") or kwargs.get("output_dataset_name")
        output_format = kwargs.get("output_format", "dataframe")

        # 如果没有指定任何提取选项，默认进行图表信息提取
        if not extract_data and not extract_chart_info:
            extract_chart_info = True

        result_data: dict[str, Any] = {}

        try:
            if extract_chart_info:
                chart_info = await self._extract_chart_info(image_source)
                result_data.update(chart_info)

            if extract_data:
                extracted_data = await self._extract_data(image_source)
                result_data["extracted_data"] = extracted_data

                # 保存为数据集
                if save_as_dataset and extracted_data:
                    df = self._data_to_dataframe(extracted_data)
                    if df is not None and not df.empty:
                        session.datasets[save_as_dataset] = df
                        result_data["dataset_name"] = save_as_dataset
                        result_data["dataset_rows"] = len(df)
                        result_data["dataset_columns"] = list(df.columns)

            # 格式化输出
            formatted_output = self._format_output(result_data, output_format)

            return SkillResult(
                success=True,
                message=self._build_success_message(result_data, extract_chart_info, extract_data),
                data=result_data,
                has_dataframe=bool(save_as_dataset and save_as_dataset in session.datasets),
                dataframe_preview=(
                    session.datasets[save_as_dataset].head().to_dict("records")
                    if save_as_dataset and save_as_dataset in session.datasets
                    else None
                ),
            )

        except Exception as exc:
            return SkillResult(
                success=False,
                message=f"图片分析失败: {exc}",
            )

    async def _get_image_source(self, session: Session, kwargs: dict[str, Any]) -> dict[str, Any] | None:
        """获取图片来源信息。"""
        # 1. 优先使用 image_data（base64 编码）
        image_data = kwargs.get("image_data")
        if image_data:
            return {"type": "base64", "data": image_data}

        # 2. 使用 image_url
        image_url = kwargs.get("image_url")
        if image_url:
            # 下载图片并转换为 base64
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(image_url)
                    response.raise_for_status()
                    image_bytes = response.content
                    base64_data = base64.b64encode(image_bytes).decode("utf-8")
                    # 检测图片类型
                    media_type = self._detect_media_type(image_url, image_bytes)
                    return {
                        "type": "base64",
                        "data": base64_data,
                        "media_type": media_type,
                    }
            except httpx.HTTPStatusError as exc:
                raise ValueError(f"无法下载图片 (HTTP {exc.response.status_code}): {exc}") from exc
            except Exception as exc:
                raise ValueError(f"无法下载图片: {exc}") from exc

        # 3. 使用 image_path
        image_path = kwargs.get("image_path")
        if image_path:
            path = Path(image_path)
            if not path.exists():
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
            image_bytes = path.read_bytes()
            base64_data = base64.b64encode(image_bytes).decode("utf-8")
            media_type = self._detect_media_type(str(path), image_bytes)
            return {
                "type": "base64",
                "data": base64_data,
                "media_type": media_type,
            }

        # 4. 检查会话中的上传文件
        if hasattr(session, "uploaded_files") and session.uploaded_files:
            # 获取第一个上传的图片文件
            for filename, filepath in session.uploaded_files.items():
                if self._is_image_file(filename):
                    path = Path(filepath)
                    if path.exists():
                        image_bytes = path.read_bytes()
                        base64_data = base64.b64encode(image_bytes).decode("utf-8")
                        media_type = self._detect_media_type(filename, image_bytes)
                        return {
                            "type": "base64",
                            "data": base64_data,
                            "media_type": media_type,
                            "source_file": filename,
                        }

        return None

    def _detect_media_type(self, filename_or_url: str, image_bytes: bytes) -> str:
        """检测图片的媒体类型。"""
        # 从文件扩展名判断
        ext = Path(filename_or_url).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        if ext in mime_map:
            return mime_map[ext]

        # 从 magic bytes 判断
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if image_bytes[:2] == b"\xff\xd8":
            return "image/jpeg"
        if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            return "image/webp"

        # 默认返回 png
        return "image/png"

    def _is_image_file(self, filename: str) -> bool:
        """判断是否为图片文件。"""
        ext = Path(filename).suffix.lower()
        return ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

    async def _extract_chart_info(self, image_source: dict[str, Any]) -> dict[str, Any]:
        """提取图表信息。"""
        if not self._is_vision_available():
            return {
                "chart_type": "unknown",
                "error": "视觉模型不可用，请配置 OpenAI API Key",
            }

        try:
            prompt = (
                "请分析这张图片中的图表。"
                "请识别：\n"
                "1. 图表类型（散点图/折线图/柱状图/箱线图/小提琴图/直方图/热力图/饼图）\n"
                "2. 图表标题（如果有）\n"
                "3. X 轴标签和单位\n"
                "4. Y 轴标签和单位\n"
                "5. 图例说明（如果有）\n"
                "6. 数据系列数量和名称\n\n"
                "请以 JSON 格式返回："
                '{"chart_type": "...", "title": "...", "x_axis": {"label": "...", "unit": "..."}, '
                '"y_axis": {"label": "...", "unit": "..."}, "legends": [...], "series_count": N}'
            )

            response = await self._call_vision_model(image_source, prompt)
            return self._parse_json_response(response, default={"chart_type": "unknown"})

        except Exception as exc:
            return {
                "chart_type": "unknown",
                "error": str(exc),
            }

    async def _extract_data(self, image_source: dict[str, Any]) -> dict[str, Any]:
        """提取数据（表格或图表数据）。"""
        if not self._is_vision_available():
            return {
                "error": "视觉模型不可用，请配置 OpenAI API Key",
            }

        try:
            prompt = (
                "请从这张图片中提取数据。"
                "如果是表格，请返回表格的行和列数据。"
                "如果是图表，请尝试估算数据点的坐标值。\n\n"
                "请以 JSON 格式返回数据："
                '{"type": "table|chart", "columns": [...], "data": [[...], [...]]} '
                '或者 {"type": "chart", "series": [{"name": "...", "x": [...], "y": [...]}]}'
            )

            response = await self._call_vision_model(image_source, prompt)
            return self._parse_json_response(response, default={})

        except Exception as exc:
            return {
                "error": str(exc),
            }

    async def _call_vision_model(self, image_source: dict[str, Any], prompt: str) -> str:
        """调用视觉模型。"""
        if not self._client:
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("未配置 OpenAI API Key")
            self._client = AsyncOpenAI(api_key=api_key)

        base64_data = image_source["data"]
        media_type = image_source.get("media_type", "image/png")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{base64_data}",
                        },
                    },
                ],
            }
        ]

        response = await self._client.chat.completions.create(
            model="gpt-4o" or "gpt-4-vision-preview",
            messages=messages,
            max_tokens=2048,
        )

        return response.choices[0].message.content or ""

    def _parse_json_response(self, response: str, default: Any = None) -> Any:
        """解析 JSON 响应。"""
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 代码块
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            # 尝试提取花括号内容
            brace_match = re.search(r"\{.*\}", response, re.DOTALL)
            if brace_match:
                try:
                    return json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    pass
            return default

    def _data_to_dataframe(self, data: dict[str, Any]) -> pd.DataFrame | None:
        """将提取的数据转换为 DataFrame。"""
        try:
            if "error" in data:
                return None

            # 表格类型数据
            if data.get("type") == "table" and "columns" in data and "data" in data:
                return pd.DataFrame(data["data"], columns=data["columns"])

            # 图表类型数据（序列格式）
            if data.get("type") == "chart" and "series" in data:
                series_list = data["series"]
                if not series_list:
                    return None

                # 如果只有一个系列
                if len(series_list) == 1:
                    series = series_list[0]
                    if "x" in series and "y" in series:
                        return pd.DataFrame({series.get("name", "value"): series["y"]}, index=series["x"])

                # 多个系列：转换为长格式
                rows = []
                for series in series_list:
                    name = series.get("name", "series")
                    x_values = series.get("x", [])
                    y_values = series.get("y", [])
                    for x, y in zip(x_values, y_values):
                        rows.append({"series": name, "x": x, "y": y})
                return pd.DataFrame(rows)

            # 兼容其他格式
            if "data" in data and isinstance(data["data"], list):
                return pd.DataFrame(data["data"])

            return None

        except Exception:
            return None

    def _format_output(self, data: dict[str, Any], output_format: str) -> str:
        """格式化输出。"""
        if output_format == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)
        if output_format == "csv":
            df = self._data_to_dataframe(data.get("extracted_data", {}))
            if df is not None:
                return df.to_csv(index=False)
            return ""
        if output_format == "text":
            return str(data)
        # dataframe 格式返回字典
        return data

    def _build_success_message(
        self,
        data: dict[str, Any],
        extracted_chart: bool,
        extracted_data: bool,
    ) -> str:
        """构建成功消息。"""
        parts = []

        if extracted_chart:
            chart_type = data.get("chart_type", "unknown")
            if chart_type != "unknown":
                parts.append(f"识别为 {chart_type}")

        if extracted_data:
            dataset_name = data.get("dataset_name")
            if dataset_name:
                rows = data.get("dataset_rows", 0)
                parts.append(f"已保存数据集 '{dataset_name}' ({rows} 行)")

        if "error" in data:
            parts.append(f"警告: {data['error']}")

        return "图片分析完成" + (". " + ", ".join(parts) if parts else ".")

    def _is_vision_available(self) -> bool:
        """检测视觉模型是否可用。"""
        if self._vision_available is not None:
            return self._vision_available

        self._vision_available = bool(settings.openai_api_key)
        return self._vision_available
