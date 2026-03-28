/**
 * Skill 执行进度面板。
 */
import {
 AlertTriangle,
 CheckCircle2,
 CircleDashed,
 Clock3,
 Loader2,
 ShieldCheck,
 SkipForward,
 Sparkles,
 XCircle,
} from "lucide-react";
import { useStore, type OutputLevel, type SkillExecutionStep } from "../store";
import Button from "./ui/Button";

function formatDuration(durationMs: number | null): string {
 if (durationMs == null || durationMs <= 0) return "进行中";
 if (durationMs < 1000) return `${durationMs}ms`;
 return `${(durationMs / 1000).toFixed(durationMs >= 10000 ? 0 : 1)}s`;
}

function statusMeta(status: SkillExecutionStep["status"]) {
 switch (status) {
 case "completed":
 return {
 label: "已完成",
 icon: <CheckCircle2 size={14} className="text-[var(--success)]" />,
 itemClass: "border-[var(--success)] bg-[var(--accent-subtle)]/70 text-[var(--success)]",
 };
 case "started":
 return {
 label: "执行中",
 icon: <Loader2 size={14} className="animate-spin text-[var(--domain-profile)]" />,
 itemClass: "border-[var(--domain-profile)] bg-[var(--accent-subtle)]/80 text-[var(--domain-profile)]",
 };
 case "review_required":
 return {
 label: "待确认",
 icon: <AlertTriangle size={14} className="text-[var(--warning)]" />,
 itemClass: "border-[var(--warning)] bg-[var(--accent-subtle)]/80 text-[var(--warning)]",
 };
 case "failed":
 return {
 label: "失败",
 icon: <XCircle size={14} className="text-[var(--error)]" />,
 itemClass: "border-[var(--error)] bg-[var(--accent-subtle)]/80 text-[var(--error)]",
 };
 case "skipped":
 return {
 label: "跳过",
 icon: <SkipForward size={14} className="text-[var(--text-muted)]" />,
 itemClass: "border-[var(--border-default)] bg-[var(--bg-elevated)]/80 text-[var(--text-secondary)] dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-muted)]",
 };
 default:
 return {
 label: "等待中",
 icon: <CircleDashed size={14} className="text-[var(--text-muted)]" />,
 itemClass: "border-[var(--border-default)] bg-[var(--bg-base)] text-[var(--text-secondary)] dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-muted)]",
 };
 }
}

function outputLevelMeta(outputLevel: OutputLevel | null) {
 switch (outputLevel) {
 case "o1":
 return { label: "建议级", className: "bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-muted)] dark:border-[var(--border-default)]" };
 case "o2":
 return { label: "草稿级", className: "bg-[var(--accent-subtle)] text-[var(--domain-profile)] border-[var(--domain-profile)]" };
 case "o3":
 return { label: "可审阅级", className: "bg-[var(--accent-subtle)] text-[var(--success)] border-[var(--success)] dark:text-[var(--success)]" };
 case "o4":
 return { label: "可导出级", className: "bg-[var(--accent-subtle)] text-[var(--domain-analysis)] border-[var(--domain-analysis)]" };
 default:
 return null;
 }
}

export default function SkillProgressPanel() {
 const skillExecution = useStore((state) => state.skillExecution);
 const submitSkillReviewDecision = useStore((state) => state.submitSkillReviewDecision);

 if (!skillExecution || skillExecution.steps.length === 0) {
 return null;
 }

 const outputLevel = outputLevelMeta(skillExecution.outputLevel);
 const isFinished = skillExecution.activeSkill === null && skillExecution.overallStatus !== null;

 return (
 <section className="mb-5 rounded-[24px] border border-[var(--border-default)] bg-[var(--bg-base)]/90 dark:bg-[var(--bg-elevated)] shadow-[0_20px_60px_-42px_rgba(15,23,42,0.5)]">
 <div className="border-b border-[var(--border-default)] bg-[linear-gradient(135deg,rgba(240,249,255,0.95),rgba(248,250,252,0.95))] dark:from-slate-800 dark:to-slate-800 px-4 py-4">
 <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--text-secondary)]">
 <span className="inline-flex h-8 w-8 items-center justify-center rounded-2xl bg-[var(--accent-subtle)] text-[var(--domain-profile)]">
 <Sparkles size={15} />
 </span>
 <span className="font-semibold text-[var(--text-primary)]">
 {skillExecution.skillName ?? skillExecution.activeSkill ?? "Skill 执行"}
 </span>
 {skillExecution.overallStatus && (
 <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-base)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
 {skillExecution.overallStatus === "completed"
 ? "已完成"
 : skillExecution.overallStatus === "partial"
 ? "部分完成"
 : "执行失败"}
 </span>
 )}
 </div>
 <div className="mt-3 flex flex-wrap gap-2 text-xs">
 <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[var(--text-secondary)]">
 步骤 {skillExecution.completedSteps + skillExecution.skippedSteps + skillExecution.failedSteps}/{skillExecution.totalSteps ?? skillExecution.steps.length}
 </span>
 {skillExecution.trustCeiling && (
 <span className="inline-flex items-center gap-1 rounded-full border border-[var(--success)] bg-[var(--accent-subtle)] px-2.5 py-1 text-[var(--success)] dark:text-[var(--success)]">
 <ShieldCheck size={12} />
 信任上限 {skillExecution.trustCeiling.toUpperCase()}
 </span>
 )}
 {outputLevel && (
 <span className={`rounded-full border px-2.5 py-1 ${outputLevel.className}`}>
 输出 {skillExecution.outputLevel?.toUpperCase()} · {outputLevel.label}
 </span>
 )}
 {skillExecution.totalDurationMs != null && (
 <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-[var(--bg-base)] px-2.5 py-1 text-[var(--text-secondary)]">
 <Clock3 size={12} />
 总耗时 {formatDuration(skillExecution.totalDurationMs)}
 </span>
 )}
 </div>
 </div>

 <div className="space-y-2 px-4 py-4">
 {skillExecution.steps.map((step) => {
 const meta = statusMeta(step.status);
 const stepOutputLevel = outputLevelMeta(step.outputLevel);
 const waitingDecision = skillExecution.submittingReviewStepId === step.stepId;

 return (
 <article
 key={step.stepId}
 className={`rounded-2xl border px-3 py-3 transition-colors ${meta.itemClass}`}
 >
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0 flex-1">
 <div className="flex items-center gap-2 text-sm font-medium">
 {meta.icon}
 <span className="truncate">{step.stepName}</span>
 <span className="rounded-full border border-black/5 dark:border-white/10 bg-[var(--bg-base)]/70 px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
 {meta.label}
 </span>
 </div>
 <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
 <span>{step.stepId}</span>
 {step.trustLevel && <span>信任 {step.trustLevel.toUpperCase()}</span>}
 {step.durationMs != null && <span>耗时 {formatDuration(step.durationMs)}</span>}
 {stepOutputLevel && (
 <span className={`rounded-full border px-2 py-0.5 ${stepOutputLevel.className}`}>
 {step.outputLevel?.toUpperCase()}
 </span>
 )}
 </div>
 {step.outputSummary && (
 <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{step.outputSummary}</p>
 )}
 {step.errorMessage && (
 <p className="mt-2 rounded-xl border border-[var(--error)] bg-[var(--bg-base)]/80/80 px-2.5 py-2 text-xs text-[var(--error)]">
 {step.errorMessage}
 </p>
 )}
 </div>
 {step.status === "review_required" && (
 <div className="flex shrink-0 flex-col gap-2">
 <Button
 type="button"
 variant="primary"
 onClick={() => submitSkillReviewDecision(step.stepId, "confirm")}
 disabled={waitingDecision}
 className="rounded-xl px-3 py-2"
 >
 确认继续
 </Button>
 <Button
 type="button"
 variant="secondary"
 onClick={() => submitSkillReviewDecision(step.stepId, "cancel")}
 disabled={waitingDecision}
 className="rounded-xl px-3 py-2"
 >
 取消
 </Button>
 </div>
 )}
 </div>
 </article>
 );
 })}
 </div>

 {isFinished && (
 <div className="border-t border-[var(--border-default)] px-4 py-3 text-xs text-[var(--text-secondary)]">
 本次 Skill 执行已结束，后续新步骤会自动覆盖当前面板。
 </div>
 )}
 </section>
 );
}
