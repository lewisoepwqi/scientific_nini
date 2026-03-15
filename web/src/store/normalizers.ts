/**
 * 数据规范化函数
 */

import type {
  IntentOption,
  IntentCandidateView,
  IntentSkillCall,
  IntentSkillSummary,
  IntentAnalysisView,
  PlanStepStatus,
  AnalysisStep,
  AnalysisTaskAttemptStatus,
} from "./types";
import { isRecord } from "./utils";

export function normalizeIntentOption(raw: unknown): IntentOption | null {
  if (!isRecord(raw)) return null;
  const label = typeof raw.label === "string" ? raw.label.trim() : "";
  const description = typeof raw.description === "string" ? raw.description.trim() : "";
  if (!label || !description) return null;
  return { label, description };
}

export function normalizeIntentCandidate(raw: unknown): IntentCandidateView | null {
  if (!isRecord(raw)) return null;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  const reason = typeof raw.reason === "string" ? raw.reason.trim() : "";
  const score = typeof raw.score === "number" ? raw.score : 0;
  if (!name) return null;
  return { name, score, reason };
}

export function normalizeIntentSkillCall(raw: unknown): IntentSkillCall | null {
  if (!isRecord(raw)) return null;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return null;
  return {
    name,
    arguments: typeof raw.arguments === "string" ? raw.arguments : "",
  };
}

export function normalizeIntentSkillSummary(raw: unknown): IntentSkillSummary | null {
  if (!isRecord(raw)) return null;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return null;
  const allowedTools = Array.isArray(raw.allowed_tools)
    ? raw.allowed_tools
        .map((item: unknown) => (typeof item === "string" ? item.trim() : ""))
        .filter(Boolean)
    : [];
  return {
    name,
    description: typeof raw.description === "string" ? raw.description.trim() : "",
    category: typeof raw.category === "string" ? raw.category.trim() || "other" : "other",
    research_domain: typeof raw.research_domain === "string" ? raw.research_domain.trim() || "general" : "general",
    difficulty_level: typeof raw.difficulty_level === "string" ? raw.difficulty_level.trim() || "intermediate" : "intermediate",
    location: typeof raw.location === "string" ? raw.location.trim() : "",
    allowed_tools: allowedTools,
  };
}

export function normalizeIntentAnalysis(raw: unknown): IntentAnalysisView | null {
  if (!isRecord(raw)) return null;
  return {
    query: typeof raw.query === "string" ? raw.query.trim() : "",
    capability_candidates: Array.isArray(raw.capability_candidates)
      ? raw.capability_candidates.map(normalizeIntentCandidate).filter(Boolean) as IntentCandidateView[]
      : [],
    skill_candidates: Array.isArray(raw.skill_candidates)
      ? raw.skill_candidates.map(normalizeIntentCandidate).filter(Boolean) as IntentCandidateView[]
      : [],
    explicit_skill_calls: Array.isArray(raw.explicit_skill_calls)
      ? raw.explicit_skill_calls.map(normalizeIntentSkillCall).filter(Boolean) as IntentSkillCall[]
      : [],
    active_skills: Array.isArray(raw.active_skills)
      ? raw.active_skills.map(normalizeIntentSkillSummary).filter(Boolean) as IntentSkillSummary[]
      : [],
    tool_hints: Array.isArray(raw.tool_hints)
      ? raw.tool_hints.map((item: unknown) => (typeof item === "string" ? item.trim() : "")).filter(Boolean)
      : [],
    allowed_tools: Array.isArray(raw.allowed_tools)
      ? raw.allowed_tools.map((item: unknown) => (typeof item === "string" ? item.trim() : "")).filter(Boolean)
      : [],
    allowed_tool_sources: Array.isArray(raw.allowed_tool_sources)
      ? raw.allowed_tool_sources.map((item: unknown) => (typeof item === "string" ? item.trim() : "")).filter(Boolean)
      : [],
    clarification_needed: raw.clarification_needed === true,
    clarification_question:
      typeof raw.clarification_question === "string" ? raw.clarification_question.trim() : null,
    clarification_options: Array.isArray(raw.clarification_options)
      ? raw.clarification_options.map(normalizeIntentOption).filter(Boolean) as IntentOption[]
      : [],
    analysis_method: typeof raw.analysis_method === "string" ? raw.analysis_method.trim() || "rule_based_v1" : "rule_based_v1",
  };
}

export function normalizePlanStepStatus(raw: unknown): PlanStepStatus {
  if (typeof raw !== "string") return "not_started";
  const normalized = raw.trim().toLowerCase();
  switch (normalized) {
    case "pending":
    case "not_started":
      return "not_started";
    case "in_progress":
      return "in_progress";
    case "completed":
    case "done":
      return "done";
    case "error":
    case "failed":
      return "failed";
    case "blocked":
      return "blocked";
    case "skipped":
      return "skipped";
    default:
      return "not_started";
  }
}

export function normalizeTaskAttemptStatus(raw: unknown): AnalysisTaskAttemptStatus {
  if (typeof raw !== "string") return "in_progress";
  const normalized = raw.trim().toLowerCase();
  switch (normalized) {
    case "retrying":
      return "retrying";
    case "success":
    case "done":
      return "success";
    case "failed":
    case "error":
      return "failed";
    default:
      return "in_progress";
  }
}

const REASONING_MARKER_PATTERN = /<\/?think>|<\/?thinking>|◁think▷|◁\/think▷/gi;
const REASONING_TOOL_WRAP_PATTERN =
  /<\/?(tool_call|arg_key|arg_value)>|<\/arg_key><arg_value>/gi;
const REASONING_TOOL_LEAK_PATTERN =
  /(content|file_path|operation|tasks|chart_id)<\/arg_key><arg_value>/i;

export function stripReasoningMarkers(text: string): string {
  if (!text) return text;
  return text.replace(REASONING_MARKER_PATTERN, "");
}

export function looksLikeToolCallReasoningPollution(text: string): boolean {
  const normalized = String(text || "").trim();
  if (!normalized) return false;
  if (REASONING_TOOL_WRAP_PATTERN.test(normalized)) return true;
  if (REASONING_TOOL_LEAK_PATTERN.test(normalized)) return true;
  return (
    normalized.length > 240 &&
    normalized.includes("</arg_key><arg_value>") &&
    normalized.includes("</arg_value>")
  );
}

export function isTerminalPlanStepStatus(status: PlanStepStatus): boolean {
  return status === "done" || status === "skipped";
}

export function mergePlanStepStatus(
  current: PlanStepStatus,
  incoming: PlanStepStatus,
): PlanStepStatus {
  if (current === incoming) return current;
  if (isTerminalPlanStepStatus(current)) return current;

  if (incoming === "done" || incoming === "skipped") {
    return incoming;
  }

  if (incoming === "in_progress") {
    return "in_progress";
  }

  if (incoming === "failed") {
    return "failed";
  }

  if (incoming === "blocked") {
    return current === "failed" ? current : "blocked";
  }

  return current;
}

export function truncatePlanText(text: string, maxLen = 72): string {
  const normalized = text.trim();
  if (normalized.length <= maxLen) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLen - 1)).trimEnd()}…`;
}

export function createDefaultPlanSteps(total: number): AnalysisStep[] {
  const safeTotal = Math.max(0, total);
  return Array.from({ length: safeTotal }, (_, idx) => ({
    id: idx + 1,
    title: `步骤 ${idx + 1}`,
    tool_hint: null,
    status: "not_started" as PlanStepStatus,
  }));
}

export function normalizeAnalysisSteps(rawSteps: unknown): AnalysisStep[] {
  if (!Array.isArray(rawSteps)) return [];
  return rawSteps
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item, idx) => {
      const idRaw = item.id;
      const id =
        typeof idRaw === "number" && Number.isFinite(idRaw) && idRaw > 0
          ? Math.floor(idRaw)
          : idx + 1;
      const title =
        typeof item.title === "string" && item.title.trim()
          ? item.title.trim()
          : `步骤 ${id}`;
      const toolHint =
        typeof item.tool_hint === "string" && item.tool_hint.trim()
          ? item.tool_hint.trim()
          : null;
      const status = normalizePlanStepStatus(item.status);
      // 处理 action_id 字段（用于任务与 action 的映射）
      const actionId =
        typeof item.action_id === "string" && item.action_id.trim()
          ? item.action_id.trim()
          : null;
      // 处理 raw_status 字段（后端原始状态）
      const rawStatus =
        typeof item.raw_status === "string" && item.raw_status.trim()
          ? item.raw_status.trim()
          : undefined;
      return {
        id,
        title,
        tool_hint: toolHint,
        status,
        action_id: actionId,
        raw_status: rawStatus,
      };
    });
}
