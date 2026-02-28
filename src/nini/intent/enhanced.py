"""增强版意图分析 —— 规则 + Embedding 语义融合。

结合规则匹配（精确、可解释）和语义匹配（泛化能力强）的优势，
提供更好的长尾表达理解能力。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.intent.base import IntentAnalysis, IntentCandidate
from nini.intent.semantic import (
    SemanticIntentMatcher,
    SimpleEmbeddingProvider,
    normalize_similarity_score,
)

logger = logging.getLogger(__name__)


class EnhancedIntentAnalyzer:
    """增强版意图分析器 —— 规则 + 语义融合。
    
    评分策略：
    - 规则匹配分数（0-10）：精确匹配、同义词、关键词
    - 语义相似度分数（0-10）：embedding 余弦相似度
    - 融合分数 = max(规则分数, 语义分数 × 权重) +  bonus
    
    当两种方法都命中时给予额外加分，提高置信度。
    """
    
    def __init__(
        self,
        semantic_weight: float = 0.9,
        agreement_bonus: float = 2.0,
        semantic_threshold: float = 0.6,
    ) -> None:
        """初始化增强分析器。
        
        Args:
            semantic_weight: 语义分数权重（相对规则分数）
            agreement_bonus: 两种方法一致时的额外加分
            semantic_threshold: 语义匹配最小阈值（余弦相似度）
        """
        self.semantic_weight = semantic_weight
        self.agreement_bonus = agreement_bonus
        self.semantic_threshold = semantic_threshold
        
        # 延迟初始化语义匹配器
        self._matcher: SemanticIntentMatcher | None = None
        self._matcher_available: bool | None = None
    
    @property
    def is_semantic_available(self) -> bool:
        """检查语义匹配是否可用。"""
        if self._matcher_available is not None:
            return self._matcher_available
        
        if self._matcher is None:
            provider = SimpleEmbeddingProvider()
            self._matcher = SemanticIntentMatcher(provider)
        
        self._matcher_available = self._matcher.provider.is_available
        if self._matcher_available:
            logger.info("语义匹配已启用（embedding 服务可用）")
        else:
            logger.info("语义匹配未启用（embedding 服务不可用），将仅使用规则匹配")
        
        return self._matcher_available
    
    def analyze(
        self,
        user_message: str,
        *,
        capabilities: list[dict[str, Any]] | None = None,
        semantic_skills: list[dict[str, Any]] | None = None,
        rule_based_analysis: IntentAnalysis | None = None,
        skill_limit: int = 3,
    ) -> IntentAnalysis:
        """执行增强版意图分析。
        
        Args:
            user_message: 用户输入
            capabilities: capability 目录
            semantic_skills: skill 目录
            rule_based_analysis: 已有的规则分析结果（可选）
            skill_limit: 返回 skill 候选数量上限
            
        Returns:
            融合后的意图分析结果
        """
        # 如果没有语义匹配能力，直接返回规则结果
        if not self.is_semantic_available or not user_message:
            if rule_based_analysis:
                rule_based_analysis.analysis_method = "rule_based_v2"
                return rule_based_analysis
            
            # 创建一个空的分析结果
            return IntentAnalysis(
                query=user_message,
                analysis_method="rule_based_v2",
            )
        
        # 确保有规则分析结果
        if rule_based_analysis is None:
            from nini.intent.service import default_intent_analyzer
            rule_based_analysis = default_intent_analyzer.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
                skill_limit=skill_limit,
            )
        
        # 执行语义匹配
        enhanced = self._apply_semantic_matching(
            user_message,
            rule_based_analysis,
            capabilities or [],
            semantic_skills or [],
        )
        
        enhanced.analysis_method = "hybrid_v1"
        return enhanced
    
    def _apply_semantic_matching(
        self,
        query: str,
        rule_analysis: IntentAnalysis,
        capabilities: list[dict[str, Any]],
        skills: list[dict[str, Any]],
    ) -> IntentAnalysis:
        """应用语义匹配并融合分数。"""
        assert self._matcher is not None
        
        result = IntentAnalysis(
            query=rule_analysis.query,
            explicit_skill_calls=rule_analysis.explicit_skill_calls,
            active_skills=rule_analysis.active_skills,
            allowed_tools=rule_analysis.allowed_tools,
            allowed_tool_sources=rule_analysis.allowed_tool_sources,
            clarification_needed=rule_analysis.clarification_needed,
            clarification_question=rule_analysis.clarification_question,
            clarification_options=rule_analysis.clarification_options,
        )
        
        # 1. 融合 capability 候选
        result.capability_candidates = self._merge_capability_candidates(
            query,
            rule_analysis.capability_candidates,
            capabilities,
        )
        
        # 2. 融合 skill 候选
        result.skill_candidates = self._merge_skill_candidates(
            query,
            rule_analysis.skill_candidates,
            skills,
        )
        
        return result
    
    def _merge_capability_candidates(
        self,
        query: str,
        rule_candidates: list[IntentCandidate],
        capabilities: list[dict[str, Any]],
    ) -> list[IntentCandidate]:
        """融合规则和语义的 capability 候选。"""
        assert self._matcher is not None
        
        # 获取语义匹配结果
        semantic_matches = self._matcher.match_capabilities(query, capabilities, top_k=10)
        semantic_dict = {
            name: score for name, score in semantic_matches
            if score >= self.semantic_threshold
        }
        
        # 规则候选转为字典
        rule_dict = {c.name: c for c in rule_candidates}
        
        # 所有可能的 capability 名称
        all_names = set(rule_dict.keys()) | set(semantic_dict.keys())
        
        merged: list[IntentCandidate] = []
        
        for name in all_names:
            rule_candidate = rule_dict.get(name)
            semantic_sim = semantic_dict.get(name, 0.0)
            
            # 获取 capability 信息
            cap_info = next(
                (c for c in capabilities if c.get("name") == name),
                {}
            )
            
            # 计算分数
            rule_score = rule_candidate.score if rule_candidate else 0.0
            semantic_score = normalize_similarity_score(semantic_sim, "sigmoid")
            
            # 融合策略
            if rule_candidate and semantic_sim >= self.semantic_threshold:
                # 两种方法都命中，取最高分 + 一致性奖励
                base_score = max(rule_score, semantic_score * self.semantic_weight)
                final_score = base_score + self.agreement_bonus
                reason = f"{rule_candidate.reason}；语义相似度: {semantic_sim:.2f}"
            elif rule_candidate:
                # 只有规则命中
                final_score = rule_score
                reason = rule_candidate.reason
            else:
                # 只有语义命中
                final_score = semantic_score * self.semantic_weight
                reason = f"语义匹配: 相似度 {semantic_sim:.2f}"
            
            # 过滤低分候选
            if final_score < 3.0:
                continue
            
            merged.append(IntentCandidate(
                name=name,
                score=min(final_score, 15.0),  # 上限 15 分
                reason=reason,
                payload=rule_candidate.payload if rule_candidate else cap_info,
            ))
        
        # 按分数排序
        merged.sort(key=lambda x: x.score, reverse=True)
        return merged[:5]  # 返回前 5
    
    def _merge_skill_candidates(
        self,
        query: str,
        rule_candidates: list[IntentCandidate],
        skills: list[dict[str, Any]],
    ) -> list[IntentCandidate]:
        """融合规则和语义的 skill 候选。"""
        assert self._matcher is not None
        
        # 获取语义匹配结果
        semantic_matches = self._matcher.match_skills(query, skills, top_k=10)
        semantic_dict = {
            name: score for name, score in semantic_matches
            if score >= self.semantic_threshold
        }
        
        # 规则候选转为字典
        rule_dict = {c.name: c for c in rule_candidates}
        
        # 所有可能的 skill 名称
        all_names = set(rule_dict.keys()) | set(semantic_dict.keys())
        
        merged: list[IntentCandidate] = []
        
        for name in all_names:
            rule_candidate = rule_dict.get(name)
            semantic_sim = semantic_dict.get(name, 0.0)
            
            # 获取 skill 信息
            skill_info = next(
                (s for s in skills if s.get("name") == name),
                {}
            )
            
            # 计算分数
            rule_score = rule_candidate.score if rule_candidate else 0.0
            semantic_score = normalize_similarity_score(semantic_sim, "sigmoid")
            
            # 融合策略
            if rule_candidate and semantic_sim >= self.semantic_threshold:
                base_score = max(rule_score, semantic_score * self.semantic_weight)
                final_score = base_score + self.agreement_bonus * 0.5  # skill 的奖励稍低
                reason = f"{rule_candidate.reason}；语义匹配"
            elif rule_candidate:
                final_score = rule_score
                reason = rule_candidate.reason
            else:
                final_score = semantic_score * self.semantic_weight
                reason = f"语义匹配: 相似度 {semantic_sim:.2f}"
            
            if final_score < 2.0:
                continue
            
            merged.append(IntentCandidate(
                name=name,
                score=min(final_score, 12.0),
                reason=reason,
                payload=rule_candidate.payload if rule_candidate else skill_info,
            ))
        
        merged.sort(key=lambda x: x.score, reverse=True)
        return merged[:3]


# 全局单例
_enhanced_analyzer: EnhancedIntentAnalyzer | None = None


def get_enhanced_intent_analyzer() -> EnhancedIntentAnalyzer:
    """获取全局增强版意图分析器实例。"""
    global _enhanced_analyzer
    if _enhanced_analyzer is None:
        _enhanced_analyzer = EnhancedIntentAnalyzer()
    return _enhanced_analyzer
