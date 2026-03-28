/**
 * AgentExecutionPanel — 多 Agent 并行执行状态面板
 *
 * 显示当前运行中的子 Agent 列表及已完成 Agent 的摘要信息。
 * 仅在有活跃或已完成 Agent 时显示。
 */

import { useStore } from "../store";
import type { AgentInfo } from "../store/types";

function AgentStatusBadge({ status }: { status: AgentInfo["status"] }) {
 const styles = {
 running: "bg-[var(--accent-subtle)] text-[var(--accent)]",
 completed: "bg-[var(--accent-subtle)] text-[var(--success)]",
 error: "bg-[var(--accent-subtle)] text-[var(--error)]",
 };
 const labels = {
 running: "运行中",
 completed: "已完成",
 error: "失败",
 };
 return (
 <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[status]}`}>
 {labels[status]}
 </span>
 );
}

function ElapsedTime({ startTime }: { startTime: number }) {
 const elapsed = Math.floor((Date.now() - startTime) / 1000);
 const minutes = Math.floor(elapsed / 60);
 const seconds = elapsed % 60;
 return (
 <span className="text-xs text-[var(--text-secondary)]">
 {minutes > 0 ? `${minutes}m ` : ""}{seconds}s
 </span>
 );
}

export default function AgentExecutionPanel() {
 const activeAgents = useStore((s) => s.activeAgents);
 const completedAgents = useStore((s) => s.completedAgents);

 const activeList = Object.values(activeAgents ?? {});
 const completedList = completedAgents ?? [];

 if (activeList.length === 0 && completedList.length === 0) {
 return null;
 }

 return (
 <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] shadow-sm overflow-hidden" aria-live="polite" aria-atomic="false">
 <div className="px-4 py-3 border-b border-[var(--border-subtle)] flex items-center gap-2">
 <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
 <span className="text-sm font-medium text-[var(--text-secondary)]">并行 Agent 执行</span>
 {activeList.length > 0 && (
 <span className="ml-auto text-xs text-[var(--text-secondary)]" aria-live="polite">
 {activeList.length} 个运行中
 </span>
 )}
 </div>

 {activeList.length > 0 && (
 <div className="divide-y divide-slate-50 dark:divide-slate-700">
 {activeList.map((agent) => (
 <div key={agent.agentId} className="px-4 py-3 flex items-start gap-3">
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 mb-1">
 <span className="text-sm font-medium text-[var(--text-primary)] truncate">
 {agent.agentName}
 </span>
 <AgentStatusBadge status={agent.status} />
 <ElapsedTime startTime={agent.startTime} />
 </div>
 <p className="text-xs text-[var(--text-secondary)] truncate">{agent.task}</p>
 </div>
 </div>
 ))}
 </div>
 )}

 {completedList.length > 0 && (
 <div className="border-t border-[var(--border-subtle)]">
 <div className="px-4 py-2 text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">
 已完成
 </div>
 <div className="divide-y divide-slate-50 dark:divide-slate-700">
 {completedList.slice(-5).map((agent, idx) => (
 <div key={`${agent.agentId}-${idx}`} className="px-4 py-3">
 <div className="flex items-center gap-2 mb-1">
 <span className="text-sm font-medium text-[var(--text-secondary)]">{agent.agentName}</span>
 <AgentStatusBadge status={agent.status} />
 </div>
 {agent.summary && (
 <p className="text-xs text-[var(--text-secondary)] line-clamp-2">{agent.summary}</p>
 )}
 </div>
 ))}
 </div>
 </div>
 )}
 </div>
 );
}
