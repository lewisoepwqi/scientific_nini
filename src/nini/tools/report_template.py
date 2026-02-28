"""发表级报告模板系统。

支持多种期刊风格的报告模板生成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ReportSection:
    """报告章节定义。"""

    id: str
    title: str
    description: str
    required: bool = False
    order: int = 0


@dataclass
class JournalTemplate:
    """期刊模板定义。"""

    id: str
    name: str
    description: str
    features: list[str]
    section_order: list[str]
    style_hints: dict[str, Any]


# 标准报告章节
STANDARD_SECTIONS: list[ReportSection] = [
    ReportSection("abstract", "摘要", "Abstract", True, 1),
    ReportSection("introduction", "引言", "Introduction", True, 2),
    ReportSection("methods", "方法", "Methods", True, 3),
    ReportSection("results", "结果", "Results", True, 4),
    ReportSection("discussion", "讨论", "Discussion", True, 5),
    ReportSection("conclusion", "结论", "Conclusion", False, 6),
    ReportSection("limitations", "局限性", "Limitations", False, 7),
    ReportSection("references", "参考文献", "References", False, 8),
]

# 期刊模板定义
JOURNAL_TEMPLATES: dict[str, JournalTemplate] = {
    "nature": JournalTemplate(
        id="nature",
        name="Nature",
        description="强调创新性和广泛影响",
        features=[
            "简短精炼的摘要（<150词）",
            "方法简述放在在线补充材料",
            "突出主要发现和创新点",
            "强调研究的广泛意义",
        ],
        section_order=["abstract", "introduction", "results", "discussion", "methods", "references"],
        style_hints={
            "abstract_max_words": 150,
            "emphasize_novelty": True,
            "brief_methods": True,
            "broad_implications": True,
        },
    ),
    "science": JournalTemplate(
        id="science",
        name="Science",
        description="跨学科综合期刊风格",
        features=[
            "清晰的问题陈述",
            "方法具有可重复性",
            "深入讨论研究的含义",
            "适合跨学科读者",
        ],
        section_order=["abstract", "introduction", "methods", "results", "discussion", "references"],
        style_hints={
            "abstract_max_words": 125,
            "interdisciplinary": True,
            "clear_problem_statement": True,
            "reproducible_methods": True,
        },
    ),
    "cell": JournalTemplate(
        id="cell",
        name="Cell",
        description="生命科学领域权威",
        features=[
            "详细的实验设计",
            "完整的结果展示",
            "深入的机制探讨",
            "丰富的补充材料",
        ],
        section_order=["abstract", "introduction", "results", "discussion", "methods", "references"],
        style_hints={
            "abstract_max_words": 150,
            "detailed_methods": True,
            "mechanistic_insights": True,
            "extensive_supplement": True,
        },
    ),
    "nejm": JournalTemplate(
        id="nejm",
        name="NEJM",
        description="临床医学顶刊风格",
        features=[
            "详细的纳入/排除标准",
            "严格的统计分析",
            "强调临床意义",
            "详细的安全性数据",
        ],
        section_order=["abstract", "introduction", "methods", "results", "discussion", "references"],
        style_hints={
            "abstract_max_words": 250,
            "structured_abstract": True,
            "clinical_focus": True,
            "safety_data": True,
            "patient_characteristics": True,
        },
    ),
    "lancet": JournalTemplate(
        id="lancet",
        name="Lancet",
        description="全球健康视角",
        features=[
            "强调公共卫生影响",
            "全球适用性讨论",
            "政策建议",
            "健康公平性",
        ],
        section_order=["abstract", "introduction", "methods", "results", "discussion", "references"],
        style_hints={
            "abstract_max_words": 300,
            "public_health_impact": True,
            "global_health": True,
            "policy_implications": True,
            "health_equity": True,
        },
    ),
    "apa": JournalTemplate(
        id="apa",
        name="APA",
        description="心理学标准格式",
        features=[
            "假设驱动的结构",
            "详细的方法描述",
            "结果与讨论分开",
            "强调统计严谨性",
        ],
        section_order=["abstract", "introduction", "methods", "results", "discussion", "references"],
        style_hints={
            "abstract_max_words": 250,
            "hypothesis_driven": True,
            "detailed_methods": True,
            "separate_results_discussion": True,
            "statistical_rigor": True,
        },
    ),
    "ieee": JournalTemplate(
        id="ieee",
        name="IEEE",
        description="工程技术领域",
        features=[
            "强调技术创新",
            "详细的算法/系统描述",
            "性能评估数据",
            "可复现的实现",
        ],
        section_order=["abstract", "introduction", "methods", "results", "discussion", "references"],
        style_hints={
            "abstract_max_words": 200,
            "technical_innovation": True,
            "algorithm_details": True,
            "performance_metrics": True,
            "reproducible_implementation": True,
        },
    ),
    "default": JournalTemplate(
        id="default",
        name="通用",
        description="标准学术报告格式",
        features=[
            "标准的 IMRAD 结构",
            "平衡的详细程度",
            "适合大多数期刊",
        ],
        section_order=["abstract", "introduction", "methods", "results", "discussion", "conclusion", "references"],
        style_hints={
            "abstract_max_words": 250,
            "standard_imrad": True,
        },
    ),
}


def get_template(template_id: str) -> JournalTemplate | None:
    """获取指定模板。"""
    return JOURNAL_TEMPLATES.get(template_id)


def list_templates() -> list[dict[str, Any]]:
    """列出所有可用模板。"""
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "features": t.features,
        }
        for t in JOURNAL_TEMPLATES.values()
    ]


def get_section_order(template_id: str, selected_sections: list[str] | None = None) -> list[str]:
    """获取章节的推荐顺序。
    
    Args:
        template_id: 模板ID
        selected_sections: 用户选择的章节（可选）
        
    Returns:
        按模板排序的章节列表
    """
    template = get_template(template_id)
    if not template:
        template = JOURNAL_TEMPLATES["default"]
    
    order = template.section_order
    
    if selected_sections:
        # 只返回用户选择且存在于模板顺序中的章节
        return [s for s in order if s in selected_sections]
    
    return order


def get_section_prompt(template_id: str, section_id: str, detail_level: str = "standard") -> str:
    """获取指定章节的生成提示。
    
    Args:
        template_id: 模板ID
        section_id: 章节ID
        detail_level: 详细程度（brief/standard/detailed）
        
    Returns:
        章节生成提示
    """
    template = get_template(template_id) or JOURNAL_TEMPLATES["default"]
    
    section_prompts = {
        "abstract": _get_abstract_prompt(template, detail_level),
        "introduction": _get_introduction_prompt(template, detail_level),
        "methods": _get_methods_prompt(template, detail_level),
        "results": _get_results_prompt(template, detail_level),
        "discussion": _get_discussion_prompt(template, detail_level),
        "conclusion": _get_conclusion_prompt(template, detail_level),
        "limitations": _get_limitations_prompt(template, detail_level),
        "references": _get_references_prompt(template, detail_level),
    }
    
    return section_prompts.get(section_id, "")


def _get_abstract_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取摘要生成提示。"""
    max_words = template.style_hints.get("abstract_max_words", 250)
    
    if template.id == "nature":
        return f"""生成 Nature 风格的摘要（不超过 {max_words} 词）：
- 第一句点明研究背景和创新点
- 简述主要发现，强调其重要性
- 说明研究的广泛意义
- 避免技术细节和统计数值
- 使用非专业人士也能理解的语言"""
    
    if template.id == "nejm":
        return f"""生成 NEJM 风格的结构化摘要（不超过 {max_words} 词）：
- Background: 研究背景和 rationale
- Methods: 研究设计、纳入排除标准、统计方法
- Results: 主要终点和关键次要终点，包括具体数值和置信区间
- Conclusions: 临床意义和安全性考量"""
    
    if detail_level == "brief":
        return f"生成简洁摘要（{max_words//2} 词左右）：概述背景、方法要点、主要结果和结论。"
    elif detail_level == "detailed":
        return f"生成详细摘要（{max_words} 词）：包含背景、目的、方法、结果、结论五个部分。"
    else:
        return f"生成标准摘要（{max_words} 词）：背景、方法、结果、结论。"


def _get_introduction_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取引言生成提示。"""
    if template.style_hints.get("hypothesis_driven"):
        return """生成假设驱动的引言：
- 从广泛背景逐步聚焦到具体问题
- 明确提出研究假设
- 简述研究目的和理论基础
- 结尾预告主要发现"""
    
    return """生成标准引言：
- 研究背景和意义
- 现有研究的不足
- 本研究的目的和贡献
- 简述主要发现"""


def _get_methods_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取方法生成提示。"""
    if template.style_hints.get("brief_methods"):
        return """生成简洁的方法描述：
- 仅描述核心方法
- 详细方法放在补充材料
- 说明统计软件版本和主要参数"""
    
    if template.style_hints.get("clinical_focus"):
        return """生成详细的临床方法：
- 研究设计和试验注册信息
- 纳入/排除标准
- 样本量计算依据
- 干预措施细节
- 终点指标定义
- 统计分析方法（包括缺失值处理）
- 伦理审批和知情同意"""
    
    return """生成标准方法描述：
- 数据来源和收集方法
- 实验设计
- 统计分析方法（包括软件版本）
- 显著性水平设定
- 多重比较校正方法"""


def _get_results_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取结果生成提示。"""
    if detail_level == "brief":
        return """生成简洁的结果描述：
- 仅报告主要发现
- 包含关键统计量（p值、效应量）
- 避免重复图表中的详细数据"""
    
    return """生成完整的结果描述：
- 按逻辑顺序呈现发现
- 报告主要和次要终点
- 包含统计量和置信区间
- 提及图表编号
- 描述效应大小和临床/实际意义"""


def _get_discussion_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取讨论生成提示。"""
    hints = []
    
    if template.style_hints.get("broad_implications"):
        hints.append("强调研究发现的广泛意义")
    
    if template.style_hints.get("mechanistic_insights"):
        hints.append("深入探讨机制")
    
    if template.style_hints.get("clinical_focus"):
        hints.append("讨论临床意义和实际应用")
    
    if template.style_hints.get("public_health_impact"):
        hints.append("评估公共卫生影响和政策建议")
    
    base_prompt = """生成讨论：
- 主要发现的总结和解释
- 与现有文献的比较
- 研究的意义（理论/实践/临床）
"""
    
    if hints:
        base_prompt += "\n特别关注点：\n- " + "\n- ".join(hints)
    
    return base_prompt


def _get_conclusion_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取结论生成提示。"""
    return """生成结论：
- 简明总结主要发现
- 强调核心贡献
- 提出实践建议
- 展望未来研究方向"""


def _get_limitations_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取局限性生成提示。"""
    return """生成局限性分析：
- 研究设计和方法的局限
- 样本量和代表性的限制
- 因果推断的限制
- 其他潜在偏倚来源
- 如何影响结果解释"""


def _get_references_prompt(template: JournalTemplate, detail_level: str) -> str:
    """获取参考文献生成提示。"""
    return """生成参考文献列表：
- 按出现顺序编号
- 包含作者、标题、期刊、年份、卷期、页码
- 遵循期刊格式要求"""
