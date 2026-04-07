/**
 * WorkflowTopology —— 多 Agent 并行执行拓扑图（纯 CSS flexbox）
 *
 * 仅在存在 >= 2 个 Agent（运行中或已完成）时渲染；少于 2 个时返回 null。
 * 节点颜色：running→蓝色、completed→绿色、error→红色。
 * 订阅 Zustand store，实时反映 agent_start/complete/error 事件。
 */
import { useStore } from "../store";
import type { AgentInfo, AgentRunThread } from "../store/types";

const STATUS_STYLES: Record<AgentInfo["status"], string> = {
 running: "bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent)]",
 completed: "bg-[var(--accent-subtle)] border-[var(--success)] text-[var(--success)]",
 error: "bg-[var(--accent-subtle)] border-[var(--error)] text-[var(--error)]",
 stopped: "bg-[var(--bg-elevated)] border-[var(--text-muted)] text-[var(--text-secondary)]",
};

const STATUS_LABEL: Record<AgentInfo["status"], string> = {
 running: "运行中",
 completed: "完成",
 error: "失败",
 stopped: "已终止",
};

const STATUS_DOT: Record<AgentInfo["status"], string> = {
 running: "bg-[var(--accent)] animate-pulse",
 completed: "bg-[var(--success)]",
 error: "bg-[var(--error)]",
 stopped: "bg-[var(--text-muted)]",
};

interface AgentNodeProps {
 agent: AgentInfo;
}

function AgentNode({ agent }: AgentNodeProps) {
 return (
 <div
 className={`flex items-start gap-2 rounded-lg border px-3 py-2 min-w-[140px] max-w-[200px] ${STATUS_STYLES[agent.status]}`}
 title={agent.task}
 >
 <span
 className={`mt-1 flex-shrink-0 h-2 w-2 rounded-full ${STATUS_DOT[agent.status]}`}
 aria-hidden="true"
 />
 <div className="min-w-0 flex-1">
 <p className="truncate text-xs font-medium leading-tight">{agent.agentName}</p>
 <p className="text-[11px] opacity-70">{STATUS_LABEL[agent.status]}</p>
 <p className="text-[11px] opacity-70 truncate">
 尝试 {agent.attemptCount}{agent.failureCount > 0 ? ` · 失败 ${agent.failureCount}` : ""}
 </p>
 </div>
 </div>
 );
}

function buildDispatchSummary(dispatchRun: AgentRunThread): string[] {
 const parts: string[] = [];
 if (typeof dispatchRun.runnableCount === "number") {
  parts.push(`可执行 ${dispatchRun.runnableCount}`);
 }
 if (typeof dispatchRun.preflightFailureCount === "number") {
  parts.push(`预检失败 ${dispatchRun.preflightFailureCount}`);
 }
 if (
  typeof dispatchRun.routingFailureCount === "number" &&
  dispatchRun.routingFailureCount > 0
 ) {
  parts.push(`路由失败 ${dispatchRun.routingFailureCount}`);
 }
 if (
  typeof dispatchRun.executionFailureCount === "number" &&
  dispatchRun.executionFailureCount > 0
 ) {
  parts.push(`执行失败 ${dispatchRun.executionFailureCount}`);
 }
 return parts;
}

export default function WorkflowTopology() {
 const activeAgents = useStore((s) => s.activeAgents);
 const completedAgents = useStore((s) => s.completedAgents);
 const agentRunTabs = useStore((s) => s.agentRunTabs);
 const agentRuns = useStore((s) => s.agentRuns);

 const activeList = Object.values(activeAgents);
 const allAgents = [...activeList, ...completedAgents].sort(
 (left, right) => right.updatedAt - left.updatedAt,
 );
 const dispatchRun = agentRunTabs
  .map((runId) => agentRuns[runId])
  .filter((run): run is AgentRunThread => Boolean(run))
  .find((run) => run.runScope === "dispatch");
 const dispatchSummary = dispatchRun ? buildDispatchSummary(dispatchRun) : [];

 if (!dispatchRun && allAgents.length < 2) {
 return null;
 }

 return (
 <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-3">
 <p className="mb-2 text-xs font-medium text-[var(--text-secondary)]">并行执行中</p>
 {dispatchRun && (
 <div className="mb-3 rounded-lg border border-[color-mix(in_srgb,var(--accent)_18%,transparent)] bg-[var(--bg-base)] px-3 py-2.5">
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0">
 <p className="text-sm font-medium text-[var(--text-primary)]">任务派发预检</p>
 <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
 {dispatchRun.progressMessage || dispatchRun.summary || dispatchRun.task}
 </p>
 </div>
 <span
 className={`inline-flex shrink-0 items-center rounded-full border px-2 py-1 text-[10px] font-semibold leading-none ${STATUS_STYLES[dispatchRun.status]}`}
 >
 {STATUS_LABEL[dispatchRun.status]}
 </span>
 </div>
 {dispatchSummary.length > 0 && (
 <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
 {dispatchSummary.map((item) => (
 <span
 key={item}
 className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2 py-1"
 >
 {item}
 </span>
 ))}
 </div>
 )}
 </div>
 )}
 {allAgents.length > 0 ? (
 <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
 {allAgents.map((agent) => (
 <AgentNode key={agent.agentId} agent={agent} />
 ))}
 </div>
 ) : (
 <p className="text-xs text-[var(--text-secondary)]">等待子 Agent 启动...</p>
 )}
 </div>
 );
}
