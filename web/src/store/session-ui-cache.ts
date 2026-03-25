import type {
  AnalysisPlanProgress,
  AnalysisTaskItem,
  CompletionCheckState,
  DeepTaskState,
  HarnessBlockedState,
  HarnessRunContextState,
  IntentAnalysisView,
  Message,
  StreamingMetrics,
  TokenUsage,
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
  currentTurnId: string | null;
  streamingText: string;
  lastHandledSeq: number | undefined;
  activePlanMsgId: string | null;
  analysisPlanOrder: number;
  activePlanTaskIds: Array<string | null>;
  planActionTaskMap: Record<string, string>;
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
  _currentTurnId: string | null;
  _streamingText: string;
  _lastHandledSeq: number | undefined;
  _activePlanMsgId: string | null;
  _analysisPlanOrder: number;
  _activePlanTaskIds: Array<string | null>;
  _planActionTaskMap: Record<string, string>;
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
    currentTurnId: null,
    streamingText: "",
    lastHandledSeq: undefined,
    activePlanMsgId: null,
    analysisPlanOrder: 0,
    activePlanTaskIds: [],
    planActionTaskMap: {},
  };
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
    currentTurnId: entry.currentTurnId,
    streamingText: entry.streamingText,
    lastHandledSeq: entry.lastHandledSeq,
    activePlanMsgId: entry.activePlanMsgId,
    analysisPlanOrder: entry.analysisPlanOrder,
    activePlanTaskIds: [...entry.activePlanTaskIds],
    planActionTaskMap: { ...entry.planActionTaskMap },
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
    currentTurnId: source._currentTurnId,
    streamingText: source._streamingText,
    lastHandledSeq: source._lastHandledSeq,
    activePlanMsgId: source._activePlanMsgId,
    analysisPlanOrder: source._analysisPlanOrder,
    activePlanTaskIds: [...source._activePlanTaskIds],
    planActionTaskMap: { ...source._planActionTaskMap },
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
