/**
 * 分析任务面板 —— 展示分析计划进度和步骤列表。
 */
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  History,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useStore, type AnalysisPlanProgress, type PlanStepStatus, type AnalysisTaskItem } from "../store";

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

function AnalysisPlanContent({ plan }: { plan: AnalysisPlanProgress }) {
  const safeCurrentIndex = Math.max(1, Math.min(plan.current_step_index, plan.total_steps || 1));
  const currentTitle = truncateText(plan.step_title || `步骤 ${safeCurrentIndex}`);
  const nextHint = truncateText(plan.next_hint || "", 120);
  const blockReason = truncateText(plan.block_reason || "", 120);

  const completedCount = plan.steps.filter((step) => step.status === "done").length;

  return (
    <div className="h-full flex flex-col">
      {/* 头部信息 */}
      <div className="px-3 py-3 border-b bg-gradient-to-b from-slate-50 to-white">
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700">
            <Sparkles size={13} />
          </span>
          <span className="font-semibold text-slate-900">分析进度</span>
          <span className="text-xs text-slate-500">
            Step {safeCurrentIndex}/{plan.total_steps}
          </span>
          <span
            className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border ${statusBadgeClass(plan.step_status)}`}
          >
            {statusLabel(plan.step_status)}
          </span>
        </div>
        <p className="mt-2 text-sm font-medium text-slate-900">{currentTitle}</p>
        {nextHint && <p className="mt-1 text-xs text-slate-600">{nextHint}</p>}
        {blockReason && (
          <p className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
            {blockReason}
          </p>
        )}
      </div>

      {/* 步骤列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
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
      <div className="px-3 py-3 border-b bg-gradient-to-b from-slate-50 to-white">
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-slate-100 text-slate-600">
            <History size={13} />
          </span>
          <span className="font-semibold text-slate-700">历史任务</span>
          <span className="text-xs text-slate-500">
            共 {tasks.length} 个任务
          </span>
        </div>
        <p className="mt-2 text-xs text-slate-500">
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
                    <p className="text-[10px] text-slate-500 mt-0.5 truncate">
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

  // 优先显示当前分析计划进度
  if (analysisPlanProgress && analysisPlanProgress.steps.length > 0) {
    return <AnalysisPlanContent plan={analysisPlanProgress} />;
  }

  // 没有当前计划但有历史任务时，显示历史任务列表
  if (analysisTasks.length > 0) {
    return <HistoryTasksContent tasks={analysisTasks} />;
  }

  // 没有任何任务时显示空状态
  return (
    <div className="h-full flex flex-col items-center justify-center text-gray-400 text-xs px-4">
      <Circle size={20} className="mb-2 opacity-50" />
      <p>暂无分析任务</p>
      <p className="text-[10px] mt-1">生成分析计划后会在这里展示任务进度</p>
    </div>
  );
}
