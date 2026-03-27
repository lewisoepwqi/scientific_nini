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
    <div className="mb-4 rounded-[24px] border border-emerald-200/80 dark:border-emerald-800/80 bg-emerald-50/70 dark:bg-emerald-900/20 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-400">
            {recipeName}
          </div>
          <div className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">
            Step {deepTaskState.current_step_index} / {deepTaskState.total_steps}
            {" · "}
            {deepTaskState.current_step_title}
          </div>
        </div>
        <div className="rounded-full border border-emerald-300 dark:border-emerald-700 bg-white dark:bg-slate-800 px-3 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
          {STATUS_LABELS[deepTaskState.status] ?? deepTaskState.status}
        </div>
      </div>
      {deepTaskState.next_hint && (
        <p className="mt-3 text-sm leading-6 text-slate-600">{deepTaskState.next_hint}</p>
      )}
      {deepTaskState.retry_count > 0 && (
        <div className="mt-2 text-xs text-amber-700">
          已触发重试 {deepTaskState.retry_count} 次
        </div>
      )}
      {deepTaskState.block_reason && (
        <div className="mt-2 text-xs text-rose-700">{deepTaskState.block_reason}</div>
      )}
      <div className="mt-4 grid gap-2 md:grid-cols-3">
        {analysisPlanProgress.steps.map((step) => (
          <div
            key={step.id}
            className={`rounded-2xl border px-3 py-3 text-xs ${
              step.status === "done"
                ? "border-emerald-300 dark:border-emerald-700 bg-white dark:bg-slate-800 text-emerald-700 dark:text-emerald-400"
                : step.status === "failed" || step.status === "blocked"
                  ? "border-rose-200 dark:border-rose-800 bg-white dark:bg-slate-800 text-rose-700 dark:text-rose-400"
                  : step.status === "in_progress"
                    ? "border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-800 text-amber-700 dark:text-amber-400"
                    : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400"
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
