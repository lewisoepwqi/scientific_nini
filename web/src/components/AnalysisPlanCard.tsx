/**
 * 分析计划卡片组件 —— 渲染结构化步骤列表或回退 Markdown 展示。
 */
import { useState } from "react";
import {
 Lightbulb,
 ChevronDown,
 ChevronRight,
 Circle,
 Loader2,
 CheckCircle2,
 SkipForward,
 XCircle,
} from "lucide-react";
import type { AnalysisPlanData } from "../store";
import LazyMarkdownContent from "./LazyMarkdownContent";

interface Props {
 content: string;
 analysisPlan?: AnalysisPlanData;
}

function StepIcon({ status }: { status: string }) {
 switch (status) {
 case "in_progress":
 return <Loader2 size={16} className="text-[var(--accent)] animate-spin" />;
 case "done":
 return <CheckCircle2 size={16} className="text-[var(--success)]" />;
 case "failed":
 case "blocked":
 return <XCircle size={16} className="text-[var(--error)]" />;
 case "skipped":
 return <SkipForward size={16} className="text-[var(--text-muted)]" />;
 default:
 return <Circle size={16} className="text-[var(--text-muted)]" />;
 }
}

export default function AnalysisPlanCard({ content, analysisPlan }: Props) {
 const [expanded, setExpanded] = useState(true);

 const steps = analysisPlan?.steps;
 const completedCount = steps?.filter((s) => s.status === "done").length ?? 0;
 const totalCount = steps?.length ?? 0;

 return (
 <div className="flex gap-3 mb-4">
 <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-[var(--accent-subtle)] text-[var(--domain-knowledge)]">
 <Lightbulb size={16} />
 </div>
 <div className="flex-1 min-w-0">
 <div className="rounded-lg border border-[var(--domain-knowledge)] bg-[var(--accent-subtle)]/50 overflow-hidden">
 {/* 标题栏 */}
 <button
 type="button"
 onClick={() => setExpanded(!expanded)}
 className="w-full flex items-center justify-between px-3 py-2 text-sm bg-transparent border-none cursor-pointer focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded"
 >
 <div className="flex items-center gap-2">
 <Lightbulb size={14} className="text-[var(--domain-knowledge)]" />
 <span className="font-medium text-[var(--domain-knowledge)]">
 {steps
 ? `分析计划 (${completedCount}/${totalCount})`
 : "分析思路"}
 </span>
 </div>
 {expanded ? (
 <ChevronDown size={14} className="text-[var(--domain-knowledge)]" />
 ) : (
 <ChevronRight size={14} className="text-[var(--domain-knowledge)]" />
 )}
 </button>

 {/* 内容区 */}
 {expanded && (
 <div className="px-4 pb-3 border-t border-[var(--domain-knowledge)]">
 {steps ? (
 <ul className="mt-2 space-y-1.5">
 {steps.map((step) => (
 <li
 key={step.id}
 className="flex items-start gap-2 text-sm"
 >
 <span className="flex-shrink-0 mt-0.5">
 <StepIcon status={step.status} />
 </span>
 <span
 className={
 step.status === "done"
 ? "text-[var(--text-secondary)] line-through"
 : step.status === "failed" ||
 step.status === "blocked"
 ? "text-[var(--error)]"
 : step.status === "skipped"
 ? "text-[var(--text-muted)] line-through"
 : step.status === "in_progress"
 ? "text-[var(--domain-knowledge)] font-medium"
 : "text-[var(--domain-knowledge)]"
 }
 >
 {step.title}
 </span>
 </li>
 ))}
 </ul>
 ) : (
 <div className="mt-2 text-sm text-[var(--domain-knowledge)] markdown-body prose prose-sm max-w-none prose-headings:text-[var(--domain-knowledge)] prose-strong:text-[var(--domain-knowledge)]">
 <LazyMarkdownContent content={content} />
 </div>
 )}
 </div>
 )}
 </div>
 </div>
 </div>
 );
}
