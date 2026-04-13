"""结构化分析记忆系统。

管理跨会话的结构化科研记忆，包含 AnalysisMemory 数据模型与持久化接口。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nini.agent.session import session_persistence_enabled
from nini.config import settings

logger = logging.getLogger(__name__)


# ---- 路径工具 ----


def _analysis_memory_dir(session_id: str, *, create: bool = True) -> Path:
    """返回会话的 AnalysisMemory 持久化目录。"""
    path = settings.sessions_dir / session_id / "analysis_memories"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _analysis_memory_path(session_id: str, dataset_name: str) -> Path:
    """返回指定数据集的 AnalysisMemory 文件路径。"""
    safe_name = quote(dataset_name, safe="")
    return _analysis_memory_dir(session_id, create=True) / f"{safe_name}.json"


# ---- 数据模型 ----


@dataclass
class Finding:
    """分析发现记录。

    用于记录分析过程中的关键发现，如统计显著性、效应量、数据问题等。
    """

    category: str  # 发现类别
    summary: str  # 简短总结
    detail: str = ""  # 详细描述
    confidence: float = 1.0  # 置信度 (0-1)
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    ltm_id: str = ""  # 已沉淀到长期记忆的条目 ID，非空表示已写入


@dataclass
class StatisticResult:
    """统计结果记录。

    记录统计检验的结果，便于后续引用和解释。
    """

    test_name: str  # 检验名称
    test_statistic: float | None = None  # 检验统计量
    p_value: float | None = None  # p 值
    degrees_of_freedom: int | None = None  # 自由度
    effect_size: float | None = None  # 效应量
    effect_type: str = ""  # 效应量类型 (cohens_d, eta_squared 等)
    confidence_interval_lower: float | None = None  # 置信区间下限
    confidence_interval_upper: float | None = None  # 置信区间上限
    confidence_level: float = 0.95  # 置信水平
    significant: bool | None = None  # 是否显著；None 表示未记录完整判定
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展元数据（样本量、配对结果等）
    ltm_id: str = ""  # 已沉淀到长期记忆的条目 ID，非空表示已写入


@dataclass
class Decision:
    """决策记录。

    记录分析过程中的决策，如方法选择、参数选择等。
    """

    decision_type: str  # 决策类型
    chosen: str  # 选择的方法/参数
    alternatives: list[str] = field(default_factory=list)  # 考虑的替代方案
    rationale: str = ""  # 决策理由
    confidence: float = 1.0  # 决策置信度
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    ltm_id: str = ""  # 已沉淀到长期记忆的条目 ID，非空表示已写入


@dataclass
class Artifact:
    """产出文件记录。

    记录分析过程中生成的文件，如图表、报告等。
    """

    artifact_type: str  # 文件类型 (chart, report, data)
    path: str  # 文件路径
    description: str = ""  # 描述
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据
    timestamp: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class AnalysisMemory:
    """结构化分析记忆。

    将分析结果提取为结构化知识，而非简单文本摘要。
    支持转换为可注入的上下文，用于后续分析。
    """

    session_id: str
    dataset_name: str
    findings: list[Finding] = field(default_factory=list)
    statistics: list[StatisticResult] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: __import__("time").time())
    updated_at: float = field(default_factory=lambda: __import__("time").time())

    def add_finding(self, finding: Finding) -> None:
        """添加发现记录。"""
        self.findings.append(finding)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def add_statistic(self, statistic: StatisticResult) -> None:
        """添加统计结果。"""
        signature = self._statistic_signature(statistic)
        for index, existing in enumerate(self.statistics):
            if self._statistic_signature(existing) == signature:
                statistic.ltm_id = existing.ltm_id or statistic.ltm_id
                self.statistics[index] = statistic
                break
        else:
            self.statistics.append(statistic)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def add_decision(self, decision: Decision) -> None:
        """添加决策记录。"""
        self.decisions.append(decision)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def add_artifact(
        self,
        artifact_type: str,
        path: str,
        description: str = "",
        **metadata: Any,
    ) -> None:
        """添加产出文件记录。"""
        artifact = Artifact(
            artifact_type=artifact_type,
            path=path,
            description=description,
            metadata=metadata,
        )
        self.artifacts.append(artifact)
        self.updated_at = __import__("time").time()
        save_analysis_memory(self)

    def summary(self) -> str:
        """生成摘要文本。"""
        parts: list[str] = []

        if self.findings:
            parts.append(f"关键发现 ({len(self.findings)} 项)")

        if self.statistics:
            parts.append(f"统计结果 ({len(self.statistics)} 项)")

        if self.decisions:
            parts.append(f"决策记录 ({len(self.decisions)} 项)")

        if self.artifacts:
            parts.append(f"产出文件 ({len(self.artifacts)} 个)")

        if not parts:
            return "分析记忆为空"

        return "、".join(parts) + f"（数据集: {self.dataset_name}）"

    @staticmethod
    def _statistic_signature(statistic: StatisticResult) -> tuple[Any, ...]:
        """生成统计结果签名，用于幂等更新相同分析结果。"""
        metadata = statistic.metadata if isinstance(statistic.metadata, dict) else {}
        key_pairs = []
        for key in ("dataset_name", "method", "sample_size", "variables", "pairwise"):
            value = metadata.get(key)
            key_pairs.append(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
        return (
            statistic.test_name,
            statistic.test_statistic,
            statistic.p_value,
            statistic.degrees_of_freedom,
            statistic.effect_size,
            statistic.effect_type,
            statistic.significant,
            *key_pairs,
        )

    def to_context(self) -> dict[str, Any]:
        """转换为可注入的上下文。"""
        return {
            "dataset_name": self.dataset_name,
            "findings": [
                {
                    "category": f.category,
                    "summary": f.summary,
                    "detail": f.detail,
                    "confidence": f.confidence,
                }
                for f in self.findings
            ],
            "statistics": [
                {
                    "test_name": s.test_name,
                    "test_statistic": s.test_statistic,
                    "p_value": s.p_value,
                    "effect_size": s.effect_size,
                    "effect_type": s.effect_type,
                    "significant": s.significant,
                    "metadata": s.metadata,
                }
                for s in self.statistics
            ],
            "decisions": [
                {
                    "type": d.decision_type,
                    "chosen": d.chosen,
                    "rationale": d.rationale,
                }
                for d in self.decisions
            ],
            "artifacts": [
                {
                    "type": a.artifact_type,
                    "path": a.path,
                    "description": a.description,
                }
                for a in self.artifacts
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）。"""
        return {
            "session_id": self.session_id,
            "dataset_name": self.dataset_name,
            "findings": [
                {
                    "category": f.category,
                    "summary": f.summary,
                    "detail": f.detail,
                    "confidence": f.confidence,
                    "timestamp": f.timestamp,
                    "ltm_id": f.ltm_id,
                }
                for f in self.findings
            ],
            "statistics": [
                {
                    "test_name": s.test_name,
                    "test_statistic": s.test_statistic,
                    "p_value": s.p_value,
                    "degrees_of_freedom": s.degrees_of_freedom,
                    "effect_size": s.effect_size,
                    "effect_type": s.effect_type,
                    "confidence_interval_lower": s.confidence_interval_lower,
                    "confidence_interval_upper": s.confidence_interval_upper,
                    "confidence_level": s.confidence_level,
                    "significant": s.significant,
                    "metadata": s.metadata,
                    "ltm_id": s.ltm_id,
                }
                for s in self.statistics
            ],
            "decisions": [
                {
                    "decision_type": d.decision_type,
                    "chosen": d.chosen,
                    "alternatives": d.alternatives,
                    "rationale": d.rationale,
                    "confidence": d.confidence,
                    "timestamp": d.timestamp,
                    "ltm_id": d.ltm_id,
                }
                for d in self.decisions
            ],
            "artifacts": [
                {
                    "artifact_type": a.artifact_type,
                    "path": a.path,
                    "description": a.description,
                    "metadata": a.metadata,
                    "timestamp": a.timestamp,
                }
                for a in self.artifacts
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisMemory:
        """从字典恢复 AnalysisMemory。"""
        return cls(
            session_id=str(data.get("session_id", "")).strip(),
            dataset_name=str(data.get("dataset_name", "")).strip(),
            findings=[
                Finding(
                    category=str(item.get("category", "")),
                    summary=str(item.get("summary", "")),
                    detail=str(item.get("detail", "")),
                    confidence=float(item.get("confidence", 1.0)),
                    timestamp=float(item.get("timestamp", 0.0)),
                    ltm_id=str(item.get("ltm_id", "")),
                )
                for item in data.get("findings", [])
                if isinstance(item, dict)
            ],
            statistics=[
                StatisticResult(
                    test_name=str(item.get("test_name", "")),
                    test_statistic=(
                        float(item["test_statistic"])
                        if item.get("test_statistic") is not None
                        else None
                    ),
                    p_value=float(item["p_value"]) if item.get("p_value") is not None else None,
                    degrees_of_freedom=(
                        int(item["degrees_of_freedom"])
                        if item.get("degrees_of_freedom") is not None
                        else None
                    ),
                    effect_size=(
                        float(item["effect_size"]) if item.get("effect_size") is not None else None
                    ),
                    effect_type=str(item.get("effect_type", "")),
                    confidence_interval_lower=(
                        float(item["confidence_interval_lower"])
                        if item.get("confidence_interval_lower") is not None
                        else None
                    ),
                    confidence_interval_upper=(
                        float(item["confidence_interval_upper"])
                        if item.get("confidence_interval_upper") is not None
                        else None
                    ),
                    confidence_level=float(item.get("confidence_level", 0.95)),
                    significant=(
                        bool(item["significant"])
                        if isinstance(item.get("significant"), bool)
                        else None
                    ),
                    metadata=(
                        dict(item.get("metadata", {}))
                        if isinstance(item.get("metadata"), dict)
                        else {}
                    ),
                    ltm_id=str(item.get("ltm_id", "")),
                )
                for item in data.get("statistics", [])
                if isinstance(item, dict)
            ],
            decisions=[
                Decision(
                    decision_type=str(item.get("decision_type", "")),
                    chosen=str(item.get("chosen", "")),
                    alternatives=[
                        str(option)
                        for option in item.get("alternatives", [])
                        if isinstance(option, str)
                    ],
                    rationale=str(item.get("rationale", "")),
                    confidence=float(item.get("confidence", 1.0)),
                    timestamp=float(item.get("timestamp", 0.0)),
                    ltm_id=str(item.get("ltm_id", "")),
                )
                for item in data.get("decisions", [])
                if isinstance(item, dict)
            ],
            artifacts=[
                Artifact(
                    artifact_type=str(item.get("artifact_type", "")),
                    path=str(item.get("path", "")),
                    description=str(item.get("description", "")),
                    metadata=(
                        dict(item.get("metadata", {}))
                        if isinstance(item.get("metadata"), dict)
                        else {}
                    ),
                    timestamp=float(item.get("timestamp", 0.0)),
                )
                for item in data.get("artifacts", [])
                if isinstance(item, dict)
            ],
            created_at=float(data.get("created_at", __import__("time").time())),
            updated_at=float(data.get("updated_at", __import__("time").time())),
        )

    def get_context_prompt(self) -> str:
        """获取用于系统提示词的记忆描述。"""
        parts: list[str] = []

        if self.findings:
            parts.append(f"**关键发现**（{len(self.findings)} 项）：")
            for f in self.findings[:5]:  # 最多显示 5 项
                parts.append(f"- {f.category}: {f.summary}")

        if self.statistics:
            parts.append(f"**统计结果**（{len(self.statistics)} 项）：")
            for s in self.statistics[:5]:  # 最多显示 5 项
                if s.significant is True:
                    sig = "显著"
                elif s.significant is False:
                    sig = "不显著"
                else:
                    sig = "未判定"
                nums: list[str] = []
                if s.test_statistic is not None:
                    nums.append(f"统计量={s.test_statistic:.4f}")
                if s.p_value is not None:
                    nums.append(f"p={s.p_value:.4f}")
                if s.effect_size is not None:
                    label = s.effect_type or "效应量"
                    nums.append(f"{label}={s.effect_size:.4f}")
                sample_size = (
                    s.metadata.get("sample_size") if isinstance(s.metadata, dict) else None
                )
                if isinstance(sample_size, int):
                    nums.append(f"n={sample_size}")
                num_str = f"（{'，'.join(nums)}）" if nums else ""
                pairwise = s.metadata.get("pairwise") if isinstance(s.metadata, dict) else None
                if isinstance(pairwise, list) and pairwise:
                    formatted_pairs: list[str] = []
                    for pair in pairwise[:3]:
                        if not isinstance(pair, dict):
                            continue
                        left = str(pair.get("var_a", "")).strip()
                        right = str(pair.get("var_b", "")).strip()
                        coefficient = pair.get("coefficient")
                        p_value = pair.get("p_value")
                        if not left or not right:
                            continue
                        pair_parts: list[str] = [f"{left} vs {right}"]
                        if isinstance(coefficient, (int, float)):
                            pair_parts.append(f"r={float(coefficient):.4f}")
                        if isinstance(p_value, (int, float)):
                            pair_parts.append(f"p={float(p_value):.4g}")
                        pair_sig = pair.get("significant")
                        if isinstance(pair_sig, bool):
                            pair_parts.append("显著" if pair_sig else "不显著")
                        formatted_pairs.append("，".join(pair_parts))
                    if formatted_pairs:
                        parts.append(
                            f"- {s.test_name}: {sig}{num_str}；" + "；".join(formatted_pairs)
                        )
                        continue
                parts.append(f"- {s.test_name}: {sig}{num_str}")

        if self.decisions:
            parts.append(f"**方法决策**（{len(self.decisions)} 项）：")
            for d in self.decisions[:3]:  # 最多显示 3 项
                parts.append(f"- {d.decision_type}: 选择 {d.chosen}")

        if self.artifacts:
            parts.append(f"**产出文件**（{len(self.artifacts)} 个）")

        if not parts:
            return f"暂无分析记录（数据集: {self.dataset_name}）"

        return "\n".join(parts)


# ---- 会话记忆注册表 ----

_analysis_memories: dict[str, AnalysisMemory] = {}


def save_analysis_memory(memory: AnalysisMemory) -> None:
    """将 AnalysisMemory 持久化到磁盘。"""
    if not session_persistence_enabled(memory.session_id):
        return
    path = _analysis_memory_path(memory.session_id, memory.dataset_name)
    path.write_text(
        json.dumps(memory.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_analysis_memory(session_id: str, dataset_name: str) -> AnalysisMemory | None:
    """从磁盘加载 AnalysisMemory。"""
    if not session_persistence_enabled(session_id):
        return None
    path = _analysis_memory_dir(session_id, create=False) / f"{quote(dataset_name, safe='')}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("读取 AnalysisMemory 失败: session=%s dataset=%s", session_id, dataset_name)
        return None
    if not isinstance(payload, dict):
        return None
    memory = AnalysisMemory.from_dict(payload)
    if not memory.session_id:
        memory.session_id = session_id
    if not memory.dataset_name:
        memory.dataset_name = dataset_name
    return memory


def get_analysis_memory(session_id: str, dataset_name: str) -> AnalysisMemory:
    """获取或创建分析记忆。"""
    key = f"{session_id}:{dataset_name}"
    if key not in _analysis_memories:
        loaded = load_analysis_memory(session_id, dataset_name)
        _analysis_memories[key] = loaded or AnalysisMemory(
            session_id=session_id,
            dataset_name=dataset_name,
        )
    return _analysis_memories[key]


def remove_analysis_memory(session_id: str, dataset_name: str) -> None:
    """移除分析记忆。"""
    key = f"{session_id}:{dataset_name}"
    _analysis_memories.pop(key, None)
    if session_persistence_enabled(session_id):
        path = _analysis_memory_path(session_id, dataset_name)
        if path.exists():
            path.unlink()


def list_session_analysis_memories(session_id: str) -> list[AnalysisMemory]:
    """列出会话的所有分析记忆（非空的）。"""
    if session_persistence_enabled(session_id):
        memory_dir = _analysis_memory_dir(session_id, create=False)
        if memory_dir.exists():
            for path in sorted(memory_dir.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning("读取 AnalysisMemory 文件失败: %s", path)
                    continue
                if not isinstance(payload, dict):
                    continue
                dataset_name = str(payload.get("dataset_name", "")).strip()
                if not dataset_name:
                    continue
                key = f"{session_id}:{dataset_name}"
                if key not in _analysis_memories:
                    _analysis_memories[key] = AnalysisMemory.from_dict(payload)

    result: list[AnalysisMemory] = []
    prefix = f"{session_id}:"
    for key, mem in _analysis_memories.items():
        if key.startswith(prefix) and (mem.findings or mem.statistics or mem.decisions):
            result.append(mem)
    return result


def clear_session_analysis_memories(session_id: str) -> None:
    """清除会话的所有分析记忆。"""
    clear_session_analysis_memory_cache(session_id)
    if session_persistence_enabled(session_id):
        memory_dir = settings.sessions_dir / session_id / "analysis_memories"
        if memory_dir.exists():
            for path in memory_dir.glob("*.json"):
                path.unlink()
            memory_dir.rmdir()


def clear_session_analysis_memory_cache(session_id: str) -> None:
    """仅清除会话的 AnalysisMemory 内存缓存。"""
    keys_to_remove = [k for k in _analysis_memories if k.startswith(f"{session_id}:")]
    for key in keys_to_remove:
        _analysis_memories.pop(key, None)
