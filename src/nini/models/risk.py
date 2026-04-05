"""风险分级与输出等级模型。

定义 RiskLevel、TrustLevel、OutputLevel 枚举及相关常量与工具函数，
为 Agent 运行时的输出标注、风险判定和人工复核触发提供统一框架。
"""

from __future__ import annotations

from enum import Enum

# ---- 枚举定义 ----


class RiskLevel(str, Enum):
    """风险等级。按对研究结果、合规或用户决策的潜在影响分级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrustLevel(str, Enum):
    """信任等级。表示当前能力或上下文的可信度，决定输出等级上限。"""

    T1 = "t1"  # 草稿级——框架性引导，工具链尚不完整
    T2 = "t2"  # 可审阅级——方法与来源较完整，适合人工审阅
    T3 = "t3"  # 可复核级——结构化产物达到导出标准，仍需人工终审


class OutputLevel(str, Enum):
    """输出等级。明确「能生成」与「可信可用」的边界。"""

    O1 = "o1"  # 建议级——方向性意见，仅供参考
    O2 = "o2"  # 草稿级——可编辑初稿，结构较完整
    O3 = "o3"  # 可审阅级——方法与来源信息较完整，适合人工审阅
    O4 = "o4"  # 可导出级——结构化产物达到导出标准


class ResearchPhase(str, Enum):
    """研究阶段。表示科研全流程的八大阶段。"""

    TOPIC_SELECTION = "topic_selection"  # 选题
    LITERATURE_REVIEW = "literature_review"  # 文献调研
    EXPERIMENT_DESIGN = "experiment_design"  # 实验设计
    DATA_COLLECTION = "data_collection"  # 数据采集
    DATA_ANALYSIS = "data_analysis"  # 数据分析
    PAPER_WRITING = "paper_writing"  # 论文写作
    SUBMISSION = "submission"  # 投稿发表
    DISSEMINATION = "dissemination"  # 传播转化


# ---- 枚举元数据 ----


RISK_LEVEL_META: dict[RiskLevel, dict[str, str]] = {
    RiskLevel.LOW: {
        "name": "低",
        "definition": "错误主要影响表达和效率，不直接影响研究判断",
        "example": "结构整理、格式适配、通用写作辅助",
    },
    RiskLevel.MEDIUM: {
        "name": "中",
        "definition": "错误会影响草稿质量或资料完整性",
        "example": "文献归纳、引用整理、综述结构",
    },
    RiskLevel.HIGH: {
        "name": "高",
        "definition": "错误会影响研究方法、统计判断或投稿策略",
        "example": "样本量估计、统计推断解释、审稿回复",
    },
    RiskLevel.CRITICAL: {
        "name": "极高",
        "definition": "错误可能影响患者安全、伦理合规或重大研究结论",
        "example": "临床建议、伦理判断、因果主张背书",
    },
}

OUTPUT_LEVEL_META: dict[OutputLevel, dict[str, str]] = {
    OutputLevel.O1: {
        "name": "建议级",
        "definition": "方向性意见，仅供参考",
        "user_expectation": "需要用户独立判断",
    },
    OutputLevel.O2: {
        "name": "草稿级",
        "definition": "可编辑初稿，结构较完整",
        "user_expectation": "需要用户修改和补充",
    },
    OutputLevel.O3: {
        "name": "可审阅级",
        "definition": "方法与来源信息较完整，适合人工审阅",
        "user_expectation": "需要专业人员复核",
    },
    OutputLevel.O4: {
        "name": "可导出级",
        "definition": "结构化产物达到导出标准",
        "user_expectation": "仍需人工终审，不代表免复核",
    },
}


# ---- Trust-ceiling 映射 ----


TRUST_CEILING_MAP: dict[TrustLevel, list[OutputLevel]] = {
    TrustLevel.T1: [OutputLevel.O1, OutputLevel.O2],
    TrustLevel.T2: [OutputLevel.O1, OutputLevel.O2, OutputLevel.O3],
    TrustLevel.T3: [OutputLevel.O1, OutputLevel.O2, OutputLevel.O3, OutputLevel.O4],
}


# ---- 强制人工复核场景 ----


MANDATORY_REVIEW_SCENARIOS: list[str] = [
    "样本量计算与关键参数推荐",
    "研究方案定稿",
    "统计结论的最终解释",
    "投稿回复与审稿意见处理",
    "期刊适配与投稿建议",
    "临床解释与伦理相关建议",
    "即将进入最终摘要、导出文档或外部发送材料的内容",
]


# ---- 禁止性规则 ----


PROHIBITED_BEHAVIORS: list[str] = [
    '在无新鲜外部来源时，输出"近 X 年研究进展综述"式强结论',
    "在无权威数据库支撑时，输出强推荐式投稿期刊建议",
    "在无证据支持时，把推测性内容写入最终摘要或结论段落",
    "把草稿级输出伪装成已验证结论",
    "在证据不足时给出确定性结论",
    "在离线模式下伪装输出高时效外部事实",
    "自动跳过人工复核门继续生成最终结论",
    "将低可信度输出提升为高可信度而不提示依据",
]


# ---- 工具函数 ----


def validate_output_level(trust: TrustLevel, output: OutputLevel) -> bool:
    """校验输出等级是否在信任等级的 ceiling 范围内。

    Args:
        trust: 当前信任等级
        output: 拟标注的输出等级

    Returns:
        True 表示合法，False 表示超出上限
    """
    return output in TRUST_CEILING_MAP[trust]


def requires_human_review(risk_level: RiskLevel, scenario_tags: list[str]) -> bool:
    """判定是否需要触发人工复核。

    当风险等级为高或极高，或 scenario_tags 命中强制复核场景列表时返回 True。
    若对风险级别存在争议，应按更高等级处理（调用方责任）。

    Args:
        risk_level: 当前风险等级
        scenario_tags: 场景标签列表，与 MANDATORY_REVIEW_SCENARIOS 中的描述匹配

    Returns:
        True 表示需要人工复核
    """
    if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return True
    return any(tag in MANDATORY_REVIEW_SCENARIOS for tag in scenario_tags)
