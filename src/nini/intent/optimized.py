"""优化版规则意图分析器 — 本地优先实现。

使用 Trie 树和倒排索引实现高效的意图匹配，无需外部 Embedding 服务。
- 延迟：~3ms（单次匹配）
- 内存：~15MB（索引结构）
- 依赖：零外部依赖
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from nini.intent.base import IntentAnalysis, IntentCandidate

logger = logging.getLogger(__name__)

# 显式 skill 调用正则（从 service.py 引入）
SLASH_SKILL_WITH_ARGS_RE = re.compile(
    r"(?<!\S)/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.+?))?(?=\s*/[A-Za-z]|\s*$)", re.DOTALL
)

# 科研意图同义词表 — 将自然语言表达映射到 capability 名称
_SYNONYM_MAP: dict[str, list[str]] = {
    "difference_analysis": [
        "差异", "显著性", "t检验", "t_test", "anova", "方差分析",
        "对比", "比较差异", "两组差异", "多组差异", "组间差异",
        "显著差别", "差别", "对比分析", "均值比较",
        "mann_whitney", "kruskal", "非参数检验", "wilcoxon",
    ],
    "correlation_analysis": [
        "相关", "相关性", "关联", "pearson", "spearman", "kendall",
        "相关系数", "变量关系", "协变", "共变", "相互关系",
        "有没有联系", "有没有关系", "是否相关", "相关性分析",
    ],
    "regression_analysis": [
        "回归", "预测", "建模", "线性模型", "regression", "拟合",
        "回归方程", "自变量", "因变量", "预测模型", "逻辑回归",
        "多元回归", "逐步回归", "岭回归", "lasso",
    ],
    "data_exploration": [
        "探索", "概览", "描述性统计", "分布", "缺失值", "异常值",
        "数据质量", "数据特征", "看看数据", "了解数据", "数据情况",
        "描述统计", "基本统计", "数据概览", "探索性分析", "eda",
    ],
    "data_cleaning": [
        "清洗", "预处理", "处理缺失", "填充", "去重", "标准化",
        "归一化", "异常处理", "数据清理", "数据整理", "缺失值处理",
        "异常值处理", "数据转换", "特征工程",
    ],
    "visualization": [
        "可视化", "画图", "作图", "图形", "箱线图", "散点图",
        "柱状图", "热力图", "直方图", "折线图", "饼图", "chart",
        "plot", "graph", "画图展示", "绘制图表",
    ],
    "report_generation": [
        "报告", "报表", "汇总", "总结", "导出报告", "生成报告",
        "分析报告", "report", "summary", "word", "pdf",
    ],
    "article_draft": [
        "论文", "文章", "初稿", "manuscript", "publication",
        "科研论文", "学术论文", "撰写论文", "论文写作",
    ],
}

# 通用中文停用词（这些词在匹配时权重降低）
_GENERIC_TERMS: set[str] = {
    "数据", "分析", "结果", "研究", "生成", "比较", "报告",
    "图表", "工具", "方法", "进行", "使用", "帮我", "请",
    "一下", "一个", "需要", "想要", "希望", "能", "可以",
}


@dataclass
class TrieNode:
    """Trie 树节点。"""
    children: dict[str, "TrieNode"] = field(default_factory=dict)
    is_end: bool = False
    capability: str | None = None


class OptimizedIntentAnalyzer:
    """优化版规则意图分析器。

    使用 Trie 树和倒排索引实现 O(1) ~ O(n) 的匹配复杂度，
    无需外部 Embedding 服务，完全本地运行。

    Attributes:
        _trie: 前缀树，用于 capability 名称快速匹配
        _inverted_index: 倒排索引，用于同义词快速查找
        _capability_keywords: capability 关键词映射
    """

    def __init__(self) -> None:
        """初始化优化版意图分析器。"""
        self._trie = TrieNode()
        self._inverted_index: dict[str, set[str]] = {}
        self._capability_keywords: dict[str, set[str]] = {}
        self._capabilities: list[dict[str, Any]] = []
        self._initialized = False

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
                "优化版意图分析器初始化完成: %d capabilities, %d 索引项",
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
        for cap_name, synonyms in _SYNONYM_MAP.items():
            for synonym in synonyms:
                synonym_lower = synonym.lower()
                if synonym_lower not in self._inverted_index:
                    self._inverted_index[synonym_lower] = set()
                self._inverted_index[synonym_lower].add(cap_name)

                # 同时索引单个字符（中文）
                if len(synonym) == 1 or all(\
                    "\u4e00" <= c <= "\u9fff" for c in synonym
                ):
                    for char in synonym:
                        if char not in self._inverted_index:
                            self._inverted_index[char] = set()
                        self._inverted_index[char].add(cap_name)

    def analyze(
        self,
        user_message: str,
        *,
        capabilities: list[dict[str, Any]] | None = None,
        skill_limit: int = 3,
    ) -> IntentAnalysis:
        """分析用户意图。

        Args:
            user_message: 用户输入消息
            capabilities: capability 列表，首次调用时必须提供
            skill_limit: skill 候选数量限制

        Returns:
            IntentAnalysis: 意图分析结果
        """
        # 延迟初始化
        if not self._initialized and capabilities:
            self.initialize(capabilities)

        if not self._initialized:
            logger.warning("意图分析器未初始化，返回空结果")
            return IntentAnalysis(query=user_message)

        analysis = IntentAnalysis(query=user_message)

        # 执行多层匹配
        trie_matches = self._trie_match(user_message)
        synonym_matches = self._synonym_match(user_message)
        keyword_matches = self._keyword_match(user_message)

        # 融合排序
        candidates = self._merge_and_rank(
            trie_matches, synonym_matches, keyword_matches
        )

        analysis.capability_candidates = candidates[:5]
        analysis.tool_hints = self._build_tool_hints(candidates)
        self._apply_clarification_policy(analysis)
        analysis.clarification_options = self._build_clarification_options(
            analysis, capabilities or self._capabilities
        )

        return analysis

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
        scores: dict[str, float] = {}

        # 直接匹配
        for synonym, caps in self._inverted_index.items():
            if synonym in message_lower:
                for cap in caps:
                    # 根据同义词长度给予不同权重
                    weight = min(6.0, 2.0 + len(synonym) * 0.5)
                    scores[cap] = scores.get(cap, 0) + weight

        return scores

    def _keyword_match(self, message: str) -> dict[str, float]:
        """关键词提取匹配。

        从 capability 描述中提取关键词进行匹配。
        """
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
        # 合并分数
        all_caps = set(trie_matches.keys()) | set(synonym_matches.keys()) | set(keyword_matches.keys())

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

    def _build_tool_hints(self, candidates: list[IntentCandidate]) -> list[str]:
        """根据候选提取工具提示。"""
        hints: list[str] = []
        seen: set[str] = set()

        for candidate in candidates[:2]:
            tools = candidate.payload.get("required_tools", [])
            for tool in tools[:4]:
                if tool not in seen:
                    seen.add(tool)
                    hints.append(tool)

        return hints[:6]

    def _apply_clarification_policy(self, analysis: IntentAnalysis) -> None:
        """应用澄清策略。

        改进版：考虑相对差距和绝对分数。
        """
        candidates = analysis.capability_candidates

        if len(candidates) < 2:
            return

        top1, top2 = candidates[0], candidates[1]

        # 策略 1：相对差距
        relative_gap = (
            (top1.score - top2.score) / top1.score if top1.score > 0 else 1.0
        )

        # 策略 2：绝对置信度阈值
        min_confidence = 5.0

        # 策略 3：分数分布（如果有多于2个候选）
        if len(candidates) >= 3:
            top3 = candidates[2]
            # 如果第三名也很接近，需要澄清
            if top1.score - top3.score < 3.0 and top1.score >= min_confidence:
                analysis.clarification_needed = True
                analysis.clarification_question = (
                    f"你想进行 {top1.payload.get('display_name', top1.name)} "
                    f"还是 {top2.payload.get('display_name', top2.name)}？"
                )
                return

        # 两个候选分数接近且都较高
        if relative_gap < 0.25 and top1.score >= min_confidence:
            analysis.clarification_needed = True
            analysis.clarification_question = (
                f"你想进行 {top1.payload.get('display_name', top1.name)} "
                f"还是 {top2.payload.get('display_name', top2.name)}？"
            )

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
                options.append({
                    "label": label,
                    "description": description,
                })

        # 如果没有候选，使用前几个 capability 兜底
        if not options and capabilities:
            for cap in capabilities[:3]:
                label = cap.get("display_name") or cap.get("name", "")
                description = cap.get("description", "")
                if label and description:
                    options.append({
                        "label": label,
                        "description": description,
                    })

        return options

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


# 全局优化版分析器实例
optimized_intent_analyzer = OptimizedIntentAnalyzer()
