/**
 * AgentRunTabsPanel —— 并行子 Agent 的 tab 切换区
 */

import { useMemo } from "react";
import { useStore } from "../store";
import Button from "./ui/Button";

function formatDuration(durationMs: number): string {
  if (durationMs < 1000) return `${Math.max(1, durationMs)}ms`;
  const seconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = seconds % 60;
  return minutes > 0 ? `${minutes}m ${remainSeconds}s` : `${remainSeconds}s`;
}

const STATUS_DOT: Record<string, string> = {
  running: "bg-[var(--accent)] animate-pulse",
  completed: "bg-[var(--success)]",
  error: "bg-[var(--error)]",
  stopped: "bg-[var(--text-muted)]",
};

const STATUS_LABEL: Record<string, string> = {
  running: "运行中",
  completed: "完成",
  error: "失败",
  stopped: "已终止",
};

export default function AgentRunTabsPanel() {
  const agentRunTabs = useStore((s) => s.agentRunTabs);
  const agentRuns = useStore((s) => s.agentRuns);
  const selectedRunId = useStore((s) => s.selectedRunId);
  const selectAgentRun = useStore((s) => s.selectAgentRun);
  const stopAgentRun = useStore((s) => s.stopAgentRun);
  const unreadByRun = useStore((s) => s.unreadByRun);

  const tabs = useMemo(
    () => agentRunTabs.map((runId) => agentRuns[runId]).filter(Boolean),
    [agentRunTabs, agentRuns],
  );

  if (tabs.length < 2) {
    return null;
  }

  return (
    <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] shadow-sm overflow-hidden">
      <div className="border-b border-[var(--border-subtle)] px-4 py-2.5">
        <div
          role="tablist"
          aria-label="并行子 Agent"
          className="flex gap-2 overflow-x-auto pb-1"
        >
          {tabs.map((run) => {
            const isSelected = run.runId === selectedRunId;
            const unread = unreadByRun[run.runId] ?? 0;
            const durationText =
              run.status === "running"
                ? formatDuration(Date.now() - run.startTime)
                : run.latestExecutionTimeMs != null
                  ? formatDuration(run.latestExecutionTimeMs)
                  : null;
            return (
              <button
                key={run.runId}
                type="button"
                role="tab"
                aria-selected={isSelected}
                aria-controls="agent-run-thread-panel"
                onClick={() => selectAgentRun(run.runId)}
                className={`min-w-[180px] shrink-0 rounded-lg border px-3 py-2 text-left transition-colors ${
                  isSelected
                    ? "border-[var(--accent)] bg-[var(--accent-subtle)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full ${STATUS_DOT[run.status]}`}
                    aria-hidden="true"
                  />
                  <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                    {run.agentName}
                  </span>
                  {unread > 0 && (
                    <span className="ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--accent)] px-1.5 text-[10px] font-semibold text-white">
                      {unread}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
                  <span>{STATUS_LABEL[run.status]}</span>
                  {durationText && <span>{durationText}</span>}
                  <span>尝试 {run.attempt}</span>
                </div>
                <div className="mt-1 truncate text-[11px] text-[var(--text-secondary)]">
                  {run.progressMessage || run.task || "等待事件..."}
                </div>
                {run.runScope === "subagent" && run.status === "running" && run.agentId && (
                  <div className="mt-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={(event) => {
                        event.stopPropagation();
                        stopAgentRun(run.runId, run.agentId!);
                      }}
                    >
                      终止
                    </Button>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
