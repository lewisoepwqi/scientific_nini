/**
 * AgentMessageCard —— 结构化分析计划消息卡片。
 *
 * 设计规范：.impeccable.md Chat Components §AgentMessageCard
 * 当 AI 输出包含 analysis_plan 类型的 tool_call 时渲染为卡片。
 */
import { Suspense, lazy } from "react";
import {
 ClipboardList,
 ExternalLink,
 RotateCw,
 Maximize2,
} from "lucide-react";
import type { Message } from "../../store";
import TaskTree from "./TaskTree";

const LazyMarkdownContent = lazy(() => import("../LazyMarkdownContent"));

interface AgentMessageCardProps {
 message: Message;
}

export default function AgentMessageCard({ message }: AgentMessageCardProps) {
 const plan = message.analysisPlan;
 if (!plan) return null;

 const steps = plan.steps;
 const completedCount = steps.filter((s) => s.status === "done").length;
 const totalCount = steps.length;
 const currentStep = steps.find((s) => s.status === "in_progress");

 return (
 <div className="my-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] overflow-hidden">
 {/* Header 44px */}
 <div className="flex h-11 items-center justify-between px-4 border-b border-[var(--border-subtle)]">
 <div className="flex items-center gap-2">
 <ClipboardList size={16} style={{ color: "var(--domain-analysis)" }} />
 <span className="text-[14px] font-medium text-[var(--text-primary)]">
 分析计划与执行
 </span>
 <span className="text-[11px] px-1.5 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)]">
 {completedCount}/{totalCount}
 </span>
 </div>
 <div className="flex items-center gap-1">
 <button
 type="button"
 className="w-7 h-7 p-0 flex items-center justify-center bg-transparent border-none cursor-pointer focus:outline-none"
 aria-label="在新窗口打开"
 >
 <ExternalLink size={14} style={{ color: "var(--text-muted)" }} />
 </button>
 <button
 type="button"
 className="w-7 h-7 p-0 flex items-center justify-center bg-transparent border-none cursor-pointer focus:outline-none"
 aria-label="重新执行"
 >
 <RotateCw size={14} style={{ color: "var(--text-muted)" }} />
 </button>
 <button
 type="button"
 className="w-7 h-7 p-0 flex items-center justify-center bg-transparent border-none cursor-pointer focus:outline-none"
 aria-label="展开"
 >
 <Maximize2 size={14} style={{ color: "var(--text-muted)" }} />
 </button>
 </div>
 </div>

 {/* 状态链 32px */}
 {steps.length > 0 && (
 <div className="flex h-8 items-center gap-1 px-4 border-b border-[var(--border-subtle)] overflow-x-auto">
 {steps.map((step, idx) => {
 const isActive = step.status === "in_progress";
 const isDone = step.status === "done";
 return (
 <span key={step.id} className="flex items-center gap-1 flex-shrink-0">
 <span
 className={`text-[11px] px-1.5 py-0.5 rounded whitespace-nowrap ${
 isActive
 ? "bg-[var(--accent-subtle)] text-[var(--accent)] font-medium"
 : isDone
 ? "text-[var(--text-muted)]"
 : "text-[var(--text-disabled)]"
 }`}
 >
 {step.title}
 </span>
 {idx < steps.length - 1 && (
 <span className="text-[var(--text-disabled)]">→</span>
 )}
 </span>
 );
 })}
 </div>
 )}

 {/* 内容区 */}
 <div className="p-4">
 {currentStep && (
 <div className="mb-3">
 <TaskTree />
 </div>
 )}
 <div className="text-sm text-[var(--text-primary)] markdown-body">
 <Suspense fallback={<div className="text-[var(--text-muted)]">加载中…</div>}>
 <LazyMarkdownContent content={plan.raw_text} />
 </Suspense>
 </div>
 </div>
 </div>
 );
}
