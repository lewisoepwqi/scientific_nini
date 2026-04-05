/**
 * Agent 执行与子运行线程切片
 *
 * 管理并行子 Agent 的生命周期、线程消息与 tab 选择状态。
 */

import type {
  AgentAttemptInfo,
  AgentInfo,
  AgentRunGroup,
  AgentRunStatus,
  AgentRunThread,
  AgentSlice,
  Message,
} from "./types";

const MAX_AGENT_HISTORY = 8;

export const ROOT_RUN_LABEL = "主 Agent";

export function buildRootRunId(turnId: string): string {
  return `root:${turnId}`;
}

export function buildAgentRunId(
  turnId: string,
  agentId: string,
  attempt: number,
): string {
  return `agent:${turnId}:${agentId}:${attempt}`;
}

export const initialAgentSlice: AgentSlice = {
  activeAgents: {},
  completedAgents: [],
  agentRuns: {},
  agentRunTabs: [],
  selectedRunId: null,
  unreadByRun: {},
  runGroupsByTurn: {},
  lastViewedRunIdBySession: {},
};

function clampHistory(history: AgentAttemptInfo[]): AgentAttemptInfo[] {
  if (history.length <= MAX_AGENT_HISTORY) return history;
  return history.slice(history.length - MAX_AGENT_HISTORY);
}

function sortRunIds(agentRuns: Record<string, AgentRunThread>, runIds: string[]): string[] {
  const rootRunIds = runIds.filter((runId) => agentRuns[runId]?.runScope === "root");
  const subagentRunIds = runIds
    .filter((runId) => agentRuns[runId]?.runScope === "subagent")
    .sort((left, right) => {
      const leftRun = agentRuns[left];
      const rightRun = agentRuns[right];
      const leftPriority = leftRun?.status === "running" ? 0 : 1;
      const rightPriority = rightRun?.status === "running" ? 0 : 1;
      if (leftPriority !== rightPriority) return leftPriority - rightPriority;
      return (rightRun?.updatedAt ?? 0) - (leftRun?.updatedAt ?? 0);
    });
  return [...rootRunIds, ...subagentRunIds];
}

export function ensureRootRun(
  state: AgentSlice,
  turnId: string,
  updatedAt: number = Date.now(),
): AgentSlice {
  const rootRunId = buildRootRunId(turnId);
  const existing = state.agentRuns[rootRunId];
  const nextRun: AgentRunThread = existing ?? {
    runId: rootRunId,
    turnId,
    parentRunId: null,
    runScope: "root",
    agentId: null,
    agentName: ROOT_RUN_LABEL,
    status: "running",
    task: "",
    attempt: 1,
    retryCount: 0,
    startTime: updatedAt,
    updatedAt,
    latestExecutionTimeMs: null,
    summary: undefined,
    lastError: null,
    phase: null,
    progressMessage: null,
    progressHint: null,
    messages: [],
  };
  const currentGroup = state.runGroupsByTurn[turnId];
  const nextGroup: AgentRunGroup = currentGroup
    ? {
        ...currentGroup,
        rootRunId,
        runIds: currentGroup.runIds.includes(rootRunId)
          ? currentGroup.runIds
          : sortRunIds(state.agentRuns, [rootRunId, ...currentGroup.runIds]),
        updatedAt,
      }
    : {
        turnId,
        rootRunId,
        runIds: [rootRunId],
        updatedAt,
      };
  const nextRuns = {
    ...state.agentRuns,
    [rootRunId]: {
      ...nextRun,
      updatedAt: Math.max(nextRun.updatedAt, updatedAt),
    },
  };
  const nextTabs = sortRunIds(nextRuns, nextGroup.runIds);
  return {
    ...state,
    agentRuns: nextRuns,
    runGroupsByTurn: {
      ...state.runGroupsByTurn,
      [turnId]: {
        ...nextGroup,
        runIds: nextTabs,
      },
    },
    agentRunTabs: nextTabs,
    selectedRunId: state.selectedRunId ?? rootRunId,
  };
}

export function upsertAgentRun(
  state: AgentSlice,
  run: AgentRunThread,
): AgentSlice {
  const ensured = ensureRootRun(state, run.turnId, run.updatedAt);
  const currentGroup = ensured.runGroupsByTurn[run.turnId];
  const nextRunIds = currentGroup.runIds.includes(run.runId)
    ? currentGroup.runIds
    : [...currentGroup.runIds, run.runId];
  const nextRuns = {
    ...ensured.agentRuns,
    [run.runId]: run,
  };
  const sortedRunIds = sortRunIds(nextRuns, nextRunIds);
  return {
    ...ensured,
    agentRuns: nextRuns,
    runGroupsByTurn: {
      ...ensured.runGroupsByTurn,
      [run.turnId]: {
        ...currentGroup,
        runIds: sortedRunIds,
        updatedAt: run.updatedAt,
      },
    },
    agentRunTabs: sortedRunIds,
  };
}

export function appendAgentRunMessage(
  state: AgentSlice,
  runId: string,
  message: Message,
): AgentSlice {
  const thread = state.agentRuns[runId];
  if (!thread) return state;
  const nextThread: AgentRunThread = {
    ...thread,
    messages: [...thread.messages, message],
    updatedAt: Math.max(thread.updatedAt, message.timestamp),
  };
  return upsertAgentRun(state, nextThread);
}

export function replaceAgentRunMessages(
  state: AgentSlice,
  runId: string,
  messages: Message[],
): AgentSlice {
  const thread = state.agentRuns[runId];
  if (!thread) return state;
  return upsertAgentRun(state, {
    ...thread,
    messages,
    updatedAt: messages[messages.length - 1]?.timestamp ?? thread.updatedAt,
  });
}

export function selectAgentRun(
  state: AgentSlice,
  runId: string | null,
): AgentSlice {
  if (!runId) {
    return {
      ...state,
      selectedRunId: null,
    };
  }
  return {
    ...state,
    selectedRunId: runId,
    unreadByRun: {
      ...state.unreadByRun,
      [runId]: 0,
    },
  };
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

function upsertUnread(state: AgentSlice, runId: string): Record<string, number> {
  if (state.selectedRunId === runId) {
    return { ...state.unreadByRun, [runId]: 0 };
  }
  return {
    ...state.unreadByRun,
    [runId]: (state.unreadByRun[runId] ?? 0) + 1,
  };
}

function updateRunStatus(
  state: AgentSlice,
  {
    runId,
    turnId,
    agentId,
    agentName,
    task,
    attempt,
    retryCount,
    status,
    updatedAt,
    summary,
    executionTimeMs,
    phase,
    progressMessage,
    progressHint,
  }: {
    runId: string;
    turnId: string;
    agentId: string;
    agentName: string;
    task: string;
    attempt: number;
    retryCount: number;
    status: AgentRunStatus;
    updatedAt: number;
    summary?: string;
    executionTimeMs?: number | null;
    phase?: string | null;
    progressMessage?: string | null;
    progressHint?: string | null;
  },
): AgentSlice {
  const existing = state.agentRuns[runId];
  const run: AgentRunThread = existing
    ? {
        ...existing,
        agentName,
        task: task || existing.task,
        attempt,
        retryCount,
        status,
        updatedAt,
        latestExecutionTimeMs:
          executionTimeMs ?? existing.latestExecutionTimeMs ?? null,
        summary: summary ?? existing.summary,
        lastError: status === "error" ? summary ?? existing.lastError : null,
        phase: phase ?? existing.phase,
        progressMessage: progressMessage ?? existing.progressMessage,
        progressHint: progressHint ?? existing.progressHint,
      }
    : {
        runId,
        turnId,
        parentRunId: buildRootRunId(turnId),
        runScope: "subagent",
        agentId,
        agentName,
        status,
        task,
        attempt,
        retryCount,
        startTime: updatedAt,
        updatedAt,
        latestExecutionTimeMs: executionTimeMs ?? null,
        summary,
        lastError: status === "error" ? summary ?? null : null,
        phase: phase ?? null,
        progressMessage: progressMessage ?? null,
        progressHint: progressHint ?? null,
        messages: [],
      };
  const nextState = upsertAgentRun(state, run);
  return {
    ...nextState,
    unreadByRun: upsertUnread(nextState, runId),
  };
}

export function setAgentStart(
  state: AgentSlice,
  agentId: string,
  agentName: string,
  task: string,
  turnId: string,
  runId: string,
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
  const nextState = updateRunStatus(
    {
      ...state,
      completedAgents: remainingCompleted,
      activeAgents: { ...state.activeAgents, [agentId]: info },
    },
    {
      runId,
      turnId,
      agentId,
      agentName,
      task,
      attempt: nextAttempt,
      retryCount: retryCount ?? Math.max(0, nextAttempt - 1),
      status: "running",
      updatedAt: now,
      phase: "starting",
      progressMessage: task,
    },
  );
  return nextState;
}

export function setAgentProgress(
  state: AgentSlice,
  agentId: string,
  agentName: string,
  turnId: string,
  runId: string,
  phase: string,
  message: string,
  progressHint?: string,
  attempt?: number,
  retryCount?: number,
): AgentSlice {
  const existing = state.agentRuns[runId];
  return updateRunStatus(state, {
    runId,
    turnId,
    agentId,
    agentName,
    task: existing?.task ?? "",
    attempt: attempt ?? existing?.attempt ?? 1,
    retryCount: retryCount ?? existing?.retryCount ?? 0,
    status: existing?.status ?? "running",
    updatedAt: Date.now(),
    phase,
    progressMessage: message,
    progressHint,
  });
}

export function setAgentComplete(
  state: AgentSlice,
  agentId: string,
  summary: string,
  turnId: string,
  runId: string,
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
  const nextState = updateRunStatus(
    {
      ...state,
      activeAgents: remainingActive,
      completedAgents: upsertCompletedAgent(state.completedAgents, completed),
    },
    {
      runId,
      turnId,
      agentId,
      agentName: existing.agentName,
      task: existing.task,
      attempt: resolvedAttempt,
      retryCount: Math.max(0, resolvedAttempt - 1),
      status: "completed",
      updatedAt: endedAt,
      summary,
      executionTimeMs: resolvedExecutionTimeMs,
      phase: "completed",
      progressMessage: summary,
    },
  );
  return nextState;
}

function finalizeAgentState(
  state: AgentSlice,
  agentId: string,
  summary: string,
  turnId: string,
  runId: string,
  status: "error" | "stopped",
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
    status === "error" &&
    !(latestAttempt?.attempt === resolvedAttempt && latestAttempt.status === "error")
      ? 1
      : 0;
  const finalized: AgentInfo = {
    ...existing,
    status,
    summary,
    latestExecutionTimeMs: resolvedExecutionTimeMs,
    lastError: status === "error" ? summary : null,
    updatedAt: endedAt,
    failureCount: existing.failureCount + failureIncrement,
    history: finalizeLatestAttempt(existing.history, {
      attempt: resolvedAttempt,
      status,
      endedAt,
      executionTimeMs: resolvedExecutionTimeMs,
      summary,
    }),
  };
  const { [agentId]: _, ...remainingActive } = state.activeAgents;
  const nextState = updateRunStatus(
    {
      ...state,
      activeAgents: remainingActive,
      completedAgents: upsertCompletedAgent(state.completedAgents, finalized),
    },
    {
      runId,
      turnId,
      agentId,
      agentName: existing.agentName,
      task: existing.task,
      attempt: resolvedAttempt,
      retryCount: Math.max(0, resolvedAttempt - 1),
      status,
      updatedAt: endedAt,
      summary,
      executionTimeMs: resolvedExecutionTimeMs,
      phase: status,
      progressMessage: summary,
    },
  );
  return nextState;
}

export function setAgentError(
  state: AgentSlice,
  agentId: string,
  error: string,
  turnId: string,
  runId: string,
  executionTimeMs?: number,
  attempt?: number,
): AgentSlice {
  return finalizeAgentState(
    state,
    agentId,
    error,
    turnId,
    runId,
    "error",
    executionTimeMs,
    attempt,
  );
}

export function setAgentStopped(
  state: AgentSlice,
  agentId: string,
  reason: string,
  turnId: string,
  runId: string,
  executionTimeMs?: number,
  attempt?: number,
): AgentSlice {
  return finalizeAgentState(
    state,
    agentId,
    reason,
    turnId,
    runId,
    "stopped",
    executionTimeMs,
    attempt,
  );
}
