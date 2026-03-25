"""Claim 校验流水线的最小规则实现。"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from nini.models import (
    ClaimVerificationCandidate,
    ClaimVerificationStatus,
    EvidenceBlock,
    ReportSessionRecord,
    SourceRecord,
)

_POSITIVE_CUES = {
    "increase",
    "increased",
    "higher",
    "improve",
    "improved",
    "significant",
    "elevated",
    "显著",
    "升高",
    "提高",
    "增加",
    "支持",
}
_NEGATIVE_CUES = {
    "decrease",
    "decreased",
    "lower",
    "reduced",
    "reduce",
    "no significant",
    "not significant",
    "contradict",
    "conflict",
    "下降",
    "降低",
    "未显著",
    "不支持",
    "冲突",
    "相反",
}


def extract_verification_candidates(
    record: ReportSessionRecord,
) -> list[ClaimVerificationCandidate]:
    """从报告记录中抽取可进入校验流水线的结论。"""
    candidates: list[ClaimVerificationCandidate] = []
    for block in record.evidence_blocks:
        claim_id = str(block.claim_id or "").strip()
        claim_summary = str(block.claim_summary or "").strip()
        if not claim_id or not claim_summary:
            continue
        candidates.append(
            ClaimVerificationCandidate(
                claim_id=claim_id,
                claim_summary=claim_summary,
                section_key=block.section_key,
                sources=block.sources,
            )
        )
    return candidates


def apply_claim_verification(record: ReportSessionRecord) -> ReportSessionRecord:
    """对报告中的证据块执行状态判定。"""
    candidate_map = {
        candidate.claim_id: verify_candidate(candidate)
        for candidate in extract_verification_candidates(record)
    }
    for block in record.evidence_blocks:
        verified = candidate_map.get(block.claim_id)
        if verified is None:
            continue
        block.verification_status = verified.verification_status
        block.confidence_score = verified.confidence_score
        block.reason_summary = verified.reason_summary
        block.conflict_summary = verified.conflict_summary
    return record


def verify_candidate(candidate: ClaimVerificationCandidate) -> EvidenceBlock:
    """对单条结论执行最小规则校验。"""
    sources = list(candidate.sources)
    if not sources:
        return _build_result(
            candidate,
            status=ClaimVerificationStatus.PENDING_VERIFICATION,
            confidence=0.15,
            reason="缺少来源记录，无法完成校验。",
        )

    stances = [_infer_source_stance(candidate.claim_summary, source) for source in sources]
    counts = Counter(stances)
    support_count = counts.get("support", 0)
    oppose_count = counts.get("oppose", 0)
    unknown_count = counts.get("unknown", 0)

    if support_count > 0 and oppose_count > 0:
        conflict_sources = [
            source.title
            for source, stance in zip(sources, stances, strict=False)
            if stance == "oppose"
        ]
        return _build_result(
            candidate,
            status=ClaimVerificationStatus.CONFLICTED,
            confidence=0.2,
            reason="来源之间存在关键事实冲突。",
            conflict_summary=f"冲突来源：{', '.join(conflict_sources)}",
        )

    if support_count >= 2 and oppose_count == 0:
        confidence = min(0.95, 0.55 + support_count * 0.15)
        return _build_result(
            candidate,
            status=ClaimVerificationStatus.VERIFIED,
            confidence=confidence,
            reason=f"已有 {support_count} 个一致来源支持该结论。",
        )

    if support_count == 1 and len(sources) == 1:
        return _build_result(
            candidate,
            status=ClaimVerificationStatus.PENDING_VERIFICATION,
            confidence=0.45,
            reason="仅有单一来源支持，尚不足以视为已验证。",
        )

    if unknown_count == len(sources):
        return _build_result(
            candidate,
            status=ClaimVerificationStatus.PENDING_VERIFICATION,
            confidence=0.3,
            reason="来源已绑定，但当前规则无法判断其是否足以支持结论。",
        )

    return _build_result(
        candidate,
        status=ClaimVerificationStatus.PENDING_VERIFICATION,
        confidence=0.4,
        reason="已有部分支持来源，但仍缺少足够一致证据。",
    )


def _infer_source_stance(claim_summary: str, source: SourceRecord) -> str:
    metadata_stance = str(source.metadata.get("claim_stance", "")).strip().lower()
    if metadata_stance in {"support", "oppose", "unknown"}:
        return metadata_stance

    claim_polarity = _infer_polarity([claim_summary])
    source_polarity = _infer_polarity(
        [source.title, source.excerpt, str(source.metadata.get("summary", ""))]
    )
    if source_polarity == "unknown":
        return "unknown"
    if claim_polarity == "unknown":
        return "support"
    if claim_polarity == source_polarity:
        return "support"
    return "oppose"


def _infer_polarity(chunks: Iterable[str]) -> str:
    text = " ".join(chunk.lower() for chunk in chunks if chunk).strip()
    if not text:
        return "unknown"

    positive_hits = sum(1 for cue in _POSITIVE_CUES if cue in text)
    negative_hits = sum(1 for cue in _NEGATIVE_CUES if cue in text)
    if positive_hits == negative_hits:
        return "unknown"
    return "positive" if positive_hits > negative_hits else "negative"


def _build_result(
    candidate: ClaimVerificationCandidate,
    *,
    status: ClaimVerificationStatus,
    confidence: float,
    reason: str,
    conflict_summary: str | None = None,
) -> EvidenceBlock:
    return EvidenceBlock(
        claim_id=candidate.claim_id,
        claim_summary=candidate.claim_summary,
        section_key=candidate.section_key,
        sources=list(candidate.sources),
        verification_status=status,
        confidence_score=confidence,
        reason_summary=reason,
        conflict_summary=conflict_summary,
    )
