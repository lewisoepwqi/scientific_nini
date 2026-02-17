"""复合技能模板模块。

将原子技能组合成"分析模板"，覆盖常见科研场景。
同时提供期刊样式模板（Nature, Science, Cell 等）的动态加载功能。
"""

from nini.tools.templates.complete_anova import CompleteANOVASkill
from nini.tools.templates.complete_comparison import CompleteComparisonSkill
from nini.tools.templates.correlation_analysis import CorrelationAnalysisSkill

# 导入期刊样式模板功能
from nini.tools.templates.journal_styles import (
    delete_custom_template,
    get_template_info,
    get_template_names,
    get_templates,
    reload_templates,
    save_custom_template,
    TEMPLATES,
)

__all__ = [
    # 复合技能类
    "CompleteComparisonSkill",
    "CompleteANOVASkill",
    "CorrelationAnalysisSkill",
    # 期刊模板函数
    "get_templates",
    "get_template_names",
    "get_template_info",
    "save_custom_template",
    "delete_custom_template",
    "reload_templates",
    "TEMPLATES",
]


def get_template(name: str):
    """获取模板的便捷函数。

    支持两种类型的模板：
    1. 复合技能模板（complete_comparison, complete_anova, correlation_analysis）
    2. 期刊样式模板（nature, science, cell, nejm, lancet, default）

    Args:
        name: 模板名称

    Returns:
        复合技能返回实例，期刊模板返回配置字典，不存在返回 None
    """
    # 首先检查复合技能模板
    if name == "complete_comparison":
        return CompleteComparisonSkill()
    if name == "complete_anova":
        return CompleteANOVASkill()
    if name == "correlation_analysis":
        return CorrelationAnalysisSkill()

    # 然后检查期刊样式模板
    from nini.tools.templates.journal_styles import get_template as get_journal_template

    journal_template = get_journal_template(name)
    # 如果返回的是默认模板且请求的不是 default，说明没找到
    if name != "default" and journal_template.get("name") == "默认模板":
        return None
    return journal_template
