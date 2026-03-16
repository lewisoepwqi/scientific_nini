"""差异分析子检验类型识别模块。

基于关键词映射表将差异分析意图细化为具体检验类型，
识别结果注入 tool_hints 首位，减少 LLM 额外对话轮次。
"""

from __future__ import annotations

# 子检验类型 → 关键词列表（首个命中即返回）
_SUBTYPE_MAP: dict[str, list[str]] = {
    "paired_t_test": ["配对t检验", "重复测量", "前后对比", "paired", "配对样本"],
    "independent_t_test": ["独立样本", "两组比较", "独立t检验", "两独立样本"],
    "one_way_anova": ["单因素方差", "one-way anova", "多组比较", "三组及以上"],
    "mann_whitney": ["mann-whitney", "Mann-Whitney", "秩和检验", "非参数两样本"],
    "kruskal_wallis": ["kruskal", "Kruskal-Wallis", "非参数多组"],
}


def get_difference_subtype(query: str) -> str | None:
    """识别差异分析的具体子检验类型。

    Args:
        query: 用户输入的查询字符串

    Returns:
        子类型标识符（如 "paired_t_test"），或 None（无法识别）
    """
    if not query:
        return None

    query_lower = query.lower()
    for subtype, keywords in _SUBTYPE_MAP.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                return subtype
    return None
