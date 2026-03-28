/**
 * WorkflowTopology —— 多 Agent 并行执行拓扑图（纯 CSS flexbox）
 *
 * 仅在存在 >= 2 个 Agent（运行中或已完成）时渲染；少于 2 个时返回 null。
 * 节点颜色：running→蓝色、completed→绿色、error→红色。
 * 订阅 Zustand store，实时反映 agent_start/complete/error 事件。
 */
import { useStore } from "../store";
import type { AgentInfo } from "../store/types";

const STATUS_STYLES: Record<AgentInfo["status"], string> = {
 running: "bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent)]",
 completed: "bg-[var(--accent-subtle)] border-[var(--success)] text-[var(--success)]",
 error: "bg-[var(--accent-subtle)] border-[var(--error)] text-[var(--error)]",
};

const STATUS_LABEL: Record<AgentInfo["status"], string> = {
 running: "运行中",
 completed: "完成",
 error: "失败",
};

const STATUS_DOT: Record<AgentInfo["status"], string> = {
 running: "bg-[var(--accent)] animate-pulse",
 completed: "bg-[var(--success)]",
 error: "bg-[var(--error)]",
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
 </div>
 </div>
 );
}

export default function WorkflowTopology() {
 const activeAgents = useStore((s) => s.activeAgents);
 const completedAgents = useStore((s) => s.completedAgents);

 const activeList = Object.values(activeAgents);
 const allAgents = [...activeList, ...completedAgents];

 // 少于 2 个 Agent 时不渲染
 if (allAgents.length < 2) {
 return null;
 }

 return (
 <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-3">
 <p className="mb-2 text-xs font-medium text-[var(--text-secondary)]">并行执行中</p>
 <div className="flex flex-wrap gap-2">
 {allAgents.map((agent) => (
 <AgentNode key={agent.agentId} agent={agent} />
 ))}
 </div>
 </div>
 );
}
