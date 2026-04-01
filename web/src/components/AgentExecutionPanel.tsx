/**
 * AgentExecutionPanel — 多 Agent 并行执行状态面板
 *
 * 显示当前运行中的子 Agent 列表及已完成 Agent 的摘要信息。
 * 仅在有活跃或已完成 Agent 时显示。
 */

import { useEffect, useMemo, useState } from "react";

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

function formatDuration(durationMs: number): string {
 if (durationMs < 1000) return `${Math.max(1, durationMs)}ms`;
 const seconds = Math.floor(durationMs / 1000);
 const minutes = Math.floor(seconds / 60);
 const remainingSeconds = seconds % 60;
 return minutes > 0 ? `${minutes}m ${remainingSeconds}s` : `${remainingSeconds}s`;
}

function RunningTime({ startTime, now }: { startTime: number; now: number }) {
 return (
 <span className="text-xs text-[var(--text-secondary)]">
 运行 {formatDuration(Math.max(0, now - startTime))}
 </span>
 );
}

function AgentMetrics({ agent }: { agent: AgentInfo }) {
 const metrics: string[] = [];
 if (agent.status === "running") {
 metrics.push(`尝试 ${agent.attemptCount}`);
 if (agent.failureCount > 0) metrics.push(`失败 ${agent.failureCount}`);
 }
 if (agent.status !== "running" && agent.latestExecutionTimeMs != null) {
 metrics.push(`耗时 ${formatDuration(agent.latestExecutionTimeMs)}`);
 }
 if (agent.status !== "running") {
 metrics.push(`尝试 ${agent.attemptCount}`);
 if (agent.failureCount > 0) metrics.push(`失败 ${agent.failureCount}`);
 }
 if (metrics.length === 0) return null;
 return (
 <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
 {metrics.map((item) => (
 <span key={item}>{item}</span>
 ))}
 </div>
 );
}

function AgentHistory({ agent }: { agent: AgentInfo }) {
 const history = [...agent.history].reverse();
 if (history.length <= 1) return null;
 return (
 <div className="mt-3 space-y-2 border-t border-[var(--border-subtle)] pt-3">
 {history.map((item) => (
 <div key={`${agent.agentId}-${item.attempt}-${item.startedAt}`} className="rounded-md bg-[var(--bg-elevated)] px-3 py-2">
 <div className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
 <span>第 {item.attempt} 次</span>
 <span>
 {item.status === "running"
 ? "运行中"
 : item.status === "completed"
 ? "完成"
 : "失败"}
 </span>
 {item.executionTimeMs != null && <span>耗时 {formatDuration(item.executionTimeMs)}</span>}
 </div>
 {item.summary && (
 <p className="mt-1 text-xs text-[var(--text-secondary)] break-words">
 {item.summary}
 </p>
 )}
 </div>
 ))}
 </div>
 );
}

export default function AgentExecutionPanel() {
 const activeAgents = useStore((s) => s.activeAgents);
 const completedAgents = useStore((s) => s.completedAgents);
 const [now, setNow] = useState(() => Date.now());
 const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>({});

 useEffect(() => {
 const timer = window.setInterval(() => setNow(Date.now()), 1000);
 return () => window.clearInterval(timer);
 }, []);

 const activeList = useMemo(
 () =>
 Object.values(activeAgents ?? {}).sort((left, right) => right.updatedAt - left.updatedAt),
 [activeAgents],
 );
 const completedList = useMemo(
 () => [...(completedAgents ?? [])].sort((left, right) => right.updatedAt - left.updatedAt),
 [completedAgents],
 );

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
 <div className="divide-y divide-[var(--border-subtle)]">
 {activeList.map((agent) => (
 <div key={agent.agentId} className="px-4 py-3 flex items-start gap-3">
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 mb-1">
 <span className="text-sm font-medium text-[var(--text-primary)] truncate">
 {agent.agentName}
 </span>
 <AgentStatusBadge status={agent.status} />
 <RunningTime startTime={agent.startTime} now={now} />
 </div>
 <p className="text-xs text-[var(--text-secondary)] break-words">{agent.task}</p>
 <AgentMetrics agent={agent} />
 </div>
 </div>
 ))}
 </div>
 )}

 {completedList.length > 0 && (
 <div className="border-t border-[var(--border-subtle)]">
 <div className="px-4 py-2 text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">
 最近结果
 </div>
 <div className="max-h-80 overflow-y-auto divide-y divide-[var(--border-subtle)]">
 {completedList.map((agent) => {
 const isExpanded = expandedAgents[agent.agentId] ?? false;
 return (
 <div key={agent.agentId} className="px-4 py-3">
 <div className="flex items-center gap-2 mb-1">
 <span className="text-sm font-medium text-[var(--text-secondary)]">{agent.agentName}</span>
 <AgentStatusBadge status={agent.status} />
 <button
 type="button"
 className="ml-auto text-[11px] text-[var(--accent)]"
 onClick={() =>
 setExpandedAgents((current) => ({
 ...current,
 [agent.agentId]: !isExpanded,
 }))
 }
 >
 {isExpanded ? "收起历史" : `历史 ${agent.history.length}`}
 </button>
 </div>
 <p className="text-xs text-[var(--text-secondary)] break-words">{agent.task}</p>
 <AgentMetrics agent={agent} />
 {agent.summary && (
 <p className="mt-2 text-xs text-[var(--text-secondary)] break-words">{agent.summary}</p>
 )}
 {isExpanded && <AgentHistory agent={agent} />}
 </div>
 );
 })}
 </div>
 </div>
 )}
 </div>
 );
}
