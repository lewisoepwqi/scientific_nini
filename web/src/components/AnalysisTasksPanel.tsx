/**
 * 分析任务面板 —— 展示分析计划进度和步骤列表。
 */
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  FileStack,
  History,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  useStore,
  type AnalysisPlanProgress,
  type PlanStepStatus,
  type AnalysisTaskItem,
  type HarnessRunContextState,
  type CompletionCheckState,
  type HarnessBlockedState,
} from "../store";

function statusLabel(status: PlanStepStatus): string {
  switch (status) {
    case "in_progress":
      return "进行中";
    case "done":
      return "已完成";
    case "blocked":
      return "已阻塞";
    case "failed":
      return "失败";
    default:
      return "未开始";
  }
}

function statusBadgeClass(status: PlanStepStatus): string {
  switch (status) {
    case "in_progress":
      return "bg-blue-100 text-blue-700 border-blue-200";
    case "done":
      return "bg-emerald-100 text-emerald-700 border-emerald-200";
    case "blocked":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "failed":
      return "bg-red-100 text-red-700 border-red-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

function StepStatusIcon({ status }: { status: PlanStepStatus }) {
  switch (status) {
    case "in_progress":
      return <Loader2 size={14} className="text-blue-600 animate-spin" />;
    case "done":
      return <CheckCircle2 size={14} className="text-emerald-600" />;
    case "blocked":
      return <AlertTriangle size={14} className="text-amber-600" />;
    case "failed":
      return <XCircle size={14} className="text-red-600" />;
    default:
      return <Circle size={14} className="text-slate-400" />;
  }
}

function truncateText(text: string, max = 96): string {
  const normalized = text.trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

function HarnessDiagnostics({
  runContext,
  completionCheck,
  blockedState,
}: {
  runContext: HarnessRunContextState | null;
  completionCheck: CompletionCheckState | null;
  blockedState: HarnessBlockedState | null;
}) {
  if (!runContext && !completionCheck && !blockedState) return null;

  return (
    <div className="px-3 py-3 border-b dark:border-slate-700 bg-white dark:bg-slate-800 space-y-2">
      {runContext && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300">
            <FileStack size={13} />
            <span>运行上下文</span>
          </div>
          {runContext.datasets.length > 0 && (
            <p className="mt-1 text-[11px] text-slate-600 dark:text-slate-400">
              数据集：{runContext.datasets.map((item) => `${item.name}${item.rows != null ? `（${item.rows}×${item.columns ?? "?"}）` : ""}`).join("、")}
            </p>
          )}
          {runContext.toolHints.length > 0 && (
            <p className="mt-1 text-[11px] text-slate-600 dark:text-slate-400">
              工具提示：{runContext.toolHints.join("、")}
            </p>
          )}
          {runContext.constraints.length > 0 && (
            <p className="mt-1 text-[11px] text-slate-600 dark:text-slate-400">
              关键约束：{runContext.constraints.join("；")}
            </p>
          )}
        </div>
      )}

      {completionCheck && (
        <div className={`rounded-lg border px-3 py-2 ${completionCheck.passed ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-medium text-slate-800 dark:text-slate-200">完成校验</span>
            <span className={completionCheck.passed ? "text-emerald-700" : "text-amber-800"}>
              第 {completionCheck.attempt} 次
            </span>
          </div>
          <div className="mt-2 space-y-1">
            {completionCheck.items.map((item) => (
              <div key={item.key} className="flex items-start gap-2 text-[11px] text-slate-700 dark:text-slate-300">
                {item.passed ? (
                  <CheckCircle2 size={12} className="mt-0.5 text-emerald-600" />
                ) : (
                  <AlertTriangle size={12} className="mt-0.5 text-amber-600" />
                )}
                <div className="min-w-0">
                  <p>{item.label}</p>
                  {item.detail && <p className="text-slate-500 dark:text-slate-400">{truncateText(item.detail, 120)}</p>}
                </div>
              </div>
            ))}
          </div>
          {!completionCheck.passed && completionCheck.missingActions.length > 0 && (
            <p className="mt-2 text-[11px] text-amber-800">
              待补齐：{completionCheck.missingActions.join("、")}
            </p>
          )}
        </div>
      )}

      {blockedState && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2">
          <div className="flex items-center gap-2 text-xs font-medium text-red-800">
            <AlertTriangle size={13} />
            <span>当前轮已阻塞</span>
          </div>
          <p className="mt-1 text-[11px] text-red-800">{blockedState.message}</p>
          {blockedState.suggestedAction && (
            <p className="mt-1 text-[11px] text-red-700">
              建议动作：{blockedState.suggestedAction}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function AnalysisPlanContent({
  plan,
  runContext,
  completionCheck,
  blockedState,
}: {
  plan: AnalysisPlanProgress;
  runContext: HarnessRunContextState | null;
  completionCheck: CompletionCheckState | null;
  blockedState: HarnessBlockedState | null;
}) {
  const safeCurrentIndex = Math.max(1, Math.min(plan.current_step_index, plan.total_steps || 1));
  const currentTitle = truncateText(plan.step_title || `步骤 ${safeCurrentIndex}`);
  const nextHint = truncateText(plan.next_hint || "", 120);
  const blockReason = truncateText(plan.block_reason || "", 120);

  const completedCount = plan.steps.filter((step) => step.status === "done").length;

  return (
    <div className="h-full flex flex-col">
      {/* 头部信息 */}
      <div className="px-3 py-3 border-b dark:border-slate-700 bg-gradient-to-b from-slate-50 dark:from-slate-800 to-white dark:to-slate-900">
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
            <Sparkles size={13} />
          </span>
          <span className="font-semibold text-slate-900 dark:text-slate-100">分析进度</span>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Step {safeCurrentIndex}/{plan.total_steps}
          </span>
          <span
            className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border ${statusBadgeClass(plan.step_status)}`}
          >
            {statusLabel(plan.step_status)}
          </span>
        </div>
        <p className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">{currentTitle}</p>
        {nextHint && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{nextHint}</p>}
        {blockReason && (
          <p className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
            {blockReason}
          </p>
        )}
      </div>

      <HarnessDiagnostics
        runContext={runContext}
        completionCheck={completionCheck}
        blockedState={blockedState}
      />

      {/* 步骤列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-2">
          <span>
            已完成 {completedCount} / {plan.total_steps}
          </span>
          <span>当前步骤高亮显示</span>
        </div>
        <ul className="space-y-1.5">
          {plan.steps.map((step) => {
            const isCurrent = step.id === safeCurrentIndex;
            const itemClass = isCurrent
              ? "border-blue-200 bg-blue-50/70 text-blue-900"
              : step.status === "done"
                ? "border-emerald-200 bg-emerald-50/60 text-emerald-900"
                : step.status === "failed"
                  ? "border-red-200 bg-red-50/60 text-red-900"
                  : step.status === "blocked"
                    ? "border-amber-200 bg-amber-50/60 text-amber-900"
                    : "border-slate-200 bg-slate-50 text-slate-700";

            return (
              <li
                key={step.id}
                className={`rounded-lg border px-2.5 py-2 flex items-start gap-2 text-xs ${itemClass}`}
              >
                <span className="mt-0.5">
                  <StepStatusIcon status={step.status} />
                </span>
                <span className={step.status === "done" ? "line-through opacity-80" : ""}>
                  {step.id}. {truncateText(step.title, 88)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

// 将任务状态映射为 PlanStepStatus
function mapTaskStatusToPlanStatus(status: AnalysisTaskItem["status"]): PlanStepStatus {
  return status;
}

// 历史任务列表组件
function HistoryTasksContent({ tasks }: { tasks: AnalysisTaskItem[] }) {
  const completedCount = tasks.filter((t) => t.status === "done").length;

  return (
    <div className="h-full flex flex-col">
      {/* 头部信息 */}
      <div className="px-3 py-3 border-b dark:border-slate-700 bg-gradient-to-b from-slate-50 dark:from-slate-800 to-white dark:to-slate-900">
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            <History size={13} />
          </span>
          <span className="font-semibold text-slate-700 dark:text-slate-300">历史任务</span>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            共 {tasks.length} 个任务
          </span>
        </div>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          已完成 {completedCount} / {tasks.length} 个任务
        </p>
      </div>

      {/* 任务列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <ul className="space-y-1.5">
          {tasks.map((task, index) => {
            const status = mapTaskStatusToPlanStatus(task.status);
            const itemClass =
              status === "done"
                ? "border-emerald-200 bg-emerald-50/40 text-emerald-900"
                : status === "failed"
                  ? "border-red-200 bg-red-50/40 text-red-900"
                  : status === "blocked"
                    ? "border-amber-200 bg-amber-50/40 text-amber-900"
                    : "border-slate-200 bg-slate-50 text-slate-600";

            return (
              <li
                key={task.id}
                className={`rounded-lg border px-2.5 py-2 flex items-start gap-2 text-xs ${itemClass}`}
              >
                <span className="mt-0.5">
                  <StepStatusIcon status={status} />
                </span>
                <div className="flex-1 min-w-0">
                  <span className={status === "done" ? "line-through opacity-80" : ""}>
                    {index + 1}. {truncateText(task.title, 88)}
                  </span>
                  {task.current_activity && (
                    <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">
                      {task.current_activity}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export default function AnalysisTasksPanel() {
  const analysisPlanProgress = useStore((s) => s.analysisPlanProgress);
  const analysisTasks = useStore((s) => s.analysisTasks);
  const harnessRunContext = useStore((s) => s.harnessRunContext);
  const completionCheck = useStore((s) => s.completionCheck);
  const blockedState = useStore((s) => s.blockedState);

  // 优先显示当前分析计划进度
  if (analysisPlanProgress && analysisPlanProgress.steps.length > 0) {
    return (
      <AnalysisPlanContent
        plan={analysisPlanProgress}
        runContext={harnessRunContext}
        completionCheck={completionCheck}
        blockedState={blockedState}
      />
    );
  }

  // 没有当前计划但有历史任务时，显示历史任务列表
  if (analysisTasks.length > 0) {
    return <HistoryTasksContent tasks={analysisTasks} />;
  }

  if (harnessRunContext || completionCheck || blockedState) {
    return (
      <div className="h-full overflow-y-auto">
        <HarnessDiagnostics
          runContext={harnessRunContext}
          completionCheck={completionCheck}
          blockedState={blockedState}
        />
      </div>
    );
  }

  // 没有任何任务时显示空状态
  return (
    <div className="h-full flex flex-col items-center justify-center text-gray-400 dark:text-slate-500 text-xs px-4">
      <Circle size={20} className="mb-2 opacity-50" />
      <p>暂无分析任务</p>
      <p className="text-[10px] mt-1">生成分析计划后会在这里展示任务进度</p>
    </div>
  );
}
