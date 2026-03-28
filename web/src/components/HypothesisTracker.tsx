/**
 * HypothesisTracker —— 假设驱动推理状态可视化
 *
 * 展示正在推理中的假设列表，含置信度进度条、状态标签和证据链折叠展开。
 * hypotheses 为空时返回 null，不渲染任何 DOM 元素。
 */
import { useState } from "react";
import { useStore } from "../store";
import type { HypothesisInfo } from "../store/types";
import Button from "./ui/Button";

const STATUS_STYLES: Record<HypothesisInfo["status"], string> = {
 pending: "bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent)]",
 validated: "bg-[var(--accent-subtle)] border-[var(--success)] text-[var(--success)]",
 refuted: "bg-[var(--accent-subtle)] border-[var(--error)] text-[var(--error)]",
 revised: "bg-[var(--accent-subtle)] border-[var(--warning)] text-[var(--warning)]",
};

const STATUS_LABEL: Record<HypothesisInfo["status"], string> = {
 pending: "待验证",
 validated: "已验证",
 refuted: "已证伪",
 revised: "已修正",
};

const STATUS_BAR: Record<HypothesisInfo["status"], string> = {
 pending: "bg-[var(--accent)]",
 validated: "bg-[var(--success)]",
 refuted: "bg-[var(--error)]",
 revised: "bg-[var(--warning)]",
};

interface HypothesisCardProps {
 hypothesis: HypothesisInfo;
}

function HypothesisCard({ hypothesis }: HypothesisCardProps) {
 const [expanded, setExpanded] = useState(false);
 const hasEvidence = hypothesis.evidenceFor.length > 0 || hypothesis.evidenceAgainst.length > 0;
 const confidencePct = Math.round(hypothesis.confidence * 100);

 return (
 <div className={`rounded-lg border px-3 py-2.5 ${STATUS_STYLES[hypothesis.status]}`}>
 {/* 标题行 */}
 <div className="flex items-start justify-between gap-2">
 <p className="flex-1 text-xs font-medium leading-snug">{hypothesis.content}</p>
 <span className="flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold border">
 {STATUS_LABEL[hypothesis.status]}
 </span>
 </div>

 {/* 置信度进度条 */}
 <div className="mt-1.5 flex items-center gap-2">
 <div className="flex-1 h-1.5 rounded-full bg-black/10">
 <div
 className={`h-full rounded-full transition-all duration-300 ${STATUS_BAR[hypothesis.status]}`}
 style={{ width: `${confidencePct}%` }}
 />
 </div>
 <span className="text-[10px] opacity-60 tabular-nums">{confidencePct}%</span>
 </div>

 {/* 证据链折叠展开 */}
 {hasEvidence && (
 <Button
 variant="ghost"
 onClick={() => setExpanded((v) => !v)}
 className="mt-1.5 text-[10px] opacity-60 hover:opacity-100 underline"
 >
 {expanded ? "收起证据" : `查看证据（${hypothesis.evidenceFor.length + hypothesis.evidenceAgainst.length}）`}
 </Button>
 )}

 {expanded && (
 <div className="mt-1.5 space-y-1">
 {hypothesis.evidenceFor.length > 0 && (
 <div>
 <p className="text-[10px] font-semibold opacity-70 mb-0.5">支持证据</p>
 <ul className="space-y-0.5">
 {hypothesis.evidenceFor.map((e, i) => (
 <li key={i} className="text-[11px] opacity-80 line-clamp-2">+ {e}</li>
 ))}
 </ul>
 </div>
 )}
 {hypothesis.evidenceAgainst.length > 0 && (
 <div>
 <p className="text-[10px] font-semibold opacity-70 mb-0.5">反驳证据</p>
 <ul className="space-y-0.5">
 {hypothesis.evidenceAgainst.map((e, i) => (
 <li key={i} className="text-[11px] opacity-80 line-clamp-2">- {e}</li>
 ))}
 </ul>
 </div>
 )}
 </div>
 )}
 </div>
 );
}

export default function HypothesisTracker() {
 const hypotheses = useStore((s) => s.hypotheses);
 const currentPhase = useStore((s) => s.currentPhase);
 const iterationCount = useStore((s) => s.iterationCount);

 if (hypotheses.length === 0) {
 return null;
 }

 return (
 <div className="rounded-lg border border-[var(--domain-analysis)] bg-[var(--accent-subtle)]/60 px-4 py-3">
 <div className="mb-2 flex items-center justify-between">
 <p className="text-xs font-medium text-[var(--domain-analysis)]">假设推理中</p>
 <span className="text-[10px] text-[var(--domain-analysis)]">
 阶段：{currentPhase}　轮次：{iterationCount}
 </span>
 </div>
 <div className="space-y-2">
 {hypotheses.map((h) => (
 <HypothesisCard key={h.id} hypothesis={h} />
 ))}
 </div>
 </div>
 );
}
