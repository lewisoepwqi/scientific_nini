/**
 * 聊天输入区 —— 从 ChatPanel 提取，独立管理输入状态，
 * 避免每次击键触发整个消息列表重渲染。
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useStore, type Message, type SkillItem } from "../store";
import { useConfirm } from "../store/confirm-store";
import { useOnboardStore } from "../store/onboard-store";
import FileUpload from "./FileUpload";
import ModelSelector from "./ModelSelector";
import { Send, Square, Archive } from "lucide-react";

/** 上下文安全等级进度条颜色 */
const CONTEXT_SAFE_COLOR = 'rgba(16, 185, 129, 0.28)'
const CONTEXT_WARNING_COLOR = 'rgba(249, 115, 22, 0.26)'
const CONTEXT_DANGER_COLOR = 'rgba(239, 68, 68, 0.26)'

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

interface ContextSizeData {
  total_context_tokens?: number;
  compress_threshold_tokens?: number;
  compress_target_tokens?: number;
}

interface SlashContext {
  start: number;
  end: number;
  query: string;
}

function resolveSlashContext(text: string, caretPos: number): SlashContext | null {
  const caret = Math.max(0, Math.min(caretPos, text.length));
  const beforeCaret = text.slice(0, caret);
  const slashIndex = beforeCaret.lastIndexOf("/");
  if (slashIndex < 0) return null;

  const prevChar = slashIndex > 0 ? beforeCaret[slashIndex - 1] : "";
  if (prevChar && !/\s/u.test(prevChar)) return null;

  const cmd = beforeCaret.slice(slashIndex + 1);
  if (/\s/u.test(cmd)) return null;
  if (cmd.includes("/")) return null;

  return {
    start: slashIndex,
    end: caret,
    query: cmd.toLowerCase(),
  };
}

function hasFunctionConflict(skill: SkillItem): boolean {
  if (!skill.metadata || typeof skill.metadata !== "object") return false;
  return (skill.metadata as Record<string, unknown>).conflict_with === "function";
}

function isUserInvocable(skill: SkillItem): boolean {
  if (!skill.metadata || typeof skill.metadata !== "object") return true;
  const value = (skill.metadata as Record<string, unknown>).user_invocable;
  return value !== false;
}

function normalizeSkillToken(value: string): string {
  return value.toLowerCase().replace(/[\s_-]+/gu, "");
}

function toStringArray(value: unknown): string[] {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  if (!Array.isArray(value)) return [];
  const items: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const trimmed = item.trim();
    if (trimmed) items.push(trimmed);
  }
  return items;
}

function getSkillAliases(skill: SkillItem): string[] {
  if (!skill.metadata || typeof skill.metadata !== "object") return [];
  const metadata = skill.metadata as Record<string, unknown>;
  return toStringArray(metadata.aliases ?? metadata.alias ?? metadata.triggers);
}

function scoreSkillForQuery(skill: SkillItem, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const normalizedQuery = normalizeSkillToken(q);
  if (!normalizedQuery) return 0;
  const name = skill.name.toLowerCase();
  const normalizedName = normalizeSkillToken(name);
  if (name === q) return 500;
  if (normalizedName === normalizedQuery) return 480;
  if (name.startsWith(q)) return 300;

  const aliases = getSkillAliases(skill).map((a) => a.toLowerCase());
  if (aliases.some((a) => a === q)) return 450;
  if (aliases.some((a) => normalizeSkillToken(a) === normalizedQuery)) return 430;
  if (aliases.some((a) => a.startsWith(q))) return 280;
  if (aliases.some((a) => a.includes(q))) return 220;

  if (name.includes(q)) return 200;
  if (normalizedName.includes(normalizedQuery)) return 180;
  if (skill.description.toLowerCase().includes(q)) return 120;
  if ((skill.category || "").toLowerCase().includes(q)) return 80;
  return -1;
}

function computeRemainingRatio(
  totalTokens: number,
  thresholdTokens: number,
  targetTokens: number,
): number {
  if (thresholdTokens <= 0) return 1;
  if (thresholdTokens <= targetTokens) {
    return clamp01((thresholdTokens - totalTokens) / thresholdTokens);
  }
  if (totalTokens <= targetTokens) return 1;
  const windowSize = thresholdTokens - targetTokens;
  return clamp01(1 - (totalTokens - targetTokens) / windowSize);
}

export default function ChatInputArea() {
  const confirm = useConfirm();
  const sessionId = useStore((s) => s.sessionId);
  const messageCount = useStore((s) => s.messages.length);
  const contextCompressionTick = useStore((s) => s.contextCompressionTick);
  const isStreaming = useStore((s) => s.isStreaming);
  const pendingAskUserQuestion = useStore((s) => s.pendingAskUserQuestion);
  const sendMessage = useStore((s) => s.sendMessage);
  const composerDraft = useStore((s) => s.composerDraft);
  const setComposerDraft = useStore((s) => s.setComposerDraft);
  const stopStreaming = useStore((s) => s.stopStreaming);
  const uploadFile = useStore((s) => s.uploadFile);
  const compressCurrentSession = useStore((s) => s.compressCurrentSession);
  const isUploading = useStore((s) => s.isUploading);
  const skills = useStore((s) => s.skills);
  const fetchSkills = useStore((s) => s.fetchSkills);
  const modelFallback = useStore((s) => s.modelFallback);
  const recipes = useStore((s) => s.recipes);
  const slashHintSeen = useOnboardStore((s) => s.isSeen("slash_commands"));

  const [input, setInput] = useState("");
  const [isDragActive, setIsDragActive] = useState(false);
  const [isCompressing, setIsCompressing] = useState(false);
  const [contextRemainingRatio, setContextRemainingRatio] = useState(1);
  const [contextTokens, setContextTokens] = useState<number | null>(null);
  const [slashContext, setSlashContext] = useState<SlashContext | null>(null);
  const [slashActiveIndex, setSlashActiveIndex] = useState(0);
  const [dismissedRecipeId, setDismissedRecipeId] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dragDepthRef = useRef(0);

  const availableSlashSkills = skills.filter(
    (s) =>
      s.type === "markdown" &&
      s.enabled &&
      !hasFunctionConflict(s) &&
      isUserInvocable(s),
  );
  const filteredSlashSkills = slashContext
    ? availableSlashSkills
        .filter((s) => scoreSkillForQuery(s, slashContext.query) >= 0)
        .sort((a, b) => {
          const scoreDiff =
            scoreSkillForQuery(b, slashContext.query) -
            scoreSkillForQuery(a, slashContext.query);
          if (scoreDiff !== 0) return scoreDiff;
          return a.name.localeCompare(b.name);
        })
    : [];
  const slashMenuOpen = slashContext !== null;

  useEffect(() => {
    if (skills.length > 0) return;
    void fetchSkills();
  }, [skills.length, fetchSkills]);

  useEffect(() => {
    if (!slashMenuOpen) return;
    // 每次打开 slash 面板都刷新一次技能，避免页面常驻导致列表过期。
    void fetchSkills();
  }, [slashMenuOpen, fetchSkills]);

  useEffect(() => {
    setSlashActiveIndex(0);
  }, [slashContext?.query]);

  useEffect(() => {
    if (filteredSlashSkills.length === 0) {
      setSlashActiveIndex(0);
      return;
    }
    if (slashActiveIndex >= filteredSlashSkills.length) {
      setSlashActiveIndex(filteredSlashSkills.length - 1);
    }
  }, [filteredSlashSkills.length, slashActiveIndex]);

  const syncSlashContext = useCallback((value: string, caretPos: number) => {
    setSlashContext(resolveSlashContext(value, caretPos));
  }, []);

  const refreshContextBudget = useCallback(async () => {
    if (!sessionId) {
      setContextRemainingRatio(1);
      setContextTokens(null);
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${sessionId}/context-size`);
      const payload = await resp.json();
      if (!payload.success) return;
      const data = (payload.data || {}) as ContextSizeData;
      const totalTokens =
        typeof data.total_context_tokens === "number"
          ? data.total_context_tokens
          : 0;
      const thresholdTokens =
        typeof data.compress_threshold_tokens === "number"
          ? data.compress_threshold_tokens
          : 30000;
      const targetTokens =
        typeof data.compress_target_tokens === "number"
          ? data.compress_target_tokens
          : 15000;
      setContextTokens(totalTokens);
      setContextRemainingRatio(
        computeRemainingRatio(totalTokens, thresholdTokens, targetTokens),
      );
    } catch {
      // 忽略网络异常
    }
  }, [sessionId]);

  // 会话上下文空间估计
  useEffect(() => {
    void refreshContextBudget();
  }, [refreshContextBudget, messageCount]);

  // 切换会话后重置进度条
  useEffect(() => {
    setContextRemainingRatio(1);
    setContextTokens(null);
  }, [sessionId]);

  // 压缩后刷新
  useEffect(() => {
    if (contextCompressionTick <= 0) return;
    setContextRemainingRatio(1);
    void refreshContextBudget();
  }, [contextCompressionTick, refreshContextBudget]);

  // 输入框自适应高度
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [input, adjustHeight]);

  useEffect(() => {
    if (composerDraft === input) return;
    setInput(composerDraft);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      const caret = composerDraft.length;
      el.setSelectionRange(caret, caret);
      adjustHeight();
      syncSlashContext(composerDraft, caret);
    });
  }, [composerDraft, input, adjustHeight, syncSlashContext]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming || pendingAskUserQuestion) return;
    sendMessage(text);
    setInput("");
    setComposerDraft("");
    setSlashContext(null);
    setSlashActiveIndex(0);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, isStreaming, pendingAskUserQuestion, sendMessage, setComposerDraft]);

  const suggestedRecipe =
    input.trim().length === 0
      ? null
      : recipes.find((recipe) =>
          recipe.recommended_triggers.some((trigger) => {
            const token = trigger.trim().toLowerCase();
            return token !== "" && input.trim().toLowerCase().includes(token);
          }),
        ) ?? null;

  useEffect(() => {
    if (!suggestedRecipe) {
      setDismissedRecipeId(null);
      return;
    }
    if (dismissedRecipeId && dismissedRecipeId !== suggestedRecipe.recipe_id) {
      setDismissedRecipeId(null);
    }
  }, [dismissedRecipeId, suggestedRecipe]);

  const applySlashSkill = useCallback(
    (skill: SkillItem) => {
      if (!slashContext) return;
      const before = input.slice(0, slashContext.start);
      const after = input.slice(slashContext.end);
      const inserted = `/${skill.name} `;
      const nextInput = `${before}${inserted}${after}`;
      const caret = before.length + inserted.length;
      setInput(nextInput);
      setComposerDraft(nextInput);
      setSlashContext(null);
      setSlashActiveIndex(0);

      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(caret, caret);
        adjustHeight();
      });
    },
    [input, slashContext, adjustHeight, setComposerDraft],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (slashMenuOpen) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          if (filteredSlashSkills.length === 0) return;
          setSlashActiveIndex((idx) =>
            idx >= filteredSlashSkills.length - 1 ? 0 : idx + 1,
          );
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          if (filteredSlashSkills.length === 0) return;
          setSlashActiveIndex((idx) =>
            idx <= 0 ? filteredSlashSkills.length - 1 : idx - 1,
          );
          return;
        }
        if ((e.key === "Enter" || e.key === "Tab") && !e.shiftKey) {
          if (filteredSlashSkills.length > 0) {
            e.preventDefault();
            const target = filteredSlashSkills[slashActiveIndex] || filteredSlashSkills[0];
            if (target) applySlashSkill(target);
            return;
          }
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setSlashContext(null);
          setSlashActiveIndex(0);
          return;
        }
      }

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [slashMenuOpen, filteredSlashSkills, slashActiveIndex, applySlashSkill, handleSend],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const nextValue = e.target.value;
      setInput(nextValue);
      setComposerDraft(nextValue);
      syncSlashContext(nextValue, e.target.selectionStart ?? nextValue.length);
      // 首次输入 / 时标记斜杠命令引导为已看
      if (!slashHintSeen && nextValue.includes("/")) {
        useOnboardStore.getState().markSeen("slash_commands");
      }
    },
    [setComposerDraft, syncSlashContext, slashHintSeen],
  );

  const handleCaretUpdate = useCallback(
    (e: React.SyntheticEvent<HTMLTextAreaElement>) => {
      const el = e.currentTarget;
      syncSlashContext(el.value, el.selectionStart ?? el.value.length);
    },
    [syncSlashContext],
  );

  const handleInputFocus = useCallback(() => {
    setIsFocused(true);
    if (skills.length === 0) {
      void fetchSkills();
    }
    const el = textareaRef.current;
    if (!el) return;
    syncSlashContext(el.value, el.selectionStart ?? el.value.length);
  }, [skills.length, fetchSkills, syncSlashContext]);

  const handleInputBlur = useCallback(() => {
    setIsFocused(false);
    setSlashContext(null);
    setSlashActiveIndex(0);
  }, []);

  const handleStop = useCallback(() => {
    if (!isStreaming) return;
    stopStreaming();
  }, [isStreaming, stopStreaming]);

  const handleCompress = useCallback(async () => {
    if (isStreaming || isCompressing) return;
    const confirmed = await confirm({
      title: "压缩会话",
      message: "将压缩当前会话的早期消息并归档，是否继续？",
      confirmText: "压缩",
    });
    if (!confirmed) return;
    setIsCompressing(true);
    const result = await compressCurrentSession();
    setIsCompressing(false);
    if (result.success) {
      setContextRemainingRatio(1);
      void refreshContextBudget();
    }
    const feedback: Message = {
      id: `compress-${Date.now()}`,
      role: "assistant",
      content: result.success ? result.message : `错误: ${result.message}`,
      timestamp: Date.now(),
    };
    useStore.setState((s) => ({ messages: [...s.messages, feedback] }));
  }, [
    isStreaming,
    isCompressing,
    compressCurrentSession,
    refreshContextBudget,
  ]);

  const uploadFilesSequentially = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        await uploadFile(file);
      }
    },
    [uploadFile],
  );

  const isFileDragEvent = useCallback((e: React.DragEvent) => {
    return Array.from(e.dataTransfer.types || []).includes("Files");
  }, []);

  const handleComposerDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return;
      e.preventDefault();
      if (isUploading) return;
      dragDepthRef.current += 1;
      setIsDragActive(true);
    },
    [isFileDragEvent, isUploading],
  );

  const handleComposerDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return;
      e.preventDefault();
      if (isUploading) return;
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) {
        setIsDragActive(false);
      }
    },
    [isFileDragEvent, isUploading],
  );

  const handleComposerDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return;
      e.preventDefault();
      if (isUploading) return;
      if (!isDragActive) setIsDragActive(true);
    },
    [isDragActive, isFileDragEvent, isUploading],
  );

  const handleComposerDrop = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return;
      e.preventDefault();
      if (isUploading) return;
      dragDepthRef.current = 0;
      setIsDragActive(false);
      const files = Array.from(e.dataTransfer.files || []);
      if (files.length > 0) {
        void uploadFilesSequentially(files);
      }
    },
    [isFileDragEvent, isUploading, uploadFilesSequentially],
  );

  const compressLevel =
    contextRemainingRatio > 0.66
      ? "safe"
      : contextRemainingRatio > 0.33
        ? "warning"
        : "critical";
  const compressProgressColor =
    compressLevel === "safe"
      ? CONTEXT_SAFE_COLOR
      : compressLevel === "warning"
        ? CONTEXT_WARNING_COLOR
        : CONTEXT_DANGER_COLOR;
  const compressTextColor =
    compressLevel === "safe"
      ? "text-emerald-700"
      : compressLevel === "warning"
        ? "text-orange-700"
        : "text-red-700";
  const contextUsageRatio = clamp01(1 - contextRemainingRatio);
  const usagePercent = Math.round(contextUsageRatio * 100);

  return (
    <div className="border-t bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
      <div className="max-w-3xl mx-auto">
        {suggestedRecipe && dismissedRecipeId !== suggestedRecipe.recipe_id && (
          <div className="mb-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                命中推荐模板：
                <span className="ml-1 font-semibold">{suggestedRecipe.name}</span>
                <div className="mt-1 text-xs text-emerald-700">{suggestedRecipe.summary}</div>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const text = input.trim();
                    if (!text) return;
                    sendMessage(text, {
                      recipeId: suggestedRecipe.recipe_id,
                      recipeInputs: {},
                    });
                    setInput("");
                    setComposerDraft("");
                    setDismissedRecipeId(null);
                  }}
                  className="rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700"
                >
                  按模板执行
                </button>
                <button
                  type="button"
                  onClick={() => setDismissedRecipeId(suggestedRecipe.recipe_id)}
                  className="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 dark:bg-slate-800 dark:text-emerald-400"
                >
                  继续自由对话
                </button>
              </div>
            </div>
          </div>
        )}
        <div
          className="relative rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-600 dark:bg-slate-800"
          onDragEnter={handleComposerDragEnter}
          onDragLeave={handleComposerDragLeave}
          onDragOver={handleComposerDragOver}
          onDrop={handleComposerDrop}
        >
          {/* 斜杠命令首次发现提示 */}
          {!slashHintSeen && isFocused && input.trim() === "" && (
            <div className="pointer-events-none absolute left-0 right-0 top-0 flex items-center px-4 py-2.5">
              <span className="animate-in fade-in duration-500 text-sm text-slate-400 dark:text-slate-500">
                输入 <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-xs text-slate-600 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-400">/</kbd> 快速调用分析技能
              </span>
            </div>
          )}
          <textarea
            id="chat-input"
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onKeyUp={handleCaretUpdate}
            onClick={handleCaretUpdate}
            onSelect={handleCaretUpdate}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            placeholder="描述你的分析需求..."
            aria-label="输入消息"
            rows={1}
            className="w-full resize-none border-0 bg-transparent px-1 py-1.5 text-sm
                       focus:outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"
            style={{ minHeight: "42px" }}
          />

          {slashMenuOpen && (
            <div className="absolute left-3 right-3 bottom-[calc(100%+18px)] z-20 rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-600 dark:bg-slate-800">
              <div className="max-h-56 overflow-y-auto p-1.5">
                {filteredSlashSkills.length === 0 ? (
                  <div className="px-2.5 py-2 text-xs text-slate-400 dark:text-slate-500">
                    未找到匹配技能
                  </div>
                ) : (
                  filteredSlashSkills.map((skill, idx) => (
                    <button
                      key={skill.name}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => applySlashSkill(skill)}
                      className={`w-full rounded-lg px-2.5 py-2 text-left transition-colors ${
                        idx === slashActiveIndex ? "bg-blue-50 dark:bg-blue-900/20" : "hover:bg-slate-50 dark:hover:bg-slate-700"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-blue-700 dark:text-blue-400">/{skill.name}</span>
                        {skill.category && (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-700 dark:text-slate-400">
                            {skill.category}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-600 dark:text-slate-400">{skill.description}</div>
                      {getSkillAliases(skill).length > 0 && (
                        <div className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">
                          别名：{getSkillAliases(skill).slice(0, 3).join(" / ")}
                        </div>
                      )}
                    </button>
                  ))
                )}
              </div>
              <div className="border-t px-2.5 py-1.5 text-[10px] text-slate-400 dark:border-slate-700">
                ↑↓ 选择，Enter/Tab 插入，Esc 关闭
              </div>
            </div>
          )}

          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <FileUpload />
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <ModelSelector
                compact
                onOpenSettings={() => window.dispatchEvent(new Event("nini:open-settings"))}
              />
              <button
                onClick={() => void handleCompress()}
                disabled={isStreaming || isCompressing || messageCount < 4}
                className={`relative h-8 px-2.5 rounded-2xl border text-xs inline-flex items-center gap-1.5
                           overflow-hidden transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                             compressTextColor
                           } ${
                             compressLevel === "safe"
                               ? "border-emerald-200 hover:bg-emerald-50/60 dark:border-emerald-800 dark:hover:bg-emerald-900/20"
                               : compressLevel === "warning"
                                 ? "border-orange-200 hover:bg-orange-50/60 dark:border-orange-800 dark:hover:bg-orange-900/20"
                                 : "border-red-200 hover:bg-red-50/60 dark:border-red-800 dark:hover:bg-red-900/20"
                           }`}
                title={
                  contextTokens === null
                    ? "压缩会话"
                    : `压缩会话（占用 ${usagePercent}% · 当前 ${contextTokens.toLocaleString()} tok）`
                }
              >
                <span
                  className="absolute left-0 top-0 h-full rounded-2xl transition-all duration-300 ease-out"
                  style={{
                    width: `${usagePercent}%`,
                    backgroundColor: compressProgressColor,
                  }}
                />
                <span className="relative z-10 inline-flex items-center gap-1.5">
                  <Archive size={12} />
                  <span>{isCompressing ? "压缩中" : "压缩"}</span>
                  <span className="text-[10px] tabular-nums">
                    {usagePercent}%
                  </span>
                </span>
              </button>
              {isStreaming ? (
                <button
                  onClick={handleStop}
                  className="flex-shrink-0 w-10 h-10 rounded-2xl bg-red-500 text-white
                             flex items-center justify-center hover:bg-red-600 transition-colors"
                  title="停止生成"
                  aria-label="停止生成"
                >
                  <Square size={14} />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || Boolean(pendingAskUserQuestion)}
                  className="flex-shrink-0 w-10 h-10 rounded-2xl bg-blue-600 text-white
                             flex items-center justify-center
                             hover:bg-blue-700 disabled:bg-slate-300 dark:disabled:bg-slate-600 disabled:cursor-not-allowed
                             transition-colors"
                  aria-label="发送消息"
                >
                  <Send size={16} />
                </button>
              )}
            </div>
          </div>

          {isDragActive && (
            <div className="pointer-events-none absolute inset-0 rounded-2xl border-2 border-blue-500 bg-blue-50/80 flex items-center justify-center text-sm font-medium text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
              释放以上传文件（支持多文件）
            </div>
          )}
        </div>

        {modelFallback ? (
          <div className="mt-1 px-1 text-[11px] text-amber-600 dark:text-amber-400">
            当前已自动降级到 `{modelFallback.to_model}`
            {modelFallback.reason ? `（原因：${modelFallback.reason}）` : ""}
          </div>
        ) : null}

        <div className="mt-1 px-1 text-[11px] text-slate-400 dark:text-slate-500">
          Enter 发送，Shift + Enter 换行，可直接拖拽文件到输入框
          {!slashHintSeen && (
            <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-blue-50 px-1.5 py-0.5 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400">
              <kbd className="font-mono text-[10px]">/</kbd>
              <span>快速调用分析技能</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
