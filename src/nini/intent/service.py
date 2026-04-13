"""意图分析服务 — 规则版 v3，内置 Trie 优化、profile_boost 和子检验识别。

原 OptimizedIntentAnalyzer（optimized.py）、apply_boost（profile_booster.py）、
get_difference_subtype（subtypes.py）已合并至本模块。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

import yaml

from nini.config import _get_bundle_root
from nini.intent.base import IntentAnalysis, IntentCandidate, QueryType
from nini.models.user_profile import UserProfile

logger = logging.getLogger(__name__)
_lowconf_logger = logging.getLogger("nini.intent.lowconf")

# 闲聊识别正则（尽量宽泛覆盖短确认、问候、感谢）
_CASUAL_RE = re.compile(
    r"^(你好|hello|hi|嗨|谢谢|感谢|好的|明白|了解|知道了|收到|okay|ok|嗯|哦|啊|哈哈|"
    r"再见|bye|不用了|没事|没问题|可以|太好了|厉害|棒|继续|好)[\W]*$",
    re.IGNORECASE,
)
# 工具指令关键词
_COMMAND_RE = re.compile(r"保存|导出|下载|清除|重置|刷新|删除|移除|整理")

# 超出支持范围的意图识别正则——命中时跳过意图澄清，由 LLM 直接解释能力边界
# 覆盖：网络检索、文献搜索、新闻查询、实时数据等 Nini 不支持的功能
_OUT_OF_SCOPE_RE = re.compile(
    r"检索|搜索|搜一下|查一下|查找|查询最新|最新进展|最新消息|最新动态|"
    r"最新研究|发展近况|联网|上网|爬虫|爬取|爬网|browse|google|pubmed|"
    r"scholar|知网|web\s*search|internet|新闻|资讯|热点|头条|"
    r"机票|酒店预订|订餐|外卖|天气预报|股票行情|彩票|播放音乐|"
    r"讲笑话|导航路线|网购|快递查询|打车",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,}")
SLASH_SKILL_WITH_ARGS_RE = re.compile(
    r"(?<!\S)/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.+?))?(?=\s*/[A-Za-z]|\s*$)", re.DOTALL
)
_GENERIC_CHINESE_TERMS = {
    "数据",
    "分析",
    "结果",
    "研究",
    "生成",
    "比较",
    "报告",
    "图表",
    "工具",
    "方法",
}

# 通用中文停用词（Trie/倒排索引路径中使用）
_GENERIC_TERMS: set[str] = {
    "数据",
    "分析",
    "结果",
    "研究",
    "生成",
    "比较",
    "报告",
    "图表",
    "工具",
    "方法",
    "进行",
    "使用",
    "帮我",
    "请",
    "一下",
    "一个",
    "需要",
    "想要",
    "希望",
    "能",
    "可以",
}

# 科研意图同义词表 — 将自然语言表达映射到 capability 名称
# 以 optimized.py 版本为基准（更完整），保留 service.py 的独有条目
_SYNONYM_MAP: dict[str, list[str]] = {
    "difference_analysis": [
        "差异",
        "显著性",
        "t检验",
        "t_test",
        "anova",
        "方差分析",
        "对比",
        "比较差异",
        "两组差异",
        "多组差异",
        "组间差异",
        "显著差别",
        "差别",
        "对比分析",
        "均值比较",
        "mann_whitney",
        "kruskal",
        "非参数检验",
        "wilcoxon",
    ],
    "correlation_analysis": [
        "相关",
        "相关性",
        "关联",
        "pearson",
        "spearman",
        "kendall",
        "相关系数",
        "变量关系",
        "协变",
        "共变",
        "相互关系",
        "有没有联系",
        "有没有关系",
        "是否相关",
        "相关性分析",
    ],
    "regression_analysis": [
        "回归",
        "预测",
        "建模",
        "线性模型",
        "regression",
        "拟合",
        "回归方程",
        "自变量",
        "因变量",
        "预测模型",
        "逻辑回归",
        "多元回归",
        "逐步回归",
        "岭回归",
        "lasso",
    ],
    "data_exploration": [
        "探索",
        "概览",
        "描述性统计",
        "分布",
        "缺失值",
        "异常值",
        "数据质量",
        "数据特征",
        "看看数据",
        "了解数据",
        "数据情况",
        "描述统计",
        "基本统计",
        "数据概览",
        "探索性分析",
        "eda",
    ],
    "data_cleaning": [
        "清洗",
        "预处理",
        "处理缺失",
        "填充",
        "去重",
        "标准化",
        "归一化",
        "异常处理",
        "数据清理",
        "数据整理",
        "缺失值处理",
        "异常值处理",
        "数据转换",
        "特征工程",
    ],
    "visualization": [
        "可视化",
        "画图",
        "作图",
        "图形",
        "箱线图",
        "散点图",
        "柱状图",
        "热力图",
        "直方图",
        "折线图",
        "饼图",
        "chart",
        "plot",
        "graph",
        "画图展示",
        "绘制图表",
    ],
    "report_generation": [
        "报告",
        "报表",
        "汇总",
        "总结",
        "导出报告",
        "生成报告",
        "分析报告",
        "report",
        "summary",
        "word",
        "pdf",
    ],
    "article_draft": [
        "论文",
        "文章",
        "初稿",
        "manuscript",
        "publication",
        "科研论文",
        "学术论文",
        "撰写论文",
        "论文写作",
    ],
    "citation_management": [
        "引用格式",
        "参考文献",
        "文献引用",
        "引用管理",
        "bibliography",
        "APA格式",
        "MLA格式",
        "GB/T格式",
        "citation",
        "文献格式化",
        "引用规范",
    ],
    "peer_review": [
        "审稿意见",
        "同行评审",
        "评审意见",
        "回复审稿",
        "修改意见",
        "reviewer",
        "peer review",
        "审稿人",
        "回复审稿人",
        "reviewer comments",
        "意见回复",
    ],
    "research_planning": [
        "研究规划",
        "研究设计",
        "实验设计",
        "研究方案",
        "研究思路",
        "样本量",
        "样本量计算",
        "随机化",
        "研究框架",
        "research design",
        "实验方案",
    ],
}


def _load_synonym_map() -> dict[str, list[str]]:
    """加载外部同义词配置，失败时回退内置 `_SYNONYM_MAP`。

    配置文件路径：`<项目根>/config/intent_synonyms.yaml`
    顶层结构须为 dict，value 须为列表；非列表条目跳过。
    """
    config_path = _get_bundle_root() / "config" / "intent_synonyms.yaml"
    if not config_path.exists():
        logger.debug("未找到外部同义词配置，使用内置 _SYNONYM_MAP")
        return dict(_SYNONYM_MAP)
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("顶层结构须为 dict")
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as exc:
        logger.warning("加载同义词配置失败，回退内置: path=%s err=%s", config_path, exc)
        return dict(_SYNONYM_MAP)


# ============================================================================
# Trie 树结构（用于 capability 名称快速前缀匹配）
# ============================================================================


@dataclass
class TrieNode:
    """Trie 树节点。"""

    children: dict[str, "TrieNode"] = field(default_factory=dict)
    is_end: bool = False
    capability: str | None = None


# ============================================================================
# profile_boost — 用户画像意图加权（原 profile_booster.py）
# ============================================================================

_MAX_BOOST_DELTA = 3.0
_BOOST_FACTOR = 3.0

_CAPABILITY_METHOD_MAP: dict[str, list[str]] = {
    "difference_analysis": [
        "t_test",
        "anova",
        "mann_whitney",
        "kruskal_wallis",
        "paired_t_test",
        "independent_t_test",
        "one_way_anova",
    ],
    "correlation_analysis": ["pearson", "spearman", "kendall", "correlation"],
    "regression_analysis": [
        "linear_regression",
        "logistic_regression",
        "multiple_regression",
    ],
    "data_exploration": ["data_summary", "preview_data", "data_quality"],
    "data_cleaning": ["clean_data", "dataset_transform"],
    "visualization": ["create_chart", "export_chart"],
    "report_generation": ["generate_report", "export_report"],
    "article_draft": [],
    "citation_management": [],
    "peer_review": [],
    "research_planning": [],
}


def _compute_delta(capability_name: str, user_profile: UserProfile) -> float:
    """计算单个能力的画像加权分数。"""
    methods = _CAPABILITY_METHOD_MAP.get(capability_name, [])
    if not methods:
        return 0.0

    preferred_methods = user_profile.preferred_methods or {}
    weight_sum = sum(preferred_methods.get(method, 0.0) for method in methods)
    return min(weight_sum * _BOOST_FACTOR, _MAX_BOOST_DELTA)


def apply_boost(
    candidates: list[IntentCandidate], user_profile: UserProfile
) -> list[IntentCandidate]:
    """基于用户画像返回新的候选排序，不修改原对象。"""
    boosted = [
        replace(
            candidate,
            score=candidate.score + _compute_delta(candidate.name, user_profile),
        )
        for candidate in candidates
    ]
    return sorted(boosted, key=lambda item: item.score, reverse=True)


# ============================================================================
# subtypes — 差异分析子检验类型识别（原 subtypes.py）
# ============================================================================

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


# ============================================================================
# 辅助函数
# ============================================================================


def _extract_terms(*texts: str) -> list[str]:
    """提取稳定的中英文关键词。"""
    terms: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in _TOKEN_RE.findall(text or ""):
            term = match.strip().lower()
            if len(term) < 2:
                continue
            if term in _GENERIC_CHINESE_TERMS:
                continue
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def _normalize_required_tools(raw_tools: Any) -> list[str]:
    if not isinstance(raw_tools, list):
        return []
    normalized: list[str] = []
    for item in raw_tools:
        tool_name = str(item).strip()
        if tool_name:
            normalized.append(tool_name)
    return normalized


def _normalize_user_invocable(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata")
    raw_value = item.get("user_invocable")
    if raw_value is None and isinstance(metadata, dict):
        raw_value = metadata.get("user_invocable")
    return raw_value is not False


def _summarize_skill_item(item: dict[str, Any]) -> dict[str, Any]:
    """提炼前端可直接消费的 skill 摘要。"""
    metadata = item.get("metadata")
    allowed_tools = None
    if isinstance(metadata, dict):
        allowed_tools = metadata.get("allowed_tools")
    if allowed_tools is None:
        allowed_tools = item.get("allowed_tools")
    return {
        "name": str(item.get("name", "")).strip(),
        "description": str(item.get("description", "")).strip(),
        "category": str(item.get("category", "other")).strip() or "other",
        "research_domain": str(item.get("research_domain", "general")).strip() or "general",
        "difficulty_level": (
            str(item.get("difficulty_level", "intermediate")).strip() or "intermediate"
        ),
        "location": str(item.get("location", "")).strip(),
        "allowed_tools": _normalize_required_tools(allowed_tools),
    }


# ============================================================================
# IntentAnalyzer — 单一意图分析器，内置 Trie 优化 + profile_boost + 子检验识别
# ============================================================================


class IntentAnalyzer:
    """规则版意图分析器，内置 Trie 树、倒排索引、用户画像加权和子检验识别。

    原 OptimizedIntentAnalyzer 的全部能力已合并至此类。
    IntentAnalyzer 同时保留 skill 处理方法（rank_semantic_skills 等），
    OptimizedIntentAnalyzer 原本缺失这些方法。

    Attributes:
        _trie: 前缀树，用于 capability 名称快速匹配
        _inverted_index: 倒排索引，用于同义词快速查找
        _capabilities: 已加载的 capability 列表
        _initialized: 是否已完成索引初始化
        _synonym_map: 同义词表（优先从 YAML 加载）
    """

    # 数据分析类白名单：has_datasets=True 时仅对这些候选收紧阈值
    _DATA_ANALYSIS_WHITELIST: set[str] = {
        "difference_analysis",
        "correlation_analysis",
        "regression_analysis",
        "data_exploration",
        "data_cleaning",
    }

    def __init__(self) -> None:
        """初始化意图分析器，延迟构建 Trie 索引。"""
        self._trie = TrieNode()
        self._inverted_index: dict[str, set[str]] = {}
        self._capabilities: list[dict[str, Any]] = []
        self._initialized = False
        # 优先从 config/intent_synonyms.yaml 加载，失败时回退内置
        self._synonym_map: dict[str, list[str]] = _load_synonym_map()

    def initialize(self, capabilities: list[dict[str, Any]] | None = None) -> None:
        """初始化索引结构。

        Args:
            capabilities: capability 列表，如果为 None 则延迟初始化
        """
        if self._initialized:
            return

        if capabilities:
            self._capabilities = capabilities
            self._build_trie()
            self._build_inverted_index()
            self._initialized = True
            logger.info(
                "意图分析器初始化完成: %d capabilities, %d 索引项",
                len(self._capabilities),
                len(self._inverted_index),
            )

    def _build_trie(self) -> None:
        """构建 capability 名称前缀树。"""
        for cap in self._capabilities:
            name = str(cap.get("name", "")).strip()
            display_name = str(cap.get("display_name", "")).strip()

            # 索引 name
            if name:
                self._insert_trie(name.lower().replace("_", " "), name)

            # 索引 display_name
            if display_name:
                self._insert_trie(display_name.lower(), name)

    def _insert_trie(self, text: str, capability: str) -> None:
        """向 Trie 树插入文本。"""
        words = text.split()
        node = self._trie

        for word in words:
            if word not in node.children:
                node.children[word] = TrieNode()
            node = node.children[word]

        node.is_end = True
        node.capability = capability

    def _build_inverted_index(self) -> None:
        """构建同义词倒排索引。"""
        for cap_name, synonyms in self._synonym_map.items():
            for synonym in synonyms:
                synonym_lower = synonym.lower()
                if synonym_lower not in self._inverted_index:
                    self._inverted_index[synonym_lower] = set()
                self._inverted_index[synonym_lower].add(cap_name)

                # 注意：不对中文词拆单字建索引——单字匹配范围过宽，
                # 会导致"检索"中的"索"字误命中 data_exploration 等能力，
                # 产生不相关的澄清问题（如对"帮我检索文献"问"你想做数据探索还是回归分析"）。
                # 只索引完整词组，依赖 _synonym_match 的子串匹配覆盖变体。

    def _trie_match(self, message: str) -> dict[str, float]:
        """Trie 树前缀匹配。

        复杂度：O(n) n为消息长度
        """
        message_lower = message.lower()
        scores: dict[str, float] = {}

        # 检查每个位置开始的前缀
        words = message_lower.split()
        for i in range(len(words)):
            node = self._trie
            for j in range(i, min(i + 5, len(words))):  # 最多匹配5个词
                word = words[j]
                if word not in node.children:
                    break
                node = node.children[word]
                if node.is_end and node.capability:
                    # 完整匹配，高分
                    cap = node.capability
                    scores[cap] = max(scores.get(cap, 0), 10.0 - (j - i) * 2)

        return scores

    def _synonym_match(self, message: str) -> dict[str, float]:
        """同义词倒排索引匹配。

        复杂度：O(n) n为消息长度
        """
        message_lower = message.lower()
        # 去空格版本：处理"t 检验"与"t检验"之类的中英混合词汇（用户可能在字母和汉字间加空格）
        message_nospace = message_lower.replace(" ", "")
        scores: dict[str, float] = {}

        # 直接匹配（含去空格归一化匹配）
        for synonym, caps in self._inverted_index.items():
            synonym_nospace = synonym.replace(" ", "")
            if synonym in message_lower or synonym_nospace in message_nospace:
                for cap in caps:
                    # 根据同义词长度给予不同权重
                    weight = min(6.0, 2.0 + len(synonym) * 0.5)
                    scores[cap] = scores.get(cap, 0) + weight

        return scores

    def _keyword_match(self, message: str) -> dict[str, float]:
        """关键词提取匹配（基于 capability 描述和展示名称）。"""
        message_lower = message.lower()
        scores: dict[str, float] = {}

        for cap in self._capabilities:
            name = str(cap.get("name", "")).strip()
            display = str(cap.get("display_name", "")).strip()
            description = str(cap.get("description", "")).strip()

            score = 0.0

            # 关键词匹配
            text = f"{display} {description}".lower()
            words = set(text.split()) - _GENERIC_TERMS

            for word in words:
                if len(word) < 2:
                    continue
                if word in message_lower:
                    score += 1.5

            # 工具名称匹配
            tools = cap.get("required_tools", [])
            for tool in tools:
                if str(tool).lower() in message_lower:
                    score += 0.5

            if score > 0:
                scores[name] = scores.get(name, 0) + score

        return scores

    def _merge_and_rank(
        self,
        trie_matches: dict[str, float],
        synonym_matches: dict[str, float],
        keyword_matches: dict[str, float],
    ) -> list[IntentCandidate]:
        """融合多路匹配结果并排序。"""
        all_caps = (
            set(trie_matches.keys()) | set(synonym_matches.keys()) | set(keyword_matches.keys())
        )

        merged: dict[str, tuple[float, list[str]]] = {}
        for cap in all_caps:
            score = 0.0
            reasons: list[str] = []

            if cap in trie_matches:
                score += trie_matches[cap]
                reasons.append(f"名称匹配 +{trie_matches[cap]:.1f}")

            if cap in synonym_matches:
                score += synonym_matches[cap]
                reasons.append(f"同义词匹配 +{synonym_matches[cap]:.1f}")

            if cap in keyword_matches:
                score += keyword_matches[cap]
                reasons.append(f"关键词匹配 +{keyword_matches[cap]:.1f}")

            # 可执行加分
            cap_data = self._get_capability(cap)
            if cap_data and cap_data.get("is_executable"):
                score += 1.0
                reasons.append("可直接执行 +1.0")

            merged[cap] = (score, reasons)

        # 排序构建候选
        candidates: list[IntentCandidate] = []
        for cap_name, (score, reasons) in sorted(
            merged.items(), key=lambda x: x[1][0], reverse=True
        ):
            cap_data = self._get_capability(cap_name)
            if cap_data:
                candidates.append(
                    IntentCandidate(
                        name=cap_name,
                        score=score,
                        reason="; ".join(reasons),
                        payload=cap_data,
                    )
                )

        return candidates

    def _get_capability(self, name: str) -> dict[str, Any] | None:
        """获取 capability 数据。"""
        for cap in self._capabilities:
            if cap.get("name") == name:
                return cap
        return None

    def analyze(
        self,
        user_message: str,
        *,
        capabilities: list[dict[str, Any]] | None = None,
        semantic_skills: list[dict[str, Any]] | None = None,
        skill_limit: int = 3,
        has_datasets: bool = False,
        user_profile: UserProfile | None = None,
    ) -> IntentAnalysis:
        """分析用户意图，同时处理 capability 候选与 skill 候选。

        Args:
            user_message: 用户输入消息
            capabilities: capability 列表，首次调用时会触发索引构建
            semantic_skills: 语义技能目录
            skill_limit: skill 候选数量限制
            has_datasets: 是否已上传数据集（影响澄清阈值）
            user_profile: 用户画像（用于 profile_boost 加权）

        Returns:
            IntentAnalysis: 意图分析结果
        """
        # 延迟初始化或 capabilities 变更时重建索引
        # 若显式传入 capabilities，且与当前缓存不同，则重置并重新初始化
        if capabilities is not None:
            if set(cap.get("name", "") for cap in capabilities) != set(
                cap.get("name", "") for cap in self._capabilities
            ):
                self._initialized = False
                self._trie = TrieNode()
                self._inverted_index = {}
                self._capabilities = []
            self.initialize(capabilities)

        analysis = IntentAnalysis(query=user_message)

        if self._initialized:
            # 三路匹配：Trie 名称 + 同义词倒排索引 + 关键词
            trie_matches = self._trie_match(user_message)
            synonym_matches = self._synonym_match(user_message)
            keyword_matches = self._keyword_match(user_message)

            candidates = self._merge_and_rank(trie_matches, synonym_matches, keyword_matches)

            # profile_boost：用户画像加权后重排
            if user_profile is not None:
                boosted_candidates = apply_boost(candidates, user_profile)
                analysis.capability_candidates = boosted_candidates[:5]
                analysis.tool_hints = self._build_tool_hints(boosted_candidates)
            else:
                analysis.capability_candidates = candidates[:5]
                analysis.tool_hints = self._build_tool_hints(candidates)

            # 子类型注入：Top-1 为 difference_analysis 时，追加具体检验工具到 tool_hints 首位
            if (
                analysis.capability_candidates
                and analysis.capability_candidates[0].name == "difference_analysis"
            ):
                subtype = get_difference_subtype(user_message)
                if subtype is not None:
                    analysis.tool_hints.insert(0, subtype)

            self._apply_clarification_policy(analysis, has_datasets=has_datasets)
            analysis.clarification_options = self._build_clarification_options(
                analysis, capabilities or self._capabilities
            )

            if not analysis.clarification_options and analysis.clarification_needed:
                analysis.clarification_options = self._build_fallback_capability_options(
                    capabilities or self._capabilities
                )

            # 低置信度结构化日志
            if not analysis.capability_candidates or analysis.capability_candidates[0].score < 3.0:
                _lowconf_logger.info(
                    json.dumps(
                        {
                            "query": user_message[:200],
                            "top_score": (
                                analysis.capability_candidates[0].score
                                if analysis.capability_candidates
                                else 0.0
                            ),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                    )
                )
        elif capabilities is not None:
            # 未初始化但有 capabilities：直接线性扫描（兜底）
            analysis.capability_candidates = self.rank_capabilities(user_message, capabilities)
            analysis.tool_hints = self._build_tool_hints(analysis.capability_candidates)
            self._apply_clarification_policy(analysis)
            analysis.clarification_options = self.build_clarification_options(analysis)
            if not analysis.clarification_options and analysis.clarification_needed:
                analysis.clarification_options = self._build_fallback_capability_options(
                    capabilities
                )

        # skill 处理
        if semantic_skills:
            analysis.explicit_skill_calls = self.parse_explicit_skill_calls(user_message)
            analysis.skill_candidates = self.rank_semantic_skills(
                user_message,
                semantic_skills,
                limit=skill_limit,
            )
            active_skills = self.select_active_skills(user_message, semantic_skills)
            analysis.active_skills = [_summarize_skill_item(item) for item in active_skills]
            allowed_tools, sources = self.collect_allowed_tools(active_skills)
            analysis.allowed_tools = sorted(allowed_tools) if allowed_tools else []
            analysis.allowed_tool_sources = sources

        # 推断查询类型并设置 RAG/LTM 门控标志
        analysis.query_type = self._classify_query_type(user_message, analysis)
        analysis.rag_needed = analysis.query_type in {QueryType.DOMAIN_TASK, QueryType.KNOWLEDGE_QA}
        analysis.ltm_needed = analysis.rag_needed
        return analysis

    def _classify_query_type(self, message: str, analysis: IntentAnalysis) -> QueryType:
        """根据意图候选结果推断查询类型。"""
        msg = message.strip()
        if not msg:
            return QueryType.DOMAIN_TASK  # 空消息保守兜底
        # 超出科研服务范围检测——提前于候选判断，因为 OOS 查询通常无候选命中，
        # 若不提前检测会错误 fallback 到 KNOWLEDGE_QA
        if _OUT_OF_SCOPE_RE.search(msg):
            return QueryType.OUT_OF_SCOPE
        if not analysis.capability_candidates:
            # 无候选命中：区分闲聊和指令
            # 长度阈值仅覆盖极短的"好"/"嗯"/"继续"等，避免把 10 字内的科研短语误判为闲聊
            if _CASUAL_RE.match(msg) or len(msg) <= 5:
                return QueryType.CASUAL_CHAT
            if _COMMAND_RE.search(msg):
                return QueryType.COMMAND
            # 无候选但消息较长：保守触发 RAG（可能是未知领域问题或 slash 技能调用）
            return QueryType.KNOWLEDGE_QA
        # 有候选：按分数区分任务和知识问答
        top_score = analysis.capability_candidates[0].score
        if top_score >= 5.0:
            return QueryType.DOMAIN_TASK
        return QueryType.KNOWLEDGE_QA

    def rank_capabilities(
        self,
        user_message: str,
        capabilities: list[dict[str, Any]],
        *,
        limit: int = 5,
    ) -> list[IntentCandidate]:
        """基于规则 + 同义词扩展打分返回 capability 候选（线性扫描，用于兜底）。"""
        if not user_message:
            return []

        query = user_message.lower()
        candidates: list[IntentCandidate] = []
        for item in capabilities:
            name = str(item.get("name", "")).strip()
            display_name = str(item.get("display_name", "")).strip()
            description = str(item.get("description", "")).strip()
            if not name:
                continue

            score = 0.0
            reasons: list[str] = []
            normalized_name = name.lower().replace("_", " ").replace("-", " ")
            normalized_display = display_name.lower()

            # 1) 精确名称匹配（最高优先）
            if name.lower() in query or normalized_name in query:
                score += 10.0
                reasons.append("命中 capability 名称")
            if normalized_display and normalized_display in query:
                score += 8.0
                reasons.append("命中展示名称")

            # 2) 同义词匹配（覆盖长尾自然语言表达）
            synonyms = _SYNONYM_MAP.get(name.lower(), [])
            synonym_hits = [s for s in synonyms if s in query]
            if synonym_hits:
                score += min(6.0, 2.0 * len(synonym_hits))
                reasons.append(f"命中同义词: {', '.join(synonym_hits[:3])}")

            # 3) 描述关键词匹配
            terms = _extract_terms(display_name, description, normalized_name)
            term_hits = [term for term in terms if term in query]
            if term_hits:
                score += min(4.0, 1.5 * len(term_hits))
                reasons.append(f"命中关键词: {', '.join(term_hits[:3])}")

            # 4) 工具名称匹配
            required_tools = _normalize_required_tools(item.get("required_tools"))
            tool_hits = [tool for tool in required_tools if tool.lower() in query]
            if tool_hits:
                score += min(2.0, 0.5 * len(tool_hits))
                reasons.append(f"命中工具提示: {', '.join(tool_hits[:3])}")

            # 5) 可执行能力加分（优先推荐可直接执行的能力）
            if score > 0 and item.get("is_executable"):
                score += 1.0
                reasons.append("可直接执行")

            if score <= 0:
                continue

            candidates.append(
                IntentCandidate(
                    name=name,
                    score=score,
                    reason="；".join(reasons),
                    payload=item,
                )
            )

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates[:limit]

    def rank_semantic_skills(
        self,
        user_message: str,
        semantic_catalog: list[dict[str, Any]],
        *,
        limit: int = 1,
    ) -> list[IntentCandidate]:
        """基于语义目录为 Markdown Skills 打分。"""
        if not user_message:
            return []

        query = user_message.lower()
        scored: list[IntentCandidate] = []
        for item in semantic_catalog:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("enabled", True)):
                continue
            if bool(item.get("disable_model_invocation", False)):
                continue

            metadata = item.get("metadata")
            aliases: list[str] = []
            tags: list[str] = []
            raw_aliases = item.get("aliases", [])
            if isinstance(raw_aliases, list):
                aliases.extend(str(alias).strip() for alias in raw_aliases if str(alias).strip())
            raw_tags = item.get("tags", [])
            if isinstance(raw_tags, list):
                tags.extend(str(tag).strip() for tag in raw_tags if str(tag).strip())
            if isinstance(metadata, dict):
                metadata_aliases = metadata.get("aliases", [])
                if isinstance(metadata_aliases, list):
                    aliases.extend(
                        str(alias).strip() for alias in metadata_aliases if str(alias).strip()
                    )
                metadata_tags = metadata.get("tags", [])
                if isinstance(metadata_tags, list):
                    tags.extend(str(tag).strip() for tag in metadata_tags if str(tag).strip())

            reasons: list[str] = []
            score = 0.0
            seen_aliases: set[str] = set()
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in seen_aliases:
                    continue
                seen_aliases.add(alias_lower)
                if alias_lower in query:
                    score += 2.0
                    reasons.append(f"命中别名: {alias}")
                    break

            seen_tags: set[str] = set()
            tag_hits: list[str] = []
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in seen_tags:
                    continue
                seen_tags.add(tag_lower)
                if tag_lower in query:
                    score += 0.5
                    tag_hits.append(tag)
            if tag_hits:
                reasons.append(f"命中标签: {', '.join(tag_hits[:3])}")

            name = str(item.get("name", "")).strip()
            normalized_name = name.lower().replace("-", " ").replace("_", " ")
            if normalized_name and normalized_name in query:
                score += 1.5
                reasons.append("命中技能名称")

            if score <= 0:
                continue

            scored.append(
                IntentCandidate(
                    name=name,
                    score=score,
                    reason="；".join(reasons),
                    payload=item,
                )
            )

        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        return scored[:limit]

    def parse_explicit_skill_calls(
        self,
        user_message: str,
        *,
        limit: int = 2,
    ) -> list[dict[str, str]]:
        """解析显式 `/skill` 调用。"""
        if not user_message:
            return []

        calls: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in SLASH_SKILL_WITH_ARGS_RE.finditer(user_message):
            name = match.group(1).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            calls.append(
                {
                    "name": name,
                    "arguments": (match.group(2) or "").strip(),
                }
            )
            if len(calls) >= limit:
                break
        return calls

    def select_active_skills(
        self,
        user_message: str,
        markdown_items: list[dict[str, Any]],
        *,
        explicit_limit: int = 2,
        auto_limit: int = 1,
    ) -> list[dict[str, Any]]:
        """选择本轮激活的 Markdown Skills。"""
        if not user_message or not isinstance(markdown_items, list):
            return []

        skill_map = {
            str(item.get("name", "")).strip(): item
            for item in markdown_items
            if isinstance(item, dict)
        }
        explicit_items: list[dict[str, Any]] = []
        for call in self.parse_explicit_skill_calls(user_message, limit=explicit_limit):
            item = skill_map.get(call["name"])
            if not isinstance(item, dict):
                continue
            if not bool(item.get("enabled", True)):
                continue
            if not _normalize_user_invocable(item):
                continue
            explicit_items.append(item)

        if explicit_items:
            return explicit_items

        matches = self.rank_semantic_skills(user_message, markdown_items, limit=auto_limit)
        selected: list[dict[str, Any]] = []
        for candidate in matches:
            if isinstance(candidate.payload, dict):
                selected.append(candidate.payload)
        return selected

    def collect_allowed_tools(
        self,
        markdown_items: list[dict[str, Any]],
    ) -> tuple[set[str] | None, list[str]]:
        """汇总 active skills 提供的 allowed_tools 推荐。"""
        if not markdown_items:
            return None, []

        allowed: set[str] = set()
        sources: list[str] = []
        for item in markdown_items:
            metadata = item.get("metadata")
            raw_tools = None
            if isinstance(metadata, dict):
                raw_tools = metadata.get("allowed_tools")
            if raw_tools is None:
                raw_tools = item.get("allowed_tools")
            tool_names = _normalize_required_tools(raw_tools)
            if not tool_names:
                continue
            allowed.update(tool_names)
            sources.append(str(item.get("name", "")).strip() or "unknown")

        if not allowed:
            return None, []
        return allowed, sources

    def _build_tool_hints(self, candidates: list[IntentCandidate]) -> list[str]:
        """根据候选 capability 提取推荐工具。"""
        if not candidates:
            return []
        tool_hints: list[str] = []
        seen: set[str] = set()
        for candidate in candidates[:2]:
            for tool_name in _normalize_required_tools(candidate.payload.get("required_tools")):
                if tool_name in seen:
                    continue
                seen.add(tool_name)
                tool_hints.append(tool_name)
                if len(tool_hints) >= 6:
                    return tool_hints
        return tool_hints

    def _apply_clarification_policy(
        self, analysis: IntentAnalysis, *, has_datasets: bool = False
    ) -> None:
        """应用澄清策略。

        改进版：考虑相对差距和绝对分数。
        当 has_datasets=True 且 Top-1 属于数据分析类白名单时，收紧阈值减少追问。
        超出支持范围的请求不触发澄清，由 LLM 直接说明能力边界。
        """
        # 超出支持范围的请求不触发澄清
        if _OUT_OF_SCOPE_RE.search(analysis.query):
            return

        candidates = analysis.capability_candidates

        if len(candidates) < 2:
            return

        top1, top2 = candidates[0], candidates[1]

        # 策略 1：相对差距
        relative_gap = (top1.score - top2.score) / top1.score if top1.score > 0 else 1.0

        # 策略 2：绝对置信度阈值
        min_confidence = 5.0

        # 有数据集 + 数据分析类候选时收紧阈值
        tighten = has_datasets and top1.name in self._DATA_ANALYSIS_WHITELIST
        gap_threshold = 0.15 if tighten else 0.25
        score_spread_threshold = 2.0 if tighten else 3.0

        # 策略 3：分数分布（如果有多于2个候选）
        if len(candidates) >= 3:
            top3 = candidates[2]
            # 如果第三名也很接近，需要澄清
            if top1.score - top3.score < score_spread_threshold and top1.score >= min_confidence:
                analysis.clarification_needed = True
                analysis.clarification_question = (
                    f"你想进行 {top1.payload.get('display_name', top1.name)} "
                    f"还是 {top2.payload.get('display_name', top2.name)}？"
                )
                return

        # 两个候选分数接近且都较高
        if relative_gap < gap_threshold and top1.score >= min_confidence:
            analysis.clarification_needed = True
            analysis.clarification_question = (
                f"你想进行 {top1.payload.get('display_name', top1.name)} "
                f"还是 {top2.payload.get('display_name', top2.name)}？"
            )

    def build_clarification_options(self, analysis: IntentAnalysis) -> list[dict[str, str]]:
        """基于 capability 候选生成澄清选项（兼容旧接口）。"""
        return self._build_clarification_options(analysis, self._capabilities)

    def _build_clarification_options(
        self,
        analysis: IntentAnalysis,
        capabilities: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """构建澄清选项。"""
        options: list[dict[str, str]] = []

        # 从候选生成
        for candidate in analysis.capability_candidates[:3]:
            payload = candidate.payload
            label = payload.get("display_name", candidate.name)
            description = payload.get("description", candidate.reason)

            if label and description:
                options.append(
                    {
                        "label": label,
                        "description": description,
                    }
                )

        # 如果没有候选，使用前几个 capability 兜底
        if not options and capabilities:
            for cap in capabilities[:3]:
                label = cap.get("display_name") or cap.get("name", "")
                description = cap.get("description", "")
                if label and description:
                    options.append(
                        {
                            "label": label,
                            "description": description,
                        }
                    )

        return options

    def _build_fallback_capability_options(
        self,
        capabilities: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """当没有候选命中时，从 capability 目录生成兜底选项。"""
        options: list[dict[str, str]] = []
        for item in capabilities[:3]:
            label = str(item.get("display_name", "")).strip() or str(item.get("name", "")).strip()
            description = str(item.get("description", "")).strip()
            if not label or not description:
                continue
            options.append(
                {
                    "label": label,
                    "description": description,
                }
            )
        return options


default_intent_analyzer = IntentAnalyzer()
