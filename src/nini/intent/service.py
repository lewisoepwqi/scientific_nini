"""意图分析服务 — 规则版 v2，支持同义词扩展和元数据加权。"""

from __future__ import annotations

import re
from typing import Any

from nini.intent.base import IntentAnalysis, IntentCandidate

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

# 科研意图同义词表 — 将自然语言表达映射到 capability 名称
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
    ],
    "correlation_analysis": [
        "相关",
        "相关性",
        "关联",
        "联系",
        "关系",
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
    ],
}


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


class IntentAnalyzer:
    """规则版意图分析器。"""

    def analyze(
        self,
        user_message: str,
        *,
        capabilities: list[dict[str, Any]] | None = None,
        semantic_skills: list[dict[str, Any]] | None = None,
        skill_limit: int = 3,
    ) -> IntentAnalysis:
        """同时分析 capability 候选与 skill 候选。"""
        analysis = IntentAnalysis(query=user_message)
        if capabilities:
            analysis.capability_candidates = self.rank_capabilities(user_message, capabilities)
            analysis.tool_hints = self._build_tool_hints(analysis.capability_candidates)
            self._apply_clarification_policy(analysis)
            analysis.clarification_options = self.build_clarification_options(analysis)
            if not analysis.clarification_options and analysis.clarification_needed:
                analysis.clarification_options = self._build_fallback_capability_options(
                    capabilities
                )
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
        return analysis

    def rank_capabilities(
        self,
        user_message: str,
        capabilities: list[dict[str, Any]],
        *,
        limit: int = 5,
    ) -> list[IntentCandidate]:
        """基于规则 + 同义词扩展打分返回 capability 候选。"""
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

    def _apply_clarification_policy(self, analysis: IntentAnalysis) -> None:
        """根据候选分布决定是否需要追问。"""
        candidates = analysis.capability_candidates
        if not candidates:
            analysis.clarification_needed = True
            analysis.clarification_question = (
                "请补充你的目标，例如是想做差异分析、相关性分析、数据探索、可视化还是报告生成？"
            )
            return

        if len(candidates) >= 2 and abs(candidates[0].score - candidates[1].score) <= 1.0:
            top_names = []
            for candidate in candidates[:2]:
                display_name = str(candidate.payload.get("display_name", "")).strip()
                top_names.append(display_name or candidate.name)
            analysis.clarification_needed = True
            analysis.clarification_question = f"你更想做 {top_names[0]} 还是 {top_names[1]}？"

    def build_clarification_options(self, analysis: IntentAnalysis) -> list[dict[str, str]]:
        """基于 capability 候选生成澄清选项。"""
        options: list[dict[str, str]] = []
        for candidate in analysis.capability_candidates[:3]:
            payload = candidate.payload or {}
            label = str(payload.get("display_name", "")).strip() or candidate.name
            description = str(payload.get("description", "")).strip() or candidate.reason
            if not label or not description:
                continue
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
