/**
 * 聊天输入区 —— 从 ChatPanel 提取，独立管理输入状态，
 * 避免每次击键触发整个消息列表重渲染。
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useStore, type Message } from "../store";
import FileUpload from "./FileUpload";
import ModelSelector from "./ModelSelector";
import { Send, Square, Archive } from "lucide-react";

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

interface ContextSizeData {
  total_context_tokens?: number;
  compress_threshold_tokens?: number;
  compress_target_tokens?: number;
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
  const sessionId = useStore((s) => s.sessionId);
  const messageCount = useStore((s) => s.messages.length);
  const contextCompressionTick = useStore((s) => s.contextCompressionTick);
  const isStreaming = useStore((s) => s.isStreaming);
  const sendMessage = useStore((s) => s.sendMessage);
  const stopStreaming = useStore((s) => s.stopStreaming);
  const uploadFile = useStore((s) => s.uploadFile);
  const compressCurrentSession = useStore((s) => s.compressCurrentSession);
  const isUploading = useStore((s) => s.isUploading);

  const [input, setInput] = useState("");
  const [isDragActive, setIsDragActive] = useState(false);
  const [isCompressing, setIsCompressing] = useState(false);
  const [contextRemainingRatio, setContextRemainingRatio] = useState(1);
  const [contextTokens, setContextTokens] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dragDepthRef = useRef(0);

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

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;
    sendMessage(text);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, isStreaming, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleStop = useCallback(() => {
    if (!isStreaming) return;
    stopStreaming();
  }, [isStreaming, stopStreaming]);

  const handleCompress = useCallback(async () => {
    if (isStreaming || isCompressing) return;
    const confirmed = window.confirm(
      "将压缩当前会话的早期消息并归档，是否继续？",
    );
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
      ? "rgba(16, 185, 129, 0.28)"
      : compressLevel === "warning"
        ? "rgba(249, 115, 22, 0.26)"
        : "rgba(239, 68, 68, 0.26)";
  const compressTextColor =
    compressLevel === "safe"
      ? "text-emerald-700"
      : compressLevel === "warning"
        ? "text-orange-700"
        : "text-red-700";
  const contextUsageRatio = clamp01(1 - contextRemainingRatio);
  const usagePercent = Math.round(contextUsageRatio * 100);

  return (
    <div className="border-t bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto">
        <div
          className="relative rounded-2xl border border-gray-200 bg-white px-3 py-2 shadow-sm"
          onDragEnter={handleComposerDragEnter}
          onDragLeave={handleComposerDragLeave}
          onDragOver={handleComposerDragOver}
          onDrop={handleComposerDrop}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="描述你的分析需求..."
            rows={1}
            className="w-full resize-none border-0 bg-transparent px-1 py-1.5 text-sm
                       focus:outline-none placeholder:text-gray-400"
            style={{ minHeight: "42px" }}
          />

          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <FileUpload />
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <ModelSelector compact menuDirection="up" align="right" />
              <button
                onClick={() => void handleCompress()}
                disabled={isStreaming || isCompressing || messageCount < 4}
                className={`relative h-8 px-2.5 rounded-2xl border text-xs inline-flex items-center gap-1.5
                           overflow-hidden transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                             compressTextColor
                           } ${
                             compressLevel === "safe"
                               ? "border-emerald-200 hover:bg-emerald-50/60"
                               : compressLevel === "warning"
                                 ? "border-orange-200 hover:bg-orange-50/60"
                                 : "border-red-200 hover:bg-red-50/60"
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
                >
                  <Square size={14} />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!input.trim()}
                  className="flex-shrink-0 w-10 h-10 rounded-2xl bg-blue-600 text-white
                             flex items-center justify-center
                             hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed
                             transition-colors"
                >
                  <Send size={16} />
                </button>
              )}
            </div>
          </div>

          {isDragActive && (
            <div className="pointer-events-none absolute inset-0 rounded-2xl border-2 border-blue-500 bg-blue-50/80 flex items-center justify-center text-sm font-medium text-blue-600">
              释放以上传文件（支持多文件）
            </div>
          )}
        </div>

        <div className="mt-1 px-1 text-[11px] text-gray-400">
          Enter 发送，Shift + Enter 换行，可直接拖拽文件到输入框
        </div>
      </div>
    </div>
  );
}
