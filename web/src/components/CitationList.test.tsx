import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CitationList from "./CitationList";

describe("CitationList", () => {
 it("应展示最小溯源字段", () => {
 render(
 <CitationList
 retrievals={[
 {
 source: "t 检验方法",
 snippet: "Welch t 检验适合方差不齐场景。",
 score: 0.91,
 sourceId: "knowledge:doc-ttest",
 sourceType: "knowledge_document",
 acquisitionMethod: "hybrid",
 sourceTime: "2026-03-26T12:00:00+00:00",
 accessedAt: "2026-03-26T12:05:00+00:00",
 claimId: "claim_verified",
 verificationStatus: "verified",
 reasonSummary: "已有 2 个一致来源支持该结论。",
 },
 ]}
 />,
 );

 expect(screen.getByText("t 检验方法")).toBeInTheDocument();
 expect(screen.getByText("knowledge_document")).toBeInTheDocument();
 expect(screen.getByText("获取方式：hybrid")).toBeInTheDocument();
 expect(screen.getByText("已验证")).toBeInTheDocument();
 expect(screen.getByText("claim_id：claim_verified")).toBeInTheDocument();
 expect(screen.getByText("来源ID：knowledge:doc-ttest")).toBeInTheDocument();
 expect(screen.getByText(/原因：已有 2 个一致来源支持该结论。/u)).toBeInTheDocument();
 expect(screen.getByText(/来源时间：/u)).toBeInTheDocument();
 expect(screen.getByText(/获取时间：/u)).toBeInTheDocument();
 });
});
