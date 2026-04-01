/**
 * Agent 执行状态切片
 *
 * 管理并行运行中子 Agent 的状态（activeAgents 和 completedAgents）。
 */

import type { AgentAttemptInfo, AgentInfo, AgentSlice } from "./types";

const MAX_AGENT_HISTORY = 8;

export const initialAgentSlice: AgentSlice = {
  activeAgents: {},
  completedAgents: [],
};

function clampHistory(history: AgentAttemptInfo[]): AgentAttemptInfo[] {
  if (history.length <= MAX_AGENT_HISTORY) return history;
  return history.slice(history.length - MAX_AGENT_HISTORY);
}

function findCompletedAgent(
  state: AgentSlice,
  agentId: string,
): AgentInfo | undefined {
  return state.completedAgents.find((agent) => agent.agentId === agentId);
}

function upsertCompletedAgent(
  agents: AgentInfo[],
  next: AgentInfo,
): AgentInfo[] {
  const filtered = agents.filter((agent) => agent.agentId !== next.agentId);
  return [next, ...filtered].sort((left, right) => right.updatedAt - left.updatedAt);
}

function finalizeLatestAttempt(
  history: AgentAttemptInfo[],
  {
    attempt,
    status,
    endedAt,
    executionTimeMs,
    summary,
  }: {
    attempt: number;
    status: AgentInfo["status"];
    endedAt: number;
    executionTimeMs: number;
    summary: string;
  },
): AgentAttemptInfo[] {
  const nextHistory = [...history];
  const latestIndex = [...nextHistory]
    .reverse()
    .findIndex((item) => item.attempt === attempt);
  const targetIndex =
    latestIndex >= 0 ? nextHistory.length - latestIndex - 1 : nextHistory.length - 1;
  const current =
    targetIndex >= 0
      ? nextHistory[targetIndex]
      : ({
          attempt,
          task: "",
          status,
          startedAt: endedAt - executionTimeMs,
          endedAt: null,
          executionTimeMs: null,
        } satisfies AgentAttemptInfo);
  const updatedAttempt: AgentAttemptInfo = {
    ...current,
    attempt,
    status,
    endedAt,
    executionTimeMs,
    summary,
  };
  if (targetIndex >= 0) {
    nextHistory[targetIndex] = updatedAttempt;
  } else {
    nextHistory.push(updatedAttempt);
  }
  return clampHistory(nextHistory);
}

export function setAgentStart(
  state: AgentSlice,
  agentId: string,
  agentName: string,
  task: string,
  attempt?: number,
  retryCount?: number,
): AgentSlice {
  const now = Date.now();
  const existing = state.activeAgents[agentId] ?? findCompletedAgent(state, agentId);
  const nextAttempt =
    typeof attempt === "number" && attempt > 0
      ? attempt
      : typeof retryCount === "number" && retryCount >= 0
        ? retryCount + 1
        : (existing?.attemptCount ?? 0) + 1;
  const nextHistory = clampHistory([
    ...(existing?.history ?? []),
    {
      attempt: nextAttempt,
      task,
      status: "running",
      startedAt: now,
      endedAt: null,
      executionTimeMs: null,
    },
  ]);
  const info: AgentInfo = {
    agentId,
    agentName,
    status: "running",
    task,
    startTime: now,
    updatedAt: now,
    attemptCount: Math.max(existing?.attemptCount ?? 0, nextAttempt),
    failureCount: existing?.failureCount ?? 0,
    latestExecutionTimeMs: existing?.latestExecutionTimeMs ?? null,
    lastError: null,
    summary: existing?.summary,
    history: nextHistory,
  };
  const remainingCompleted = state.completedAgents.filter(
    (agent) => agent.agentId !== agentId,
  );
  return {
    ...state,
    completedAgents: remainingCompleted,
    activeAgents: { ...state.activeAgents, [agentId]: info },
  };
}

export function setAgentComplete(
  state: AgentSlice,
  agentId: string,
  summary: string,
  executionTimeMs?: number,
  attempt?: number,
): AgentSlice {
  const existing = state.activeAgents[agentId] ?? findCompletedAgent(state, agentId);
  if (!existing) return state;

  const endedAt = Date.now();
  const resolvedAttempt = attempt ?? existing.attemptCount;
  const resolvedExecutionTimeMs =
    typeof executionTimeMs === "number" && executionTimeMs >= 0
      ? executionTimeMs
      : Math.max(0, endedAt - existing.startTime);
  const completed: AgentInfo = {
    ...existing,
    status: "completed",
    summary,
    latestExecutionTimeMs: resolvedExecutionTimeMs,
    lastError: null,
    updatedAt: endedAt,
    history: finalizeLatestAttempt(existing.history, {
      attempt: resolvedAttempt,
      status: "completed",
      endedAt,
      executionTimeMs: resolvedExecutionTimeMs,
      summary,
    }),
  };
  const { [agentId]: _, ...remainingActive } = state.activeAgents;
  return {
    activeAgents: remainingActive,
    completedAgents: upsertCompletedAgent(state.completedAgents, completed),
  };
}

export function setAgentError(
  state: AgentSlice,
  agentId: string,
  error: string,
  executionTimeMs?: number,
  attempt?: number,
): AgentSlice {
  const existing = state.activeAgents[agentId] ?? findCompletedAgent(state, agentId);
  if (!existing) return state;

  const endedAt = Date.now();
  const resolvedAttempt = attempt ?? existing.attemptCount;
  const resolvedExecutionTimeMs =
    typeof executionTimeMs === "number" && executionTimeMs >= 0
      ? executionTimeMs
      : Math.max(0, endedAt - existing.startTime);
  const latestAttempt = existing.history[existing.history.length - 1];
  const failureIncrement =
    latestAttempt?.attempt === resolvedAttempt && latestAttempt.status === "error" ? 0 : 1;
  const failed: AgentInfo = {
    ...existing,
    status: "error",
    summary: error,
    latestExecutionTimeMs: resolvedExecutionTimeMs,
    lastError: error,
    updatedAt: endedAt,
    failureCount: existing.failureCount + failureIncrement,
    history: finalizeLatestAttempt(existing.history, {
      attempt: resolvedAttempt,
      status: "error",
      endedAt,
      executionTimeMs: resolvedExecutionTimeMs,
      summary: error,
    }),
  };
  const { [agentId]: _, ...remainingActive } = state.activeAgents;
  return {
    activeAgents: remainingActive,
    completedAgents: upsertCompletedAgent(state.completedAgents, failed),
  };
}
