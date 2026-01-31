"""
AI 建议服务。
"""
from typing import Any, Dict, List


def _ensure_list(value: Any) -> List[str]:
    """确保返回字符串列表。"""
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


class AISuggestionService:
    """AI 建议服务（占位实现）。"""

    async def generate_suggestions(self, summary: Dict[str, Any] | None) -> Dict[str, List[str]]:
        """生成结构化建议。"""
        _ = summary
        return {
            "cleaning": ["检查缺失值与异常值"],
            "statistics": ["建议进行描述性统计"],
            "chart_recommendations": ["推荐散点图或箱线图"],
            "notes": ["注意样本量对显著性检验的影响"],
        }


ai_suggestion_service = AISuggestionService()
