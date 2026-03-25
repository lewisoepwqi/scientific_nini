"""Claim 校验流水线回归测试。"""

from __future__ import annotations

import asyncio

from nini.agent.session import Session
from nini.claim_verification import verify_candidate
from nini.models import ClaimVerificationCandidate, ClaimVerificationStatus, SourceRecord
from nini.tools.registry import create_default_tool_registry
from nini.workspace import WorkspaceManager


def test_verify_candidate_distinguishes_verified_pending_and_conflicted() -> None:
    verified = verify_candidate(
        ClaimVerificationCandidate(
            claim_id="claim_verified",
            claim_summary="实验组显著提高了指标。",
            sources=[
                SourceRecord(
                    source_id="knowledge:1",
                    source_type="knowledge_document",
                    title="来源一",
                    acquisition_method="hybrid",
                    excerpt="实验组显著提高了指标。",
                    metadata={"claim_stance": "support"},
                ),
                SourceRecord(
                    source_id="knowledge:2",
                    source_type="knowledge_document",
                    title="来源二",
                    acquisition_method="hybrid",
                    excerpt="结果支持实验组指标升高。",
                    metadata={"claim_stance": "support"},
                ),
            ],
        )
    )
    assert verified.verification_status == ClaimVerificationStatus.VERIFIED

    pending = verify_candidate(
        ClaimVerificationCandidate(
            claim_id="claim_pending",
            claim_summary="实验组显著提高了指标。",
            sources=[
                SourceRecord(
                    source_id="knowledge:3",
                    source_type="knowledge_document",
                    title="来源三",
                    acquisition_method="hybrid",
                    excerpt="实验组显著提高了指标。",
                    metadata={"claim_stance": "support"},
                )
            ],
        )
    )
    assert pending.verification_status == ClaimVerificationStatus.PENDING_VERIFICATION

    conflicted = verify_candidate(
        ClaimVerificationCandidate(
            claim_id="claim_conflicted",
            claim_summary="实验组显著提高了指标。",
            sources=[
                SourceRecord(
                    source_id="knowledge:4",
                    source_type="knowledge_document",
                    title="支持来源",
                    acquisition_method="hybrid",
                    excerpt="实验组显著提高了指标。",
                    metadata={"claim_stance": "support"},
                ),
                SourceRecord(
                    source_id="knowledge:5",
                    source_type="knowledge_document",
                    title="冲突来源",
                    acquisition_method="hybrid",
                    excerpt="实验组未显著提高指标。",
                    metadata={"claim_stance": "oppose"},
                ),
            ],
        )
    )
    assert conflicted.verification_status == ClaimVerificationStatus.CONFLICTED
    assert conflicted.conflict_summary


def test_report_session_renders_verified_summary_and_status_sections() -> None:
    registry = create_default_tool_registry()
    session = Session()
    manager = WorkspaceManager(session.id)

    create_result = asyncio.run(
        registry.execute(
            "report_session",
            session=session,
            operation="create",
            report_id="report_claim_verify",
            title="Claim 校验报告",
            sections=[
                {"key": "summary", "title": "分析摘要", "content": "草稿摘要"},
                {"key": "claim_verified", "title": "结论 A", "content": "实验组显著提高了指标。"},
                {"key": "claim_pending", "title": "结论 B", "content": "样本外结论尚待确认。"},
                {"key": "claim_conflicted", "title": "结论 C", "content": "另一项指标存在提升。"},
            ],
            evidence_blocks=[
                {
                    "claim_id": "claim_verified",
                    "claim_summary": "实验组显著提高了指标。",
                    "section_key": "claim_verified",
                    "sources": [
                        {
                            "source_id": "knowledge:1",
                            "source_type": "knowledge_document",
                            "title": "来源一",
                            "acquisition_method": "hybrid",
                            "excerpt": "实验组显著提高了指标。",
                            "metadata": {"claim_stance": "support"},
                        },
                        {
                            "source_id": "knowledge:2",
                            "source_type": "knowledge_document",
                            "title": "来源二",
                            "acquisition_method": "hybrid",
                            "excerpt": "结果支持实验组指标升高。",
                            "metadata": {"claim_stance": "support"},
                        },
                    ],
                },
                {
                    "claim_id": "claim_pending",
                    "claim_summary": "样本外结论尚待确认。",
                    "section_key": "claim_pending",
                    "sources": [
                        {
                            "source_id": "knowledge:3",
                            "source_type": "knowledge_document",
                            "title": "来源三",
                            "acquisition_method": "hybrid",
                            "excerpt": "目前只有单一来源提到该结论。",
                            "metadata": {"claim_stance": "support"},
                        }
                    ],
                },
                {
                    "claim_id": "claim_conflicted",
                    "claim_summary": "另一项指标存在提升。",
                    "section_key": "claim_conflicted",
                    "sources": [
                        {
                            "source_id": "knowledge:4",
                            "source_type": "knowledge_document",
                            "title": "支持来源",
                            "acquisition_method": "hybrid",
                            "excerpt": "该指标显著提高。",
                            "metadata": {"claim_stance": "support"},
                        },
                        {
                            "source_id": "knowledge:5",
                            "source_type": "knowledge_document",
                            "title": "冲突来源",
                            "acquisition_method": "hybrid",
                            "excerpt": "该指标未显著提高。",
                            "metadata": {"claim_stance": "oppose"},
                        },
                    ],
                },
            ],
        )
    )
    assert create_result["success"] is True, create_result

    record = create_result["data"]["record"]
    assert record["evidence_blocks"][0]["verification_status"] == "verified"
    assert record["evidence_blocks"][1]["verification_status"] == "pending_verification"
    assert record["evidence_blocks"][2]["verification_status"] == "conflicted"

    markdown_path = manager.resolve_workspace_path(record["markdown_path"], allow_missing=False)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "以下摘要仅纳入已验证结论。" in markdown
    assert "### 已验证结论摘要" in markdown
    assert "实验组显著提高了指标。" in markdown
    assert "## 待验证结论" in markdown
    assert "## 证据冲突结论" in markdown
    assert "验证状态: 已验证" in markdown
