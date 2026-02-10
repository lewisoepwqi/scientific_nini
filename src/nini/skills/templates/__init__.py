"""复合技能模板模块。

将原子技能组合成"分析模板"，覆盖常见科研场景。
"""

from nini.skills.templates.complete_anova import CompleteANOVASkill
from nini.skills.templates.complete_comparison import CompleteComparisonSkill
from nini.skills.templates.correlation_analysis import CorrelationAnalysisSkill

__all__ = [
    "CompleteComparisonSkill",
    "CompleteANOVASkill",
    "CorrelationAnalysisSkill",
    "get_template",
]


def get_template(name: str):
    """获取模板的便捷函数。"""
    templates = {
        "complete_comparison": CompleteComparisonSkill,
        "complete_anova": CompleteANOVASkill,
        "correlation_analysis": CorrelationAnalysisSkill,
    }
    template_class = templates.get(name)
    if template_class:
        return template_class()
    return None
