/**
 * AgentRunTabsPanel —— 并行子 Agent 的 tab 切换区
 */

import { useMemo } from "react";
import { useStore } from "../store";

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
  completed: "已完成",
  error: "失败",
  stopped: "已终止",
};

const STATUS_BADGE: Record<string, string> = {
  running:
    "border-[color-mix(in_srgb,var(--accent)_22%,transparent)] bg-[var(--accent-subtle)] text-[var(--accent)]",
  completed:
    "border-[color-mix(in_srgb,var(--success)_22%,transparent)] bg-[color-mix(in_srgb,var(--success)_10%,var(--bg-base))] text-[var(--success)]",
  error:
    "border-[color-mix(in_srgb,var(--error)_22%,transparent)] bg-[color-mix(in_srgb,var(--error)_10%,var(--bg-base))] text-[var(--error)]",
  stopped:
    "border-[color-mix(in_srgb,var(--text-muted)_24%,transparent)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]",
};

function formatUnreadLabel(unread: number): string {
  if (unread <= 0) return "";
  return `新消息 ${unread > 99 ? "99+" : unread}`;
}

export default function AgentRunTabsPanel() {
  const agentRunTabs = useStore((s) => s.agentRunTabs);
  const agentRuns = useStore((s) => s.agentRuns);
  const selectedRunId = useStore((s) => s.selectedRunId);
  const selectAgentRun = useStore((s) => s.selectAgentRun);
  const unreadByRun = useStore((s) => s.unreadByRun);

  const tabs = useMemo(
    () => agentRunTabs.map((runId) => agentRuns[runId]).filter(Boolean),
    [agentRunTabs, agentRuns],
  );

  if (tabs.length < 2) {
    return null;
  }

  function renderDispatchSummary(run: (typeof tabs)[number]) {
    if (run.runScope !== "dispatch") return null;
    const parts: string[] = [];
    if (typeof run.runnableCount === "number") {
      parts.push(`可执行 ${run.runnableCount}`);
    }
    if (typeof run.preflightFailureCount === "number") {
      parts.push(`预检失败 ${run.preflightFailureCount}`);
    }
    if (typeof run.routingFailureCount === "number" && run.routingFailureCount > 0) {
      parts.push(`路由失败 ${run.routingFailureCount}`);
    }
    if (typeof run.executionFailureCount === "number" && run.executionFailureCount > 0) {
      parts.push(`执行失败 ${run.executionFailureCount}`);
    }
    if (parts.length === 0) return null;
    return (
      <div className="mt-2 text-[11px] leading-4 text-[var(--text-secondary)]">
        {parts.join(" · ")}
      </div>
    );
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
                className={`flex min-h-[116px] min-w-[196px] shrink-0 flex-col items-start justify-start rounded-lg border px-3 py-2.5 text-left align-top transition-colors ${
                  isSelected
                    ? "border-[var(--accent)] bg-[var(--accent-subtle)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                <div className="flex w-full items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start gap-2">
                      <span
                        className={`mt-1 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[run.status]}`}
                        aria-hidden="true"
                      />
                      <span className="truncate text-sm font-medium leading-5 text-[var(--text-primary)]">
                        {run.agentName}
                      </span>
                    </div>
                    {unread > 0 && (
                      <span className="mt-2 inline-flex items-center rounded-full border border-[color-mix(in_srgb,var(--accent)_18%,transparent)] bg-[var(--accent-subtle)] px-2 py-0.5 text-[10px] font-semibold leading-none text-[var(--accent)]">
                        {formatUnreadLabel(unread)}
                      </span>
                    )}
                  </div>
                  <span
                    className={`inline-flex shrink-0 items-center rounded-full border px-2 py-1 text-[10px] font-semibold leading-none ${STATUS_BADGE[run.status]}`}
                  >
                    {STATUS_LABEL[run.status]}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--text-secondary)]">
                  {durationText && <span>{durationText}</span>}
                  <span>尝试 {run.attempt}</span>
                </div>
                <div className="mt-2 min-h-[32px] overflow-hidden text-[11px] leading-4 text-[var(--text-secondary)]">
                  {run.progressMessage || run.task || "等待事件..."}
                </div>
                {renderDispatchSummary(run)}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
