import type {
  AnalysisPlanProgress,
  AnalysisTaskItem,
  CompletionCheckState,
  DeepTaskState,
  HarnessBlockedState,
  HarnessRunContextState,
  IntentAnalysisView,
  Message,
  SkillExecutionState,
  StreamingMetrics,
  TokenUsage,
  AgentRunThread,
  AgentRunGroup,
  DispatchLedgerSummary,
} from "./types";

export interface SessionUiCacheEntry {
  messages: Message[];
  analysisTasks: AnalysisTaskItem[];
  analysisPlanProgress: AnalysisPlanProgress | null;
  harnessRunContext: HarnessRunContextState | null;
  completionCheck: CompletionCheckState | null;
  blockedState: HarnessBlockedState | null;
  currentIntentAnalysis: IntentAnalysisView | null;
  workspacePanelTab: "files" | "executions" | "tasks";
  streamingMetrics: StreamingMetrics;
  tokenUsage: TokenUsage | null;
  activeRecipeId: string | null;
  deepTaskState: DeepTaskState | null;
  skillExecution: SkillExecutionState | null;
  currentTurnId: string | null;
  streamingText: string;
  lastHandledSeq: number | undefined;
  activePlanMsgId: string | null;
  analysisPlanOrder: number;
  activePlanTaskIds: Array<string | null>;
  planActionTaskMap: Record<string, string>;
  agentRuns: Record<string, AgentRunThread>;
  agentRunTabs: string[];
  selectedRunId: string | null;
  unreadByRun: Record<string, number>;
  runGroupsByTurn: Record<string, AgentRunGroup>;
  dispatchLedgers: DispatchLedgerSummary[];
}

export interface SessionUiCacheSnapshotSource {
  messages: Message[];
  analysisTasks: AnalysisTaskItem[];
  analysisPlanProgress: AnalysisPlanProgress | null;
  harnessRunContext: HarnessRunContextState | null;
  completionCheck: CompletionCheckState | null;
  blockedState: HarnessBlockedState | null;
  currentIntentAnalysis: IntentAnalysisView | null;
  workspacePanelTab: "files" | "executions" | "tasks";
  _streamingMetrics: StreamingMetrics;
  tokenUsage: TokenUsage | null;
  activeRecipeId: string | null;
  deepTaskState: DeepTaskState | null;
  skillExecution: SkillExecutionState | null;
  _currentTurnId: string | null;
  _streamingText: string;
  _lastHandledSeq: number | undefined;
  _activePlanMsgId: string | null;
  _analysisPlanOrder: number;
  _activePlanTaskIds: Array<string | null>;
  _planActionTaskMap: Record<string, string>;
  agentRuns: Record<string, AgentRunThread>;
  agentRunTabs: string[];
  selectedRunId: string | null;
  unreadByRun: Record<string, number>;
  runGroupsByTurn: Record<string, AgentRunGroup>;
  dispatchLedgers: DispatchLedgerSummary[];
}

const MAX_SESSION_CACHE = 10;
const sessionUiCache = new Map<string, SessionUiCacheEntry>();

export function cloneMessages(messages: Message[]): Message[] {
  return messages.map((message) => ({ ...message }));
}

export function cloneAnalysisTasks(tasks: AnalysisTaskItem[]): AnalysisTaskItem[] {
  return tasks.map((task) => ({
    ...task,
    attempts: task.attempts.map((attempt) => ({ ...attempt })),
  }));
}

export function clonePlanProgress(
  progress: AnalysisPlanProgress | null,
): AnalysisPlanProgress | null {
  if (!progress) return null;
  return {
    ...progress,
    steps: progress.steps.map((step) => ({ ...step })),
  };
}

export function cloneStreamingMetrics(metrics: StreamingMetrics): StreamingMetrics {
  return { ...metrics };
}

export function cloneTokenUsage(tokenUsage: TokenUsage | null): TokenUsage | null {
  if (!tokenUsage) return null;
  const modelBreakdown = tokenUsage.model_breakdown ?? {};
  return {
    ...tokenUsage,
    model_breakdown: Object.fromEntries(
      Object.entries(modelBreakdown).map(([model, usage]) => [
        model,
        { ...usage },
      ]),
    ),
  };
}

export function cloneSkillExecution(
  skillExecution: SkillExecutionState | null,
): SkillExecutionState | null {
  if (!skillExecution) return null;
  return {
    ...skillExecution,
    steps: skillExecution.steps.map((step) => ({ ...step })),
  };
}

export function createEmptySessionUiCacheEntry(): SessionUiCacheEntry {
  return {
    messages: [],
    analysisTasks: [],
    analysisPlanProgress: null,
    harnessRunContext: null,
    completionCheck: null,
    blockedState: null,
    currentIntentAnalysis: null,
    workspacePanelTab: "files",
    streamingMetrics: {
      startedAt: null,
      turnId: null,
      totalTokens: 0,
      hasTokenUsage: false,
    },
    tokenUsage: null,
    activeRecipeId: null,
    deepTaskState: null,
    skillExecution: null,
    currentTurnId: null,
    streamingText: "",
    lastHandledSeq: undefined,
    activePlanMsgId: null,
    analysisPlanOrder: 0,
    activePlanTaskIds: [],
    planActionTaskMap: {},
    agentRuns: {},
    agentRunTabs: [],
    selectedRunId: null,
    unreadByRun: {},
    runGroupsByTurn: {},
    dispatchLedgers: [],
  };
}

function cloneDispatchLedgers(
  ledgers: DispatchLedgerSummary[],
): DispatchLedgerSummary[] {
  return ledgers.map((ledger) => ({
    ...ledger,
    failures: Array.isArray(ledger.failures)
      ? ledger.failures.map((item) => ({ ...item }))
      : ledger.failures ?? null,
    dispatch_ledger: Array.isArray(ledger.dispatch_ledger)
      ? ledger.dispatch_ledger.map((item) => ({ ...item }))
      : ledger.dispatch_ledger ?? null,
  }));
}

function cloneAgentRuns(
  agentRuns: Record<string, AgentRunThread>,
): Record<string, AgentRunThread> {
  return Object.fromEntries(
    Object.entries(agentRuns).map(([runId, run]) => [
      runId,
      {
        ...run,
        messages: cloneMessages(run.messages),
        failures: Array.isArray(run.failures)
          ? run.failures.map((item) => ({ ...item }))
          : run.failures ?? null,
        dispatchLedger: Array.isArray(run.dispatchLedger)
          ? run.dispatchLedger.map((item) => ({ ...item }))
          : run.dispatchLedger ?? null,
      },
    ]),
  );
}

function cloneRunGroups(
  groups: Record<string, AgentRunGroup>,
): Record<string, AgentRunGroup> {
  return Object.fromEntries(
    Object.entries(groups).map(([turnId, group]) => [
      turnId,
      {
        ...group,
        runIds: [...group.runIds],
      },
    ]),
  );
}

export function cloneSessionUiCacheEntry(
  entry: SessionUiCacheEntry,
): SessionUiCacheEntry {
  return {
    messages: cloneMessages(entry.messages),
    analysisTasks: cloneAnalysisTasks(entry.analysisTasks),
    analysisPlanProgress: clonePlanProgress(entry.analysisPlanProgress),
    harnessRunContext: entry.harnessRunContext
      ? { ...entry.harnessRunContext }
      : null,
    completionCheck: entry.completionCheck
      ? {
          ...entry.completionCheck,
          items: entry.completionCheck.items.map((item) => ({ ...item })),
          missingActions: [...entry.completionCheck.missingActions],
        }
      : null,
    blockedState: entry.blockedState ? { ...entry.blockedState } : null,
    currentIntentAnalysis: entry.currentIntentAnalysis
      ? ({ ...entry.currentIntentAnalysis } as IntentAnalysisView)
      : null,
    workspacePanelTab: entry.workspacePanelTab,
    streamingMetrics: cloneStreamingMetrics(entry.streamingMetrics),
    tokenUsage: cloneTokenUsage(entry.tokenUsage),
    activeRecipeId: entry.activeRecipeId,
    deepTaskState: entry.deepTaskState ? { ...entry.deepTaskState } : null,
    skillExecution: cloneSkillExecution(entry.skillExecution),
    currentTurnId: entry.currentTurnId,
    streamingText: entry.streamingText,
    lastHandledSeq: entry.lastHandledSeq,
    activePlanMsgId: entry.activePlanMsgId,
    analysisPlanOrder: entry.analysisPlanOrder,
    activePlanTaskIds: [...entry.activePlanTaskIds],
    planActionTaskMap: { ...entry.planActionTaskMap },
    agentRuns: cloneAgentRuns(entry.agentRuns),
    agentRunTabs: [...entry.agentRunTabs],
    selectedRunId: entry.selectedRunId,
    unreadByRun: { ...entry.unreadByRun },
    runGroupsByTurn: cloneRunGroups(entry.runGroupsByTurn),
    dispatchLedgers: cloneDispatchLedgers(entry.dispatchLedgers),
  };
}

export function captureSessionUiCacheEntry(
  source: SessionUiCacheSnapshotSource,
): SessionUiCacheEntry {
  return {
    messages: cloneMessages(source.messages),
    analysisTasks: cloneAnalysisTasks(source.analysisTasks),
    analysisPlanProgress: clonePlanProgress(source.analysisPlanProgress),
    harnessRunContext: source.harnessRunContext
      ? { ...source.harnessRunContext }
      : null,
    completionCheck: source.completionCheck
      ? {
          ...source.completionCheck,
          items: source.completionCheck.items.map((item) => ({ ...item })),
          missingActions: [...source.completionCheck.missingActions],
        }
      : null,
    blockedState: source.blockedState ? { ...source.blockedState } : null,
    currentIntentAnalysis: source.currentIntentAnalysis
      ? ({ ...source.currentIntentAnalysis } as IntentAnalysisView)
      : null,
    workspacePanelTab: source.workspacePanelTab,
    streamingMetrics: cloneStreamingMetrics(source._streamingMetrics),
    tokenUsage: cloneTokenUsage(source.tokenUsage),
    activeRecipeId: source.activeRecipeId,
    deepTaskState: source.deepTaskState ? { ...source.deepTaskState } : null,
    skillExecution: cloneSkillExecution(source.skillExecution),
    currentTurnId: source._currentTurnId,
    streamingText: source._streamingText,
    lastHandledSeq: source._lastHandledSeq,
    activePlanMsgId: source._activePlanMsgId,
    analysisPlanOrder: source._analysisPlanOrder,
    activePlanTaskIds: [...source._activePlanTaskIds],
    planActionTaskMap: { ...source._planActionTaskMap },
    agentRuns: cloneAgentRuns(source.agentRuns),
    agentRunTabs: [...source.agentRunTabs],
    selectedRunId: source.selectedRunId,
    unreadByRun: { ...source.unreadByRun },
    runGroupsByTurn: cloneRunGroups(source.runGroupsByTurn),
    dispatchLedgers: cloneDispatchLedgers(source.dispatchLedgers),
  };
}

function touchSessionUiCacheEntry(sessionId: string, entry: SessionUiCacheEntry): void {
  if (sessionUiCache.has(sessionId)) {
    sessionUiCache.delete(sessionId);
  }
  sessionUiCache.set(sessionId, entry);
  if (sessionUiCache.size > MAX_SESSION_CACHE) {
    const oldest = sessionUiCache.keys().next().value;
    if (oldest !== undefined) {
      sessionUiCache.delete(oldest);
    }
  }
}

export function getSessionUiCacheEntry(
  sessionId: string,
): SessionUiCacheEntry | undefined {
  const entry = sessionUiCache.get(sessionId);
  if (!entry) return undefined;
  touchSessionUiCacheEntry(sessionId, entry);
  return cloneSessionUiCacheEntry(entry);
}

export function setSessionUiCacheEntry(
  sessionId: string,
  entry: SessionUiCacheEntry,
): void {
  touchSessionUiCacheEntry(sessionId, cloneSessionUiCacheEntry(entry));
}

export function updateSessionUiCacheEntry(
  sessionId: string,
  updater: (entry: SessionUiCacheEntry) => SessionUiCacheEntry,
): SessionUiCacheEntry {
  const current = sessionUiCache.get(sessionId);
  const next = updater(
    current ? cloneSessionUiCacheEntry(current) : createEmptySessionUiCacheEntry(),
  );
  touchSessionUiCacheEntry(sessionId, next);
  return cloneSessionUiCacheEntry(next);
}

export function deleteSessionUiCacheEntry(sessionId: string): void {
  sessionUiCache.delete(sessionId);
}

export function clearAllSessionUiCacheEntries(): void {
  sessionUiCache.clear();
}
