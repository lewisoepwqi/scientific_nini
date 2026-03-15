/**
 * Agent 执行状态切片
 *
 * 管理并行运行中子 Agent 的状态（activeAgents 和 completedAgents）。
 */

import type { AgentInfo, AgentSlice } from "./types";

export const initialAgentSlice: AgentSlice = {
  activeAgents: {},
  completedAgents: [],
};

export function setAgentStart(
  state: AgentSlice,
  agentId: string,
  agentName: string,
  task: string,
): AgentSlice {
  const info: AgentInfo = {
    agentId,
    agentName,
    status: "running",
    task,
    startTime: Date.now(),
  };
  return {
    ...state,
    activeAgents: { ...state.activeAgents, [agentId]: info },
  };
}

export function setAgentComplete(
  state: AgentSlice,
  agentId: string,
  summary: string,
): AgentSlice {
  const existing = state.activeAgents[agentId];
  if (!existing) return state;

  const completed: AgentInfo = { ...existing, status: "completed", summary };
  const { [agentId]: _, ...remainingActive } = state.activeAgents;
  return {
    activeAgents: remainingActive,
    completedAgents: [...state.completedAgents, completed],
  };
}

export function setAgentError(
  state: AgentSlice,
  agentId: string,
  error: string,
): AgentSlice {
  const existing = state.activeAgents[agentId];
  if (!existing) return state;

  const failed: AgentInfo = { ...existing, status: "error", summary: error };
  const { [agentId]: _, ...remainingActive } = state.activeAgents;
  return {
    activeAgents: remainingActive,
    completedAgents: [...state.completedAgents, failed],
  };
}
