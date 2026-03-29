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
import { Badge } from "./ui/Badge";

type Tone = "accent" | "success" | "warning" | "error";

function toneToken(tone: Tone): string {
 switch (tone) {
 case "success":
 return "var(--success)";
 case "warning":
 return "var(--warning)";
 case "error":
 return "var(--error)";
 default:
 return "var(--accent)";
 }
}

function toneSurfaceStyle(tone: Tone, weight = 10) {
 return {
 backgroundColor: `color-mix(in srgb, ${toneToken(tone)} ${weight}%, var(--bg-base))`,
 };
}

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

function statusToVariant(status: PlanStepStatus): "default" | "success" | "warning" | "error" {
 switch (status) {
 case "done":
 return "success";
 case "blocked":
 return "warning";
 case "failed":
 return "error";
 default:
 return "default";
 }
}

function StepStatusIcon({ status }: { status: PlanStepStatus }) {
 switch (status) {
 case "in_progress":
 return <Loader2 size={14} className="text-[var(--accent)] animate-spin" />;
 case "done":
 return <CheckCircle2 size={14} className="text-[var(--success)]" />;
 case "blocked":
 return <AlertTriangle size={14} className="text-[var(--warning)]" />;
 case "failed":
 return <XCircle size={14} className="text-[var(--error)]" />;
 default:
 return <Circle size={14} className="text-[var(--text-muted)]" />;
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
 <div className="px-3 py-3 border-b border-[var(--border-default)] bg-[var(--bg-base)] space-y-2">
 {runContext && (
 <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
 <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
 <FileStack size={13} />
 <span>运行上下文</span>
 </div>
 {runContext.datasets.length > 0 && (
 <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
 数据集：{runContext.datasets.map((item) => `${item.name}${item.rows != null ? `（${item.rows}×${item.columns ?? "?"}）` : ""}`).join("、")}
 </p>
 )}
 {runContext.toolHints.length > 0 && (
 <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
 工具提示：{runContext.toolHints.join("、")}
 </p>
 )}
 {runContext.constraints.length > 0 && (
 <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
 关键约束：{runContext.constraints.join("；")}
 </p>
 )}
 </div>
 )}

 {completionCheck && (
 <div
 className={`rounded-lg border px-3 py-2 ${
 completionCheck.passed ? "border-[var(--success)]" : "border-[var(--warning)]"
 }`}
 style={toneSurfaceStyle(completionCheck.passed ? "success" : "warning", 10)}
 >
 <div className="flex items-center justify-between gap-2 text-xs">
 <span className="font-medium text-[var(--text-primary)]">完成校验</span>
 <span className={completionCheck.passed ? "text-[var(--success)]" : "text-[var(--warning)]"}>
 第 {completionCheck.attempt} 次
 </span>
 </div>
 <div className="mt-2 space-y-1">
 {completionCheck.items.map((item) => (
 <div key={item.key} className="flex items-start gap-2 text-[11px] text-[var(--text-secondary)]">
 {item.passed ? (
 <CheckCircle2 size={12} className="mt-0.5 text-[var(--success)]" />
 ) : (
 <AlertTriangle size={12} className="mt-0.5 text-[var(--warning)]" />
 )}
 <div className="min-w-0">
 <p>{item.label}</p>
 {item.detail && <p className="text-[var(--text-secondary)]">{truncateText(item.detail, 120)}</p>}
 </div>
 </div>
 ))}
 </div>
 {!completionCheck.passed && completionCheck.missingActions.length > 0 && (
 <p className="mt-2 text-[11px] text-[var(--warning)]">
 待补齐：{completionCheck.missingActions.join("、")}
 </p>
 )}
 </div>
 )}

 {blockedState && (
 <div
 className="rounded-lg border border-[var(--error)] px-3 py-2"
 style={toneSurfaceStyle("error", 12)}
 >
 <div className="flex items-center gap-2 text-xs font-medium text-[var(--error)]">
 <AlertTriangle size={13} />
 <span>当前轮已阻塞</span>
 </div>
 <p className="mt-1 text-[11px] text-[var(--error)]">{blockedState.message}</p>
 {blockedState.suggestedAction && (
 <p className="mt-1 text-[11px] text-[var(--error)]">
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
 <header className="px-3 py-3 border-b border-[var(--border-default)] bg-[var(--bg-base)]">
 <div className="flex items-center gap-2 text-sm">
 <span
 className="inline-flex items-center justify-center w-6 h-6 rounded-full text-[var(--accent)]"
 style={toneSurfaceStyle("accent", 12)}
 >
 <Sparkles size={13} />
 </span>
 <span className="font-semibold text-[var(--text-primary)]">分析进度</span>
 <span className="text-xs text-[var(--text-secondary)]">
 Step {safeCurrentIndex}/{plan.total_steps}
 </span>
 <Badge variant={statusToVariant(plan.step_status)}>
 {statusLabel(plan.step_status)}
 </Badge>
 </div>
 <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{currentTitle}</p>
 {nextHint && <p className="mt-1 text-xs text-[var(--text-secondary)]">{nextHint}</p>}
 {blockReason && (
 <p
 className="mt-1 rounded px-2 py-1 text-xs text-[var(--warning)] border border-[var(--warning)]"
 style={toneSurfaceStyle("warning", 10)}
 >
 {blockReason}
 </p>
 )}
 </header>

 <HarnessDiagnostics
 runContext={runContext}
 completionCheck={completionCheck}
 blockedState={blockedState}
 />

 {/* 步骤列表 */}
 <div className="flex-1 overflow-y-auto px-3 py-3">
 <div className="flex items-center justify-between text-xs text-[var(--text-secondary)] mb-2">
 <span>
 已完成 {completedCount} / {plan.total_steps}
 </span>
 <span>当前步骤高亮显示</span>
 </div>
 <ul className="space-y-1.5" role="list" aria-live="polite">
 {plan.steps.map((step) => {
 const isCurrent = step.id === safeCurrentIndex;
 const itemClass = isCurrent
 ? "border-[var(--accent)] text-[var(--accent)]"
 : step.status === "done"
 ? "border-[var(--success)] text-[var(--success)]"
 : step.status === "failed"
 ? "border-[var(--error)] text-[var(--error)]"
 : step.status === "blocked"
 ? "border-[var(--warning)] text-[var(--warning)]"
 : "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)] dark:text-[var(--text-muted)]";
 const itemStyle = isCurrent
 ? toneSurfaceStyle("accent", 12)
 : step.status === "done"
 ? toneSurfaceStyle("success", 10)
 : step.status === "failed"
 ? toneSurfaceStyle("error", 12)
 : step.status === "blocked"
 ? toneSurfaceStyle("warning", 10)
 : undefined;

 return (
 <li
 key={step.id}
 className={`rounded-lg border px-2.5 py-2 flex items-start gap-2 text-xs ${itemClass}`}
 style={itemStyle}
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
 <header className="px-3 py-3 border-b border-[var(--border-default)] bg-[var(--bg-base)]">
 <div className="flex items-center gap-2 text-sm">
 <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
 <History size={13} />
 </span>
 <span className="font-semibold text-[var(--text-secondary)]">历史任务</span>
 <span className="text-xs text-[var(--text-secondary)]">
 共 {tasks.length} 个任务
 </span>
 </div>
 <p className="mt-2 text-xs text-[var(--text-secondary)]">
 已完成 {completedCount} / {tasks.length} 个任务
 </p>
 </header>
 <div className="flex-1 overflow-y-auto px-3 py-3">
 <ul className="space-y-1.5">
 {tasks.map((task, index) => {
 const status = mapTaskStatusToPlanStatus(task.status);
 const itemClass =
 status === "done"
 ? "border-[var(--success)] text-[var(--success)]"
 : status === "failed"
 ? "border-[var(--error)] text-[var(--error)]"
 : status === "blocked"
 ? "border-[var(--warning)] text-[var(--warning)]"
 : "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]";
 const itemStyle =
 status === "done"
 ? toneSurfaceStyle("success", 10)
 : status === "failed"
 ? toneSurfaceStyle("error", 12)
 : status === "blocked"
 ? toneSurfaceStyle("warning", 10)
 : undefined;

 return (
 <li
 key={task.id}
 className={`rounded-lg border px-2.5 py-2 flex items-start gap-2 text-xs ${itemClass}`}
 style={itemStyle}
 >
 <span className="mt-0.5">
 <StepStatusIcon status={status} />
 </span>
 <div className="flex-1 min-w-0">
 <span className={status === "done" ? "line-through opacity-80" : ""}>
 {index + 1}. {truncateText(task.title, 88)}
 </span>
 {task.current_activity && (
 <p className="text-[10px] text-[var(--text-secondary)] mt-0.5 truncate">
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
 <div className="h-full flex flex-col items-center justify-center text-[var(--text-muted)] text-xs px-4">
 <Circle size={20} className="mb-2 opacity-50" />
 <p>暂无分析任务</p>
 <p className="text-[10px] mt-1">生成分析计划后会在这里展示任务进度</p>
 </div>
 );
}
