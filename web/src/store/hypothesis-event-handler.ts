/**
 * Hypothesis-Driven 范式事件处理器
 *
 * 处理 hypothesis_generated / evidence_collected / hypothesis_validated /
 * hypothesis_refuted / paradigm_switched 事件，更新 Zustand store 中的 HypothesisSlice 状态。
 */

import type { WSEvent, HypothesisInfo } from "./types";
import type { SetStateFn, GetStateFn } from "./event-handler";
import { isRecord } from "./utils";
import {
  setHypothesesGenerated,
  addEvidence,
  setHypothesisValidated,
  setHypothesisRefuted,
  setParadigmSwitched,
} from "./hypothesis-slice";

export function handleHypothesisEvent(
  evt: WSEvent,
  set: SetStateFn,
  _get: GetStateFn,
): void {
  const data = evt.data;

  switch (evt.type) {
    case "paradigm_switched": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      if (!agentId) break;
      set((s) => ({ ...s, ...setParadigmSwitched(s, agentId) }));
      break;
    }

    case "hypothesis_generated": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const rawList = Array.isArray(data.hypotheses) ? data.hypotheses : [];
      const hypotheses: HypothesisInfo[] = rawList
        .filter(isRecord)
        .map((h) => ({
          id: typeof h.id === "string" ? h.id : String(Math.random()),
          content: typeof h.content === "string" ? h.content : "",
          confidence: typeof h.confidence === "number" ? h.confidence : 0.5,
          status: "pending" as const,
          evidenceFor: [],
          evidenceAgainst: [],
        }));
      set((s) => ({ ...s, ...setHypothesesGenerated(s, agentId, hypotheses) }));
      break;
    }

    case "evidence_collected": {
      if (!isRecord(data)) break;
      const hypothesisId = typeof data.hypothesis_id === "string" ? data.hypothesis_id : "";
      const evidenceType = data.evidence_type === "against" ? "against" : ("for" as const);
      const content = typeof data.content === "string" ? data.content : "";
      if (!hypothesisId) break;
      set((s) => ({ ...s, ...addEvidence(s, hypothesisId, evidenceType, content) }));
      break;
    }

    case "hypothesis_validated": {
      if (!isRecord(data)) break;
      const hypothesisId = typeof data.hypothesis_id === "string" ? data.hypothesis_id : "";
      const confidence = typeof data.confidence === "number" ? data.confidence : 1.0;
      if (!hypothesisId) break;
      set((s) => ({ ...s, ...setHypothesisValidated(s, hypothesisId, confidence) }));
      break;
    }

    case "hypothesis_refuted": {
      if (!isRecord(data)) break;
      const hypothesisId = typeof data.hypothesis_id === "string" ? data.hypothesis_id : "";
      if (!hypothesisId) break;
      set((s) => ({ ...s, ...setHypothesisRefuted(s, hypothesisId) }));
      break;
    }
  }
}
