/**
 * TaskTree —— 折叠式任务树，替代线性 StepProgressBar。
 *
 * 设计规范：.impeccable.md Chat Components §TaskTree
 * 默认折叠（单行 36px），展开后显示任务列表（每项 32px）。
 */
import { useState } from "react";
import {
 Check,
 Loader2,
 Circle,
 AlertCircle,
 ChevronDown,
 ChevronRight,
} from "lucide-react";
import type {
 AnalysisPlanProgress,
 AnalysisTaskItem,
 PlanStepStatus,
} from "../../store";
import { useStore } from "../../store";

/** 状态 → 图标映射（遵循 .impeccable.md 规范） */
function StepIcon({ status }: { status: PlanStepStatus }) {
 switch (status) {
 case "done":
 return <Check size={14} style={{ color: "var(--success)" }} />;
 case "in_progress":
 return (
 <Loader2
 size={14}
 className="animate-spin"
 style={{ color: "var(--accent)" }}
 />
 );
 case "failed":
 case "blocked":
 return <AlertCircle size={14} style={{ color: "var(--error)" }} />;
 default:
 return <Circle size={14} style={{ color: "var(--text-muted)" }} />;
 }
}

function statusLabel(status: PlanStepStatus): string {
 switch (status) {
 case "in_progress": return "进行中";
 case "done": return "已完成";
 case "blocked": return "已阻塞";
 case "failed": return "失败";
 default: return "未开始";
 }
}

interface TaskTreeProps {
 plan?: AnalysisPlanProgress | null;
 tasks?: AnalysisTaskItem[];
}

export default function TaskTree({ plan, tasks }: TaskTreeProps) {
 const [expanded, setExpanded] = useState(false);

 // 数据源：优先使用传入 props，否则从 store 读取
 const storePlan = useStore((s) => s.analysisPlanProgress);
 const storeTasks = useStore((s) => s.analysisTasks);
 const activePlan = plan ?? storePlan;
 const activeTasks = tasks ?? storeTasks;

 const steps = activePlan?.steps ?? [];
 const totalCount = steps.length;
 const completedCount = steps.filter(
 (s) => s.status === "done" || s.status === "failed" || s.status === "skipped",
 ).length;
 const progress = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;
 const currentStep = activePlan?.step_title ?? "";

 if (totalCount === 0 && activeTasks.length === 0) {
 return (
 <div className="flex items-center justify-center py-4 text-xs text-[var(--text-muted)]">
 暂无任务
 </div>
 );
 }

 return (
 <div className="flex flex-col">
 {/* 标题栏 */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex h-9 items-center gap-2 w-full px-2 transition-colors bg-transparent border-none cursor-pointer focus:outline-none"
      >
 {/* 当前步骤状态图标 */}
 <StepIcon status={activePlan?.step_status ?? "not_started"} />

 {/* 任务总标题 */}
 <span className="flex-1 text-left text-[13px] font-medium text-[var(--text-primary)] truncate">
 {currentStep || `共 ${totalCount} 个步骤`}
 </span>

 {/* 完成百分比 */}
 <span className="text-xs text-[var(--text-secondary)] tabular-nums">
 {progress}%
 </span>

 {/* 展开箭头 */}
 {expanded ? (
 <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
 ) : (
 <ChevronRight size={14} style={{ color: "var(--text-muted)" }} />
 )}
 </button>

 {/* 展开态：任务列表 */}
 {expanded && (
 <div className="ml-4 mt-1 space-y-0.5">
 {steps.map((step) => {
 const isActive = step.status === "in_progress";
 return (
 <div
 key={step.id}
 className={`flex h-8 items-center gap-2 rounded-md px-2 transition-colors ${
 isActive ? "bg-[var(--accent-subtle)]" : ""
 }`}
 >
 <StepIcon status={step.status} />
 <span
 className={`flex-1 text-[13px] truncate ${
 isActive
 ? "text-[var(--accent)] font-medium"
 : step.status === "done"
 ? "text-[var(--text-muted)]"
 : "text-[var(--text-primary)]"
 }`}
 >
 {step.title}
 </span>
 <span className="text-[11px] text-[var(--text-muted)]">
 {statusLabel(step.status)}
 </span>
 </div>
 );
 })}
 </div>
 )}
 </div>
 );
}
