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
        icon: <CheckCircle2 size={14} className="text-emerald-600" />,
        itemClass: "border-emerald-200 bg-emerald-50/70 text-emerald-950",
      };
    case "started":
      return {
        label: "执行中",
        icon: <Loader2 size={14} className="animate-spin text-sky-600" />,
        itemClass: "border-sky-200 bg-sky-50/80 text-sky-950",
      };
    case "review_required":
      return {
        label: "待确认",
        icon: <AlertTriangle size={14} className="text-amber-600" />,
        itemClass: "border-amber-200 bg-amber-50/80 text-amber-950",
      };
    case "failed":
      return {
        label: "失败",
        icon: <XCircle size={14} className="text-rose-600" />,
        itemClass: "border-rose-200 bg-rose-50/80 text-rose-950",
      };
    case "skipped":
      return {
        label: "跳过",
        icon: <SkipForward size={14} className="text-slate-500" />,
        itemClass: "border-slate-200 bg-slate-50/80 text-slate-700",
      };
    default:
      return {
        label: "等待中",
        icon: <CircleDashed size={14} className="text-slate-400" />,
        itemClass: "border-slate-200 bg-white text-slate-700",
      };
  }
}

function outputLevelMeta(outputLevel: OutputLevel | null) {
  switch (outputLevel) {
    case "o1":
      return { label: "建议级", className: "bg-slate-100 text-slate-700 border-slate-200" };
    case "o2":
      return { label: "草稿级", className: "bg-sky-100 text-sky-700 border-sky-200" };
    case "o3":
      return { label: "可审阅级", className: "bg-emerald-100 text-emerald-700 border-emerald-200" };
    case "o4":
      return { label: "可导出级", className: "bg-violet-100 text-violet-700 border-violet-200" };
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
    <section className="mb-5 rounded-[24px] border border-slate-200/80 bg-white/90 shadow-[0_20px_60px_-42px_rgba(15,23,42,0.5)]">
      <div className="border-b border-slate-200/80 bg-[linear-gradient(135deg,rgba(240,249,255,0.95),rgba(248,250,252,0.95))] px-4 py-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-2xl bg-sky-100 text-sky-700">
            <Sparkles size={15} />
          </span>
          <span className="font-semibold text-slate-900">
            {skillExecution.skillName ?? skillExecution.activeSkill ?? "Skill 执行"}
          </span>
          {skillExecution.overallStatus && (
            <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600">
              {skillExecution.overallStatus === "completed"
                ? "已完成"
                : skillExecution.overallStatus === "partial"
                  ? "部分完成"
                  : "执行失败"}
            </span>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600">
            步骤 {skillExecution.completedSteps + skillExecution.skippedSteps + skillExecution.failedSteps}/{skillExecution.totalSteps ?? skillExecution.steps.length}
          </span>
          {skillExecution.trustCeiling && (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-emerald-700">
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
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-600">
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
          const waitingDecision = skillExecution.pendingReviewStepId === step.stepId;

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
                    <span className="rounded-full border border-black/5 bg-white/70 px-2 py-0.5 text-[11px] font-medium text-slate-500">
                      {meta.label}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
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
                    <p className="mt-2 text-xs leading-5 text-slate-600">{step.outputSummary}</p>
                  )}
                  {step.errorMessage && (
                    <p className="mt-2 rounded-xl border border-rose-200 bg-white/80 px-2.5 py-2 text-xs text-rose-700">
                      {step.errorMessage}
                    </p>
                  )}
                </div>
                {step.status === "review_required" && (
                  <div className="flex shrink-0 flex-col gap-2">
                    <button
                      type="button"
                      onClick={() => submitSkillReviewDecision(step.stepId, "confirm")}
                      disabled={waitingDecision}
                      className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      确认继续
                    </button>
                    <button
                      type="button"
                      onClick={() => submitSkillReviewDecision(step.stepId, "cancel")}
                      disabled={waitingDecision}
                      className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      取消
                    </button>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {isFinished && (
        <div className="border-t border-slate-200/80 px-4 py-3 text-xs text-slate-500">
          本次 Skill 执行已结束，后续新步骤会自动覆盖当前面板。
        </div>
      )}
    </section>
  );
}
