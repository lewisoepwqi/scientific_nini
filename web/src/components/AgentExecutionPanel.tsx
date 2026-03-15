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
    running: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    error: "bg-red-100 text-red-700",
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
    <span className="text-xs text-gray-400">
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
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
        <span className="text-sm font-medium text-gray-700">并行 Agent 执行</span>
        {activeList.length > 0 && (
          <span className="ml-auto text-xs text-gray-500">
            {activeList.length} 个运行中
          </span>
        )}
      </div>

      {activeList.length > 0 && (
        <div className="divide-y divide-gray-50">
          {activeList.map((agent) => (
            <div key={agent.agentId} className="px-4 py-3 flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-gray-800 truncate">
                    {agent.agentName}
                  </span>
                  <AgentStatusBadge status={agent.status} />
                  <ElapsedTime startTime={agent.startTime} />
                </div>
                <p className="text-xs text-gray-500 truncate">{agent.task}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {completedList.length > 0 && (
        <div className="border-t border-gray-100">
          <div className="px-4 py-2 text-xs font-medium text-gray-500 uppercase tracking-wide">
            已完成
          </div>
          <div className="divide-y divide-gray-50">
            {completedList.slice(-5).map((agent, idx) => (
              <div key={`${agent.agentId}-${idx}`} className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-gray-700">{agent.agentName}</span>
                  <AgentStatusBadge status={agent.status} />
                </div>
                {agent.summary && (
                  <p className="text-xs text-gray-500 line-clamp-2">{agent.summary}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
