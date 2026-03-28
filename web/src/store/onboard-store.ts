/**
 * 引导状态管理 —— 跟踪用户已查看的引导提示，持久化到 localStorage。
 * 使用 nini_ 前缀 + try/catch 容错，沿用项目 localStorage 模式。
 */
import { create } from "zustand";

const STORAGE_KEY = "nini_onboard_seen";

/** 所有引导 ID 枚举 */
export type OnboardHintId =
  | "welcome"
  | "slash_commands"
  | "output_level"
  | "toolbar_hints";

function loadSeenIds(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v): v is string => typeof v === "string"));
  } catch {
    // localStorage 不可用则使用默认值
    return new Set();
  }
}

function persistSeenIds(ids: Set<string>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
  } catch {
    // 写入失败静默忽略
  }
}

interface OnboardState {
  seenIds: Set<string>;
  markSeen: (id: OnboardHintId) => void;
  isSeen: (id: OnboardHintId) => boolean;
}

export const useOnboardStore = create<OnboardState>((set, get) => ({
  seenIds: loadSeenIds(),

  markSeen: (id) => {
    const next = new Set(get().seenIds);
    next.add(id);
    persistSeenIds(next);
    set({ seenIds: next });
  },

  isSeen: (id) => get().seenIds.has(id),
}));
