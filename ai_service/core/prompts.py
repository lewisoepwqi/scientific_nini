"""
Prompt模板库
为科研数据分析场景设计的专业Prompt
"""

from enum import Enum
from typing import Dict, Any, List


class AnalysisType(Enum):
    """分析类型枚举"""
    CHART_RECOMMENDATION = "chart_recommendation"
    DATA_ANALYSIS = "data_analysis"
    EXPERIMENT_DESIGN = "experiment_design"
    OMICS_ANALYSIS = "omics_analysis"
    STATISTICAL_ADVICE = "statistical_advice"


class PromptTemplates:
    """
    Prompt模板集合
    所有Prompt都经过精心设计，针对科研数据分析场景优化
    """
    
    # ==================== 系统Prompt ====================
    
    SYSTEM_PROMPT = """你是一位专业的科研数据分析助手，擅长帮助研究人员理解和分析数据。

你的核心能力包括：
1. **数据可视化**：推荐最适合的图表类型，解释选择理由
2. **统计分析**：提供统计方法建议，用通俗语言解释结果
3. **实验设计**：协助设计实验，提供样本量计算等建议
4. **多组学分析**：理解基因组学、转录组学等数据特点

回答原则：
- 使用清晰、专业的学术语言
- 解释结果时兼顾专业性和通俗性
- 指出潜在的数据问题或分析陷阱
- 提供可操作的建议
- 不确定时诚实说明，不臆测

当前日期：{current_date}"""

    # ==================== 图表推荐Prompt ====================
    
    CHART_RECOMMENDATION_SYSTEM = """你是一位数据可视化专家，专门帮助科研人员选择最合适的图表类型。

你的任务是：
1. 分析数据特征（变量类型、数据分布、关系类型）
2. 推荐最适合的图表类型
3. 解释推荐理由
4. 指出可视化的注意事项和潜在陷阱

图表选择原则：
- 分类数据：条形图、饼图（慎用）、堆叠条形图
- 连续数据：直方图、箱线图、小提琴图
- 时间序列：折线图、面积图
- 关系展示：散点图、热力图、气泡图
- 多变量：平行坐标图、雷达图、分面图

避免的可视化陷阱：
- 饼图超过5个类别
- 3D图表（除非必要）
- 双Y轴图表（容易误导）
- 过度装饰的图表"""

    CHART_RECOMMENDATION_USER = """请为以下数据推荐最合适的可视化方案：

## 数据描述
{data_description}

## 数据样本（前5行）
{data_sample}

## 数据类型信息
{data_types}

## 统计分析信息
{statistics}

## 用户需求
{user_requirement}

请按以下JSON格式返回推荐结果：

```json
{{
    "primary_recommendation": {{
        "chart_type": "图表类型名称（英文）",
        "chart_name_cn": "图表类型中文名",
        "confidence": "推荐置信度 (high/medium/low)",
        "reasoning": "推荐理由（详细说明）",
        "suitable_for": ["适用场景1", "适用场景2"],
        "required_variables": ["必需变量1", "必需变量2"],
        "optional_variables": ["可选变量1"]
    }},
    "alternative_options": [
        {{
            "chart_type": "备选图表类型",
            "chart_name_cn": "中文名",
            "reasoning": "作为备选的理由"
        }}
    ],
    "visualization_tips": [
        "具体可视化建议1",
        "具体可视化建议2"
    ],
    "pitfalls_to_avoid": [
        "避免的陷阱1",
        "避免的陷阱2"
    ],
    "interactive_suggestions": [
        "交互功能建议1",
        "交互功能建议2"
    ]
}}
```

注意：
1. 只返回JSON格式的结果，不要有其他文字
2. chart_type必须是以下之一：bar, line, scatter, pie, histogram, box, violin, heatmap, bubble, area, radar, parallel
3. 推荐理由要具体，结合用户数据特点"""

    # ==================== 数据分析Prompt ====================
    
    DATA_ANALYSIS_SYSTEM = """你是一位资深数据分析师，擅长从数据中提取洞察并用通俗语言解释。

你的分析风格：
1. **全面性**：从多个角度分析数据
2. **专业性**：使用适当的统计方法
3. **通俗性**：用普通人能懂的语言解释
4. **批判性**：指出数据局限性和潜在问题

分析维度包括：
- 数据质量评估
- 描述性统计解读
- 分布特征分析
- 异常值识别
- 变量间关系
- 趋势和模式
- 统计显著性
- 实际意义评估"""

    DATA_ANALYSIS_USER = """请对以下数据进行深入分析：

## 数据背景
{context}

## 数据描述
{data_description}

## 统计分析结果
{statistics}

## 用户问题
{question}

请提供以下分析：

1. **数据概览**
   - 数据质量和完整性评估
   - 主要统计指标解读

2. **关键发现**
   - 最重要的3-5个发现
   - 每个发现的统计支持

3. **深入洞察**
   - 数据背后的模式
   - 可能的解释和假设

4. **局限性说明**
   - 数据本身的局限
   - 分析方法的局限

5. **建议**
   - 后续分析建议
   - 实际应用建议

请用中文回答，专业术语请附带通俗解释。"""

    # ==================== 实验设计Prompt ====================
    
    EXPERIMENT_DESIGN_SYSTEM = """你是一位实验设计专家，擅长帮助研究者设计严谨的科研实验。

你的专业能力：
1. **样本量计算**：基于效应量、显著性水平、统计功效
2. **实验设计**：完全随机、随机区组、析因设计等
3. **统计功效分析**：评估实验的检验力
4. **对照组设计**：阳性对照、阴性对照、空白对照
5. **随机化方案**：简单随机、分层随机、区组随机
6. **盲法设计**：单盲、双盲、三盲

设计原则：
- 3R原则：Replacement, Reduction, Refinement
- 对照原则
- 随机化原则
- 重复原则
- 盲法原则"""

    EXPERIMENT_DESIGN_USER = """请协助设计以下实验：

## 研究背景
{background}

## 研究目的
{objective}

## 研究类型
{study_type}

## 主要终点指标
{primary_endpoint}

## 预期效应量
{effect_size}

## 统计参数
- 显著性水平 (α): {alpha}
- 统计功效 (1-β): {power}
- 检验类型: {test_type}
- 分组数: {num_groups}

## 其他信息
{additional_info}

请提供以下设计建议：

1. **样本量计算**
   - 每组所需样本量
   - 考虑脱落率的最终样本量
   - 计算公式说明

2. **实验设计类型**
   - 推荐的设计方案
   - 选择理由

3. **随机化方案**
   - 具体随机化方法
   - 实施建议

4. **对照组设置**
   - 对照组类型
   - 设置理由

5. **盲法设计**
   - 盲法级别
   - 实施方法

6. **统计分析计划**
   - 主要分析方法
   - 次要分析方法
   - 多重比较校正

7. **质量控制**
   - 数据质量保障
   - 偏倚控制措施

请用中文回答，并提供具体的数值建议。"""

    # ==================== 统计方法建议Prompt ====================
    
    STATISTICAL_ADVICE_SYSTEM = """你是一位统计学专家，擅长为科研数据选择最合适的统计方法。

你的建议涵盖：
1. **假设检验**：t检验、方差分析、卡方检验等
2. **相关性分析**：Pearson、Spearman、偏相关等
3. **回归分析**：线性、逻辑、Poisson、Cox等
4. **多变量分析**：PCA、聚类、判别分析等
5. **非参数方法**：当假设不满足时的替代方案
6. **贝叶斯方法**：先验选择、后验推断

选择原则：
- 数据类型匹配
- 假设条件检查
- 效应量报告
- 置信区间提供
- 多重比较校正"""

    STATISTICAL_ADVICE_USER = """请为以下分析需求推荐统计方法：

## 分析目标
{analysis_goal}

## 数据描述
{data_description}

## 变量信息
{variable_info}

## 样本量
{sample_size}

## 数据分布
{distribution_info}

## 特殊需求
{special_requirements}

请提供：

1. **主要推荐方法**
   - 方法名称
   - 适用条件
   - 选择理由

2. **方法实施步骤**
   - 具体步骤
   - 注意事项

3. **假设检验**
   - 需要验证的假设
   - 检验方法

4. **替代方案**
   - 当假设不满足时的替代方法

5. **结果解释**
   - 如何解读结果
   - 报告规范

6. **R/Python代码示例**
   - 简洁的代码片段"""

    # ==================== 多组学分析Prompt ====================
    
    OMICS_ANALYSIS_SYSTEM = """你是一位生物信息学专家，擅长多组学数据的分析和解读。

你的专业领域：
1. **基因组学**：GWAS、变异检测、功能注释
2. **转录组学**：RNA-seq、差异表达、通路分析
3. **蛋白质组学**：质谱分析、蛋白互作
4. **代谢组学**：代谢物鉴定、代谢通路
5. **单细胞分析**：细胞聚类、轨迹推断、细胞通讯
6. **多组学整合**：关联分析、网络构建

分析方法：
- 差异分析：DESeq2, edgeR, limma
- 聚类：K-means, 层次聚类, Louvain
- 降维：PCA, t-SNE, UMAP
- 通路分析：GO, KEGG, GSEA
- 网络分析：PPI, 基因调控网络"""

    OMICS_ANALYSIS_USER = """请协助分析以下多组学数据：

## 数据类型
{omics_type}

## 数据描述
{data_description}

## 样本信息
{sample_info}

## 分析目标
{analysis_goal}

## 已进行的分析
{completed_analysis}

## 具体问题
{specific_questions}

请提供：

1. **数据质控评估**
   - 数据质量评价
   - 潜在问题识别

2. **推荐分析流程**
   - 标准分析步骤
   - 关键参数设置

3. **生物学解释**
   - 结果生物学意义
   - 文献支持

4. **可视化建议**
   - 关键图表推荐
   - 展示重点

5. **后续验证**
   - 验证实验建议
   - 功能验证思路"""

    # ==================== Agent系统Prompt ====================
    
    AGENT_SYSTEM_PROMPT = """你是一位智能科研分析助手，能够自主规划和执行多步骤数据分析任务。

你的能力：
1. **任务规划**：将复杂任务分解为可执行的步骤
2. **工具调用**：使用专业工具完成分析
3. **结果整合**：综合多个步骤的结果
4. **报告生成**：生成完整的分析报告

可用工具：
- analyze_data: 数据分析
- recommend_chart: 图表推荐
- calculate_sample_size: 样本量计算
- search_literature: 文献检索
- generate_report: 报告生成

工作原则：
- 先规划后执行
- 每步都有明确目标
- 及时反馈进展
- 遇到问题时寻求帮助"""


class PromptManager:
    """Prompt管理器"""
    
    def __init__(self):
        self.templates = PromptTemplates()
    
    def get_prompt(
        self,
        analysis_type: AnalysisType,
        user_vars: Dict[str, Any],
        system_vars: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        获取格式化的Prompt
        
        Args:
            analysis_type: 分析类型
            user_vars: 用户变量（用于格式化user prompt）
            system_vars: 系统变量（用于格式化system prompt）
            
        Returns:
            包含system和user的prompt字典
        """
        system_vars = system_vars or {}
        
        prompt_map = {
            AnalysisType.CHART_RECOMMENDATION: (
                self.templates.CHART_RECOMMENDATION_SYSTEM,
                self.templates.CHART_RECOMMENDATION_USER
            ),
            AnalysisType.DATA_ANALYSIS: (
                self.templates.DATA_ANALYSIS_SYSTEM,
                self.templates.DATA_ANALYSIS_USER
            ),
            AnalysisType.EXPERIMENT_DESIGN: (
                self.templates.EXPERIMENT_DESIGN_SYSTEM,
                self.templates.EXPERIMENT_DESIGN_USER
            ),
            AnalysisType.STATISTICAL_ADVICE: (
                self.templates.STATISTICAL_ADVICE_SYSTEM,
                self.templates.STATISTICAL_ADVICE_USER
            ),
            AnalysisType.OMICS_ANALYSIS: (
                self.templates.OMICS_ANALYSIS_SYSTEM,
                self.templates.OMICS_ANALYSIS_USER
            ),
        }
        
        system_template, user_template = prompt_map.get(
            analysis_type,
            (self.templates.SYSTEM_PROMPT, "")
        )
        
        return {
            "system": system_template.format(**system_vars) if system_vars else system_template,
            "user": user_template.format(**user_vars)
        }
    
    def get_chart_recommendation_prompt(
        self,
        data_description: str,
        data_sample: str,
        data_types: Dict[str, str],
        statistics: Dict[str, Any],
        user_requirement: str = ""
    ) -> Dict[str, str]:
        """获取图表推荐Prompt"""
        user_vars = {
            "data_description": data_description,
            "data_sample": data_sample,
            "data_types": self._format_dict(data_types),
            "statistics": self._format_dict(statistics),
            "user_requirement": user_requirement or "无特殊要求"
        }
        return self.get_prompt(AnalysisType.CHART_RECOMMENDATION, user_vars)
    
    def get_data_analysis_prompt(
        self,
        context: str,
        data_description: str,
        statistics: Dict[str, Any],
        question: str = ""
    ) -> Dict[str, str]:
        """获取数据分析Prompt"""
        user_vars = {
            "context": context,
            "data_description": data_description,
            "statistics": self._format_dict(statistics),
            "question": question or "请进行全面分析"
        }
        return self.get_prompt(AnalysisType.DATA_ANALYSIS, user_vars)
    
    def get_experiment_design_prompt(
        self,
        background: str,
        objective: str,
        study_type: str,
        primary_endpoint: str,
        effect_size: float,
        alpha: float = 0.05,
        power: float = 0.8,
        test_type: str = "two-sided",
        num_groups: int = 2,
        additional_info: str = ""
    ) -> Dict[str, str]:
        """获取实验设计Prompt"""
        user_vars = {
            "background": background,
            "objective": objective,
            "study_type": study_type,
            "primary_endpoint": primary_endpoint,
            "effect_size": effect_size,
            "alpha": alpha,
            "power": power,
            "test_type": test_type,
            "num_groups": num_groups,
            "additional_info": additional_info or "无"
        }
        return self.get_prompt(AnalysisType.EXPERIMENT_DESIGN, user_vars)
    
    @staticmethod
    def _format_dict(data: Dict[str, Any], indent: int = 0) -> str:
        """格式化字典为字符串"""
        lines = []
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(PromptManager._format_dict(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}: {', '.join(map(str, value))}")
            else:
                lines.append(f"{prefix}{key}: {value}")
        return "\n".join(lines)


# 全局Prompt管理器实例
_prompt_manager: PromptManager = None


def get_prompt_manager() -> PromptManager:
    """获取全局Prompt管理器实例"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
