/**
 * DispatchLedgerOverviewPanel —— 调度账本总览，含跨会话审计摘要。
 */
import { useCallback, useMemo } from "react";
import { useStore } from "../store";

function formatCount(label: string, value: number | null | undefined): string | null {
  if (typeof value !== "number") return null;
  return `${label} ${value}`;
}

export default function DispatchLedgerOverviewPanel() {
  const dispatchLedgers = useStore((s) => s.dispatchLedgers);
  const dispatchLedgerAggregate = useStore((s) => s.dispatchLedgerAggregate);
  const selectAgentRun = useStore((s) => s.selectAgentRun);
  const switchSession = useStore((s) => s.switchSession);

  const ledgers = useMemo(
    () =>
      [...dispatchLedgers].sort((left, right) =>
        String(right.updated_at || "").localeCompare(String(left.updated_at || "")),
      ),
    [dispatchLedgers],
  );
  const riskySessions = useMemo(() => {
    const sessions = dispatchLedgerAggregate?.sessions ?? [];
    const prioritized = sessions.filter((item) => item.failure_count > 0);
    return (prioritized.length > 0 ? prioritized : sessions).slice(0, 3);
  }, [dispatchLedgerAggregate]);

  const handleOpenSession = useCallback(
    async (sessionId: string, latestRunId?: string | null) => {
      if (!sessionId) return;
      await switchSession(sessionId);
      if (latestRunId) {
        selectAgentRun(latestRunId);
      }
    },
    [selectAgentRun, switchSession],
  );

  if (!dispatchLedgerAggregate && ledgers.length === 0) {
    return null;
  }

  return (
    <section className="border-b border-[var(--border-default)] bg-[var(--bg-base)] px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-[var(--text-primary)]">调度账本</p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
            {dispatchLedgerAggregate
              ? `跨 ${dispatchLedgerAggregate.dispatch_session_count} 个会话累计 ${dispatchLedgerAggregate.dispatch_run_count} 次多 Agent 派发`
              : `当前会话共 ${ledgers.length} 次多 Agent 派发`}
          </p>
        </div>
      </div>
      {dispatchLedgerAggregate && (
        <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-3">
          <div className="flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
            {[
              formatCount("覆盖会话", dispatchLedgerAggregate.dispatch_session_count),
              formatCount("派发轮次", dispatchLedgerAggregate.dispatch_run_count),
              formatCount("子任务", dispatchLedgerAggregate.subtask_count),
              formatCount("失败总数", dispatchLedgerAggregate.failure_count),
              formatCount("预检失败", dispatchLedgerAggregate.preflight_failure_count),
              formatCount("路由失败", dispatchLedgerAggregate.routing_failure_count),
              formatCount("执行失败", dispatchLedgerAggregate.execution_failure_count),
            ]
              .filter(Boolean)
              .map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-[var(--border-subtle)] px-2 py-1"
                >
                  {item}
                </span>
              ))}
          </div>
          {riskySessions.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-[11px] font-medium text-[var(--text-secondary)]">
                {riskySessions.some((item) => item.failure_count > 0)
                  ? "近期高风险会话"
                  : "近期有调度记录的会话"}
              </p>
              {riskySessions.map((item) => (
                <button
                  key={item.session_id}
                  type="button"
                  onClick={() => void handleOpenSession(item.session_id, item.latest_run_id)}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2 text-left hover:bg-[var(--bg-hover)]"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-[var(--text-primary)]">
                        {item.title || item.session_id}
                      </p>
                      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                        派发 {item.dispatch_run_count} 次 · 子任务 {item.subtask_count} 个 · 失败 {item.failure_count} 个
                      </p>
                    </div>
                    <span className="shrink-0 text-[10px] text-[var(--text-muted)]">
                      {item.last_dispatch_at ? String(item.last_dispatch_at).slice(5, 16) : "无时间"}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {ledgers.length > 0 && (
        <div className="mt-3 space-y-2">
          <p className="text-[11px] font-medium text-[var(--text-secondary)]">
            当前会话共 {ledgers.length} 次多 Agent 派发
          </p>
          {ledgers.map((ledger) => {
            const summaryParts = [
              formatCount("可执行", ledger.runnable_count),
              formatCount("预检失败", ledger.preflight_failure_count),
              formatCount("路由失败", ledger.routing_failure_count),
              formatCount("执行失败", ledger.execution_failure_count),
            ].filter(Boolean);
            const previewItems = Array.isArray(ledger.dispatch_ledger)
              ? ledger.dispatch_ledger.slice(0, 3)
              : [];
            return (
              <button
                key={ledger.run_id}
                type="button"
                onClick={() => selectAgentRun(ledger.run_id)}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-left hover:bg-[var(--bg-hover)]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[var(--text-primary)]">
                      {ledger.agent_name || "任务派发"}
                    </p>
                    <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                      {ledger.progress_message || ledger.summary || ledger.task || "等待调度摘要..."}
                    </p>
                  </div>
                  <span className="shrink-0 text-[10px] text-[var(--text-muted)]">
                    {ledger.latest_phase || "dispatch"}
                  </span>
                </div>
                {summaryParts.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
                    {summaryParts.map((item) => (
                      <span
                        key={item}
                        className="rounded-full border border-[var(--border-subtle)] px-2 py-1"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                )}
                {previewItems.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {previewItems.map((item, index) => (
                      <div
                        key={`${ledger.run_id}-${item.agent_id || item.agent_name || index}`}
                        className="text-[11px] text-[var(--text-secondary)]"
                      >
                        {(item.agent_name || item.agent_id || "未命名 agent") +
                          " · " +
                          (item.task || "未命名任务")}
                      </div>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
