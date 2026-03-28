import { useMemo } from "react";
import { useStore } from "../store";

const STATUS_LABELS: Record<string, string> = {
 queued: "已排队",
 running: "执行中",
 retrying: "重试中",
 blocked: "已阻塞",
 completed: "已完成",
 failed: "失败",
};

export default function DeepTaskProgressCard() {
 const deepTaskState = useStore((s) => s.deepTaskState);
 const activeRecipeId = useStore((s) => s.activeRecipeId);
 const analysisPlanProgress = useStore((s) => s.analysisPlanProgress);
 const recipes = useStore((s) => s.recipes);

 const recipeName = useMemo(
 () => recipes.find((recipe) => recipe.recipe_id === activeRecipeId)?.name ?? "Deep Task",
 [activeRecipeId, recipes],
 );

 if (!deepTaskState || !analysisPlanProgress) {
 return null;
 }

 return (
 <div className="mb-4 rounded-[24px] border border-[var(--success)] bg-[var(--accent-subtle)]/70 p-4 shadow-sm">
 <div className="flex flex-wrap items-center justify-between gap-3">
 <div>
 <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--success)]">
 {recipeName}
 </div>
 <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
 Step {deepTaskState.current_step_index} / {deepTaskState.total_steps}
 {" ·"}
 {deepTaskState.current_step_title}
 </div>
 </div>
 <div className="rounded-full border border-[var(--success)] bg-[var(--bg-base)] px-3 py-1 text-xs font-medium text-[var(--success)]">
 {STATUS_LABELS[deepTaskState.status] ?? deepTaskState.status}
 </div>
 </div>
 {deepTaskState.next_hint && (
 <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{deepTaskState.next_hint}</p>
 )}
 {deepTaskState.retry_count > 0 && (
 <div className="mt-2 text-xs text-[var(--warning)]">
 已触发重试 {deepTaskState.retry_count} 次
 </div>
 )}
 {deepTaskState.block_reason && (
 <div className="mt-2 text-xs text-[var(--error)]">{deepTaskState.block_reason}</div>
 )}
 <div className="mt-4 grid gap-2 md:grid-cols-3">
 {analysisPlanProgress.steps.map((step) => (
 <div
 key={step.id}
 className={`rounded-2xl border px-3 py-3 text-xs ${
 step.status === "done"
 ? "border-[var(--success)] bg-[var(--bg-base)] text-[var(--success)]"
 : step.status === "failed" || step.status === "blocked"
 ? "border-[var(--error)] bg-[var(--bg-base)] text-[var(--error)]"
 : step.status === "in_progress"
 ? "border-[var(--warning)] bg-[var(--bg-base)] text-[var(--warning)]"
 : "border-[var(--border-default)] bg-[var(--bg-base)] text-[var(--text-secondary)]"
 }`}
 >
 <div className="font-semibold">Step {step.id}</div>
 <div className="mt-1">{step.title}</div>
 </div>
 ))}
 </div>
 </div>
 );
}
