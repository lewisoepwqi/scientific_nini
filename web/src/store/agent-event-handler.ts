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
  setAgentComplete,
  setAgentError,
} from "./agent-slice";

export function handleAgentEvent(
  evt: WSEvent,
  set: SetStateFn,
  _get: GetStateFn,
): void {
  const data = evt.data;

  switch (evt.type) {
    case "agent_start": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const agentName = typeof data.agent_name === "string" ? data.agent_name : agentId;
      const task = typeof data.task === "string" ? data.task : "";
      if (!agentId) break;
      set((s) => setAgentStart(s, agentId, agentName, task));
      break;
    }

    case "agent_progress": {
      // Phase 1 仅记录日志，payload 结构在 Phase 2 规划
      break;
    }

    case "agent_complete": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const summary = typeof data.summary === "string" ? data.summary : "";
      if (!agentId) break;
      set((s) => setAgentComplete(s, agentId, summary));
      break;
    }

    case "agent_error": {
      if (!isRecord(data)) break;
      const agentId = typeof data.agent_id === "string" ? data.agent_id : "";
      const error = typeof data.error === "string" ? data.error : "未知错误";
      if (!agentId) break;
      set((s) => setAgentError(s, agentId, error));
      break;
    }
  }
}
