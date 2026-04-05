/**
 * 多 Agent 事件处理器
 *
 * 处理 agent_start / agent_progress / agent_complete / agent_error 事件，
 * 更新 Zustand store 中的 AgentSlice 状态。
 */

import type { WSEvent } from "./types";
import type { SetStateFn, GetStateFn } from "./event-handler";
import { isRecord } from "./utils";
import {
  setAgentStart,
  setAgentProgress,
  setAgentComplete,
  setAgentError,
  setAgentStopped,
} from "./agent-slice";

export function handleAgentEvent(
  evt: WSEvent,
  set: SetStateFn,
  get: GetStateFn,
): void {
  const data = evt.data;
  const currentSessionId = get().sessionId;
  if (
    typeof evt.session_id === "string" &&
    evt.session_id.trim() &&
    currentSessionId &&
    evt.session_id !== currentSessionId
  ) {
    return;
  }
  const metadata = isRecord(evt.metadata) ? evt.metadata : {};
  const agentIdFromData =
    isRecord(data) && typeof data.agent_id === "string" && data.agent_id.trim()
      ? data.agent_id.trim()
      : "";
  const attemptFromData =
    isRecord(data) && typeof data.attempt === "number" ? data.attempt : 1;
  const turnId =
    typeof metadata.turn_id === "string" && metadata.turn_id.trim()
      ? metadata.turn_id.trim()
      : typeof evt.turn_id === "string" && evt.turn_id.trim()
        ? evt.turn_id.trim()
        : get()._currentTurnId
          ? get()._currentTurnId
          : agentIdFromData
            ? `legacy:${agentIdFromData}`
            : "";
  const runId =
    typeof metadata.run_id === "string" && metadata.run_id.trim()
      ? metadata.run_id.trim()
      : turnId && agentIdFromData
        ? `agent:${turnId}:${agentIdFromData}:${attemptFromData}`
        : "";

  switch (evt.type) {
    case "agent_start": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const agentName = typeof data.agent_name === "string" ? data.agent_name : agentId;
      const task = typeof data.task === "string" ? data.task : "";
      const attempt = typeof data.attempt === "number" ? data.attempt : undefined;
      const retryCount =
        typeof data.retry_count === "number" ? data.retry_count : undefined;
      if (!agentId || !turnId || !runId) break;
      set((s) => setAgentStart(s, agentId, agentName, task, turnId, runId, attempt, retryCount));
      break;
    }

    case "agent_progress": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const agentName = typeof data.agent_name === "string" ? data.agent_name : agentId;
      const phase = typeof data.phase === "string" ? data.phase : "running";
      const message = typeof data.message === "string" ? data.message : "";
      const progressHint =
        typeof data.progress_hint === "string" ? data.progress_hint : undefined;
      const attempt = typeof data.attempt === "number" ? data.attempt : undefined;
      const retryCount =
        typeof data.retry_count === "number" ? data.retry_count : undefined;
      if (!agentId || !turnId || !runId) break;
      set((s) =>
        setAgentProgress(
          s,
          agentId,
          agentName,
          turnId,
          runId,
          phase,
          message,
          progressHint,
          attempt,
          retryCount,
        ),
      );
      break;
    }

    case "agent_complete": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const summary = typeof data.summary === "string" ? data.summary : "";
      const executionTimeMs =
        typeof data.execution_time_ms === "number" ? data.execution_time_ms : undefined;
      const attempt = typeof data.attempt === "number" ? data.attempt : undefined;
      if (!agentId || !turnId || !runId) break;
      set((s) => setAgentComplete(s, agentId, summary, turnId, runId, executionTimeMs, attempt));
      break;
    }

    case "agent_error": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const error = typeof data.error === "string" ? data.error : "未知错误";
      const executionTimeMs =
        typeof data.execution_time_ms === "number" ? data.execution_time_ms : undefined;
      const attempt = typeof data.attempt === "number" ? data.attempt : undefined;
      if (!agentId || !turnId || !runId) break;
      set((s) => setAgentError(s, agentId, error, turnId, runId, executionTimeMs, attempt));
      break;
    }

    case "agent_stopped": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const reason = typeof data.reason === "string" ? data.reason : "用户已终止";
      const executionTimeMs =
        typeof data.execution_time_ms === "number" ? data.execution_time_ms : undefined;
      const attempt = typeof data.attempt === "number" ? data.attempt : undefined;
      if (!agentId || !turnId || !runId) break;
      set((s) =>
        setAgentStopped(s, agentId, reason, turnId, runId, executionTimeMs, attempt),
      );
      break;
    }
  }
}
