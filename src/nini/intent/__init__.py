"""意图分析模块。"""

from nini.intent.base import IntentAnalysis, IntentCandidate
from nini.intent.service import IntentAnalyzer, default_intent_analyzer

# 导出增强版语义分析（可选依赖）
try:
    from nini.intent.enhanced import EnhancedIntentAnalyzer, get_enhanced_intent_analyzer
    from nini.intent.semantic import SemanticIntentMatcher, SimpleEmbeddingProvider
    _enhanced_available = True
except ImportError:
    _enhanced_available = False
    EnhancedIntentAnalyzer = None  # type: ignore
    get_enhanced_intent_analyzer = None  # type: ignore
    SemanticIntentMatcher = None  # type: ignore
    SimpleEmbeddingProvider = None  # type: ignore

__all__ = [
    "IntentAnalysis",
    "IntentCandidate",
    "IntentAnalyzer",
    "default_intent_analyzer",
]

# 如果增强版可用，添加到导出
if _enhanced_available:
    __all__.extend([
        "EnhancedIntentAnalyzer",
        "get_enhanced_intent_analyzer",
        "SemanticIntentMatcher",
        "SimpleEmbeddingProvider",
    ])
