/**
 * 分析任务面板 —— 展示任务生命周期与尝试轨迹（attempt timeline）。
 */
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Loader2,
  RotateCcw,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";
import {
  useStore,
  type AnalysisTaskAttempt,
  type AnalysisTaskItem,
  type AnalysisTaskAttemptStatus,
  type PlanStepStatus,
} from "../store";

function stepLabel(status: PlanStepStatus): string {
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

function stepBadgeClass(status: PlanStepStatus): string {
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

function stepIcon(status: PlanStepStatus) {
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

function attemptLabel(status: AnalysisTaskAttemptStatus): string {
  switch (status) {
    case "in_progress":
      return "执行中";
    case "retrying":
      return "重试中";
    case "success":
      return "成功";
    case "failed":
      return "失败";
  }
}

function attemptBadgeClass(status: AnalysisTaskAttemptStatus): string {
  switch (status) {
    case "in_progress":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "retrying":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "success":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "failed":
      return "bg-red-50 text-red-700 border-red-200";
  }
}

function AttemptIcon({ status }: { status: AnalysisTaskAttemptStatus }) {
  switch (status) {
    case "in_progress":
      return <Loader2 size={12} className="text-blue-600 animate-spin" />;
    case "retrying":
      return <RotateCcw size={12} className="text-amber-600" />;
    case "success":
      return <CheckCircle2 size={12} className="text-emerald-600" />;
    case "failed":
      return <XCircle size={12} className="text-red-600" />;
  }
}

function formatTime(ts: number): string {
  try {
    return new Date(ts).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "-";
  }
}

function AttemptItem({ attempt }: { attempt: AnalysisTaskAttempt }) {
  return (
    <li className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5">
      <div className="flex items-center gap-1.5 min-w-0">
        <AttemptIcon status={attempt.status} />
        <span className="text-[11px] text-slate-700 font-medium truncate">
          #{attempt.attempt}/{attempt.max_attempts} · {attempt.tool_name}
        </span>
        <span
          className={`ml-auto inline-flex items-center px-1.5 py-0.5 text-[10px] rounded-full border ${attemptBadgeClass(attempt.status)}`}
        >
          {attemptLabel(attempt.status)}
        </span>
      </div>
      {(attempt.note || attempt.error) && (
        <p className={`mt-1 text-[11px] ${attempt.error ? "text-red-600" : "text-slate-500"}`}>
          {attempt.error || attempt.note}
        </p>
      )}
      <p className="mt-1 text-[10px] text-slate-400">{formatTime(attempt.updated_at)}</p>
    </li>
  );
}

function TaskItem({
  task,
  index,
  onDelete,
}: {
  task: AnalysisTaskItem;
  index: number;
  onDelete: (id: string) => void;
}) {
  const latestAttempt = task.attempts[task.attempts.length - 1];

  return (
    <li className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-start gap-2">
        <span className="mt-0.5">{stepIcon(task.status)}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-400">{index + 1}.</span>
            <p
              className={`text-xs font-medium text-slate-900 truncate ${
                task.status === "done" ? "line-through opacity-75" : ""
              }`}
              title={task.title}
            >
              {task.title}
            </p>
            <span
              className={`ml-auto inline-flex items-center px-1.5 py-0.5 text-[10px] rounded-full border ${stepBadgeClass(task.status)}`}
            >
              {stepLabel(task.status)}
            </span>
          </div>

          {task.current_activity && (
            <p className="mt-1 text-[11px] text-slate-600 truncate" title={task.current_activity}>
              当前动作：{task.current_activity}
            </p>
          )}
          {task.last_error && (
            <p className="mt-1 text-[11px] text-red-600 truncate" title={task.last_error}>
              最近错误：{task.last_error}
            </p>
          )}
          {task.tool_hint && (
            <p className="mt-1 text-[11px] text-slate-500 truncate" title={task.tool_hint}>
              计划工具：{task.tool_hint}
            </p>
          )}
          <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-400">
            <span>添加于 {formatTime(task.created_at)}</span>
            <span>尝试 {task.attempts.length} 次</span>
            {latestAttempt && <span>最近更新 {formatTime(latestAttempt.updated_at)}</span>}
          </div>

          {task.attempts.length > 0 && (
            <div className="mt-2">
              <div className="flex items-center gap-1 text-[11px] text-slate-500 mb-1">
                <Wrench size={11} />
                尝试轨迹
              </div>
              <ul className="space-y-1">
                {task.attempts.map((attempt) => (
                  <AttemptItem key={attempt.id} attempt={attempt} />
                ))}
              </ul>
            </div>
          )}
        </div>
        <button
          onClick={() => onDelete(task.id)}
          className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
          title="删除任务"
          aria-label="删除任务"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </li>
  );
}

export default function AnalysisTasksPanel() {
  const analysisTasks = useStore((s) => s.analysisTasks);
  const deleteAnalysisTask = useStore((s) => s.deleteAnalysisTask);
  const clearAnalysisTasks = useStore((s) => s.clearAnalysisTasks);

  if (analysisTasks.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-gray-400 text-xs px-4">
        <Circle size={20} className="mb-2 opacity-50" />
        <p>暂无分析任务</p>
        <p className="text-[10px] mt-1">生成分析计划后会在这里展示任务与重试轨迹</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b flex items-center justify-between">
        <span className="text-[11px] text-slate-500">会话任务数：{analysisTasks.length}</span>
        <button
          onClick={clearAnalysisTasks}
          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-200 text-[11px] text-slate-500 hover:bg-slate-50"
        >
          <Trash2 size={11} />
          清空
        </button>
      </div>
      <ul className="flex-1 overflow-y-auto p-2 space-y-2">
        {analysisTasks.map((task, idx) => (
          <TaskItem key={task.id} task={task} index={idx} onDelete={deleteAnalysisTask} />
        ))}
      </ul>
    </div>
  );
}
