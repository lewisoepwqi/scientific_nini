/**
 * Hypothesis-Driven 范式状态切片
 *
 * 管理假设推理过程中的假设列表、置信度及证据链。
 */

import type { HypothesisInfo, HypothesisSlice } from "./types";

export const initialHypothesisSlice: Omit<
  HypothesisSlice,
  | "setHypothesesGenerated"
  | "addEvidence"
  | "setHypothesisValidated"
  | "setHypothesisRefuted"
  | "setParadigmSwitched"
  | "clearHypotheses"
> = {
  hypotheses: [],
  currentPhase: "generation",
  iterationCount: 0,
  activeAgentId: null,
};

export function setHypothesesGenerated(
  state: Pick<HypothesisSlice, "hypotheses" | "currentPhase" | "iterationCount">,
  _agentId: string,
  hypotheses: HypothesisInfo[],
): Partial<HypothesisSlice> {
  return {
    ...state,
    hypotheses,
    currentPhase: "collection",
    iterationCount: 0,
  };
}

export function addEvidence(
  state: Pick<HypothesisSlice, "hypotheses">,
  hypothesisId: string,
  evidenceType: "for" | "against",
  content: string,
): Partial<HypothesisSlice> {
  return {
    hypotheses: state.hypotheses.map((h) => {
      if (h.id !== hypothesisId) return h;
      return evidenceType === "for"
        ? { ...h, evidenceFor: [...h.evidenceFor, content] }
        : { ...h, evidenceAgainst: [...h.evidenceAgainst, content] };
    }),
  };
}

export function setHypothesisValidated(
  state: Pick<HypothesisSlice, "hypotheses">,
  hypothesisId: string,
  confidence: number,
): Partial<HypothesisSlice> {
  return {
    hypotheses: state.hypotheses.map((h) =>
      h.id === hypothesisId ? { ...h, status: "validated" as const, confidence } : h,
    ),
  };
}

export function setHypothesisRefuted(
  state: Pick<HypothesisSlice, "hypotheses">,
  hypothesisId: string,
): Partial<HypothesisSlice> {
  return {
    hypotheses: state.hypotheses.map((h) =>
      h.id === hypothesisId ? { ...h, status: "refuted" as const } : h,
    ),
  };
}

export function setParadigmSwitched(
  _state: unknown,
  agentId: string,
): Partial<HypothesisSlice> {
  return {
    activeAgentId: agentId,
    currentPhase: "generation",
    hypotheses: [],
    iterationCount: 0,
  };
}

export function clearHypotheses(): Partial<HypothesisSlice> {
  return {
    hypotheses: [],
    currentPhase: "generation",
    iterationCount: 0,
    activeAgentId: null,
  };
}
