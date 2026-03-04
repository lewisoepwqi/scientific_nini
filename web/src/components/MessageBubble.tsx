/**
 * 消息气泡组件 —— 渲染用户和 AI 消息，支持工具消息折叠和产物下载。
 */
import React, { Suspense, lazy, useEffect, useState } from "react";
import { type Message, type RetrievalItem } from "../store";
import {
  Bot,
  User,
  Wrench,
  Lightbulb,
  ChevronDown,
  ChevronRight,
  Play,
  CheckCircle2,
  XCircle,
  RotateCcw,
} from "lucide-react";
import DataViewer from "./DataViewer";
import ArtifactDownload from "./ArtifactDownload";
import MarkdownContent from "./MarkdownContent";
import ReasoningPanel from "./ReasoningPanel";
import CitationMarker from "./CitationMarker";
import CitationList from "./CitationList";

interface Props {
  message: Message;
  showRetry?: boolean;
  onRetry?: () => void;
  retryDisabled?: boolean;
}

const ChartViewer = lazy(() => import("./ChartViewer"));

// 解析引用标记 [1], [2] 等
function parseCitations(content: string): { text: string; citations: Array<{ index: number; text: string }> } {
  const citations: Array<{ index: number; text: string }> = [];
  let text = content;

  // 查找所有引用标记
  const citationRegex = /\[(\d+)\]/g;
  let match;
  while ((match = citationRegex.exec(content)) !== null) {
    const index = parseInt(match[1], 10);
    if (!citations.find((c) => c.index === index)) {
      citations.push({ index, text: `[${index}]` });
    }
  }

  return { text, citations };
}

// 解析结构化推理数据（如果消息包含）
function parseReasoningData(content: string): {
  step?: string;
  thought: string;
  rationale?: string;
  alternatives?: string[];
  confidence?: number;
  reasoning_type?: "analysis" | "decision" | "planning" | "reflection";
  key_decisions?: string[];
  tags?: string[];
} | null {
  // 尝试解析 JSON 格式的推理数据
  try {
    const data = JSON.parse(content);
    if (data.step || data.thought || data.reasoning_type) {
      return {
        step: data.step,
        thought: data.thought || content,
        rationale: data.rationale,
        alternatives: data.alternatives,
        confidence: data.confidence,
        reasoning_type: data.reasoning_type,
        key_decisions: data.key_decisions,
        tags: data.tags,
      };
    }
  } catch {
    // 不是 JSON 格式，返回 null
  }
  return null;
}

function MessageBubble({
  message,
  showRetry = false,
  onRetry,
  retryDisabled = false,
}: Props) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const isReasoning = !!message.isReasoning;
  const hasEmbeddedPlotly =
    typeof message.content === "string" &&
    message.content.includes(".plotly.json");
  const [toolExpanded, setToolExpanded] = useState(
    message.toolStatus === "error",
  );
  const [reasoningDisplay, setReasoningDisplay] = useState(
    isReasoning && message.reasoningLive ? "" : message.content,
  );
  const [reasoningExpanded, setReasoningExpanded] = useState(
    isReasoning ? false : true,
  );
  const hasWideContent =
    !!message.chartData ||
    (!!message.images && message.images.length > 0) ||
    hasEmbeddedPlotly;
  const thinkingLabelClass = message.reasoningLive
    ? "nini-thinking-shimmer"
    : "";

  useEffect(() => {
    if (message.toolStatus === "error") {
      setToolExpanded(true);
    }
  }, [message.toolStatus]);

  useEffect(() => {
    if (!isReasoning) return;
    setReasoningExpanded(false);
  }, [isReasoning, message.id]);

  // 统一处理 reasoning 显示状态和动画
  useEffect(() => {
    if (!isReasoning) return;

    // 流式阶段：使用逐字动画效果
    if (message.reasoningLive) {
      // 如果内容被重置或改变，需要重新同步
      if (!message.content.startsWith(reasoningDisplay)) {
        setReasoningDisplay(message.content);
        return;
      }

      // 逐字动画
      if (reasoningDisplay.length < message.content.length) {
        const remain = message.content.length - reasoningDisplay.length;
        const step = remain > 30 ? 4 : remain > 12 ? 2 : 1;
        const timer = window.setTimeout(() => {
          const nextLen = Math.min(
            message.content.length,
            reasoningDisplay.length + step,
          );
          setReasoningDisplay(message.content.slice(0, nextLen));
        }, 16);
        return () => window.clearTimeout(timer);
      }
    } else {
      // 最终阶段：直接显示完整内容（避免闪烁）
      setReasoningDisplay(message.content);
    }
  }, [isReasoning, message.id, message.content, message.reasoningLive, reasoningDisplay]);

  const showTypingCursor =
    isReasoning &&
    message.reasoningLive &&
    reasoningDisplay.length < message.content.length;

  // 思考过程消息使用独立气泡样式，区别于正式回复
  if (isReasoning) {
    // 结构化分析计划已迁移到工作区「任务」Tab，不在对话区重复展示
    if (message.analysisPlan) {
      return null;
    }

    // 尝试解析结构化推理数据
    const reasoningData = parseReasoningData(message.content);

    // 如果有结构化数据，使用 ReasoningPanel 组件
    if (reasoningData && reasoningData.step) {
      return (
        <div className="flex gap-3 mb-3">
          <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-slate-100 text-slate-600">
            <Lightbulb size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <ReasoningPanel
              data={{
                step: reasoningData.step,
                thought: reasoningData.thought,
                rationale: reasoningData.rationale || "",
                alternatives: reasoningData.alternatives,
                confidence: reasoningData.confidence,
                reasoning_type: reasoningData.reasoning_type,
                key_decisions: reasoningData.key_decisions,
                tags: reasoningData.tags,
              }}
              defaultExpanded={false}
            />
          </div>
        </div>
      );
    }

    // 默认使用极简折叠显示 - 无背景无边框
    return (
      <div className="flex gap-3 mb-3">
        <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-slate-100 text-slate-500">
          <Lightbulb size={14} />
        </div>
        <div className="flex-1 min-w-0">
          {reasoningExpanded ? (
            // 展开状态：显示完整内容和收起按钮
            <div className="max-w-[85%] lg:max-w-2xl">
              <button
                type="button"
                onClick={() => setReasoningExpanded(false)}
                className="flex items-center gap-2 h-7 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
              >
                <span className={`font-medium ${thinkingLabelClass}`}>Thinking</span>
                <ChevronDown size={14} />
              </button>
              {/* 引用块样式容器：左边竖线 + 轻微背景 */}
              <div className="mt-1 pl-3 py-2 border-l-2 border-slate-300 bg-slate-50/60 dark:border-slate-600 dark:bg-slate-800/40 rounded-r">
                <div className="markdown-body reasoning-markdown text-[13px] text-slate-600 dark:text-slate-400">
                  <MarkdownContent content={reasoningDisplay} />
                  {showTypingCursor && (
                    <span
                      className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-slate-500 align-middle"
                      aria-hidden="true"
                    />
                  )}
                </div>
              </div>
            </div>
          ) : (
            // 折叠状态：纯文本按钮，无背景无边框
            <button
              type="button"
              onClick={() => setReasoningExpanded(true)}
              className="flex items-center gap-1.5 h-7 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
            >
              <span className={`font-medium ${thinkingLabelClass}`}>Thinking</span>
              <ChevronRight size={14} />
            </button>
          )}
        </div>
      </div>
    );
  }

  // 工具消息使用卡片式折叠显示
  if (isTool) {
    const hasResult = !!message.toolResult;
    const isError = message.toolStatus === "error";

    // 根据状态确定颜色主题
    const themeColors = isError
      ? {
          icon: "text-red-600",
          bg: "bg-red-50/50",
          border: "border-red-200",
          headerBg: "hover:bg-red-100/50",
          title: "text-red-900",
          resultHeader: "text-red-700",
          resultBg: "bg-red-50/50",
          resultBorder: "border-red-200",
          resultText: "text-red-900",
          statusText: "text-red-600",
          badge: "bg-red-100 text-red-700",
        }
      : {
          icon: "text-amber-600",
          bg: "bg-amber-50/50",
          border: "border-amber-200",
          headerBg: "hover:bg-amber-100/50",
          title: "text-amber-900",
          resultHeader: "text-green-700",
          resultBg: "bg-green-50/50",
          resultBorder: "border-green-200",
          resultText: "text-green-900",
          statusText: "text-green-600",
          badge: "bg-amber-100 text-amber-700",
        };

    return (
      <div className="flex gap-3 mb-3">
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${themeColors.badge}`}
        >
          <Wrench size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <div
            className={`rounded-lg border ${themeColors.border} ${themeColors.bg} overflow-hidden`}
          >
            {/* 标题栏 - 可点击展开/折叠 */}
            <button
              onClick={() => setToolExpanded(!toolExpanded)}
              className={`w-full flex items-center justify-between px-3 py-2 text-sm ${themeColors.headerBg} transition-colors`}
            >
              <div className="flex items-center gap-2">
                {hasResult ? (
                  isError ? (
                    <XCircle size={14} className="text-red-600" />
                  ) : (
                    <CheckCircle2 size={14} className="text-green-600" />
                  )
                ) : (
                  <Play size={14} className={themeColors.icon} />
                )}
                <span className={`font-medium ${themeColors.title}`}>
                  {message.toolName || "工具调用"}
                </span>
                {message.toolIntent && (
                  <span
                    className={`text-xs ${themeColors.title} opacity-80 truncate max-w-[260px]`}
                    title={message.toolIntent}
                  >
                    {message.toolIntent}
                  </span>
                )}
                {hasResult && (
                  <span
                    className={`text-xs ${isError ? "text-red-600" : "text-green-600"}`}
                  >
                    {isError ? "执行失败" : "执行完成"}
                  </span>
                )}
              </div>
              {toolExpanded ? (
                <ChevronDown size={14} className={themeColors.icon} />
              ) : (
                <ChevronRight size={14} className={themeColors.icon} />
              )}
            </button>

            {/* 展开内容 */}
            {toolExpanded && (
              <div className={`px-3 pb-3 border-t ${themeColors.border}/50`}>
                {/* 调用参数 */}
                {message.toolInput && (
                  <div className="mt-2">
                    <div
                      className={`text-xs font-medium ${themeColors.title} mb-1`}
                    >
                      调用参数：
                    </div>
                    <pre
                      className={`text-xs bg-white/70 border ${themeColors.border} rounded px-2 py-1.5 overflow-x-auto ${themeColors.title}`}
                    >
                      <code>{JSON.stringify(message.toolInput, null, 2)}</code>
                    </pre>
                  </div>
                )}

                {/* 执行结果 */}
                {hasResult && (
                  <div className="mt-2">
                    <div
                      className={`text-xs font-medium ${themeColors.resultHeader} mb-1`}
                    >
                      {isError ? "错误信息：" : "执行结果："}
                    </div>
                    <div
                      className={`text-xs ${themeColors.resultBg} border ${themeColors.resultBorder} rounded px-2 py-1.5 ${themeColors.resultText} markdown-body prose prose-sm max-w-none`}
                    >
                      <MarkdownContent content={message.toolResult!} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {message.artifacts && message.artifacts.length > 0 && (
            <ArtifactDownload artifacts={message.artifacts} />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""} mb-4`}>
      {/* 头像 */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? "bg-blue-600 text-white" : "bg-emerald-100 text-emerald-700"
        }`}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* 内容 */}
      {/* 包含图表或图片的消息使用更宽的宽度 */}
      <div
        className={`flex items-end gap-2 min-w-0 ${
          isUser ? "flex-row-reverse" : "flex-1"
        }`}
      >
        <div
          className={`${
            hasWideContent
              ? "w-full max-w-[95%] lg:max-w-4xl xl:max-w-5xl"
              : "max-w-[80%] lg:max-w-2xl"
          } rounded-2xl px-4 py-2.5 ${
            isUser
              ? "bg-blue-600 text-white rounded-tr-md"
              : "bg-gray-100 text-gray-900 rounded-tl-md"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <>
              <div className="markdown-body prose prose-sm max-w-none">
                {message.isError && (
                  <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                    <div className="font-medium">
                      {message.errorHint || "模型调用异常，可重试上一轮。"}
                    </div>
                    {message.errorCode && (
                      <div className="mt-1 text-[11px] text-red-700">
                        错误码：{message.errorCode}
                      </div>
                    )}
                    {message.errorDetail && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-[11px] text-red-700 hover:text-red-800">
                          查看详细错误
                        </summary>
                        <div className="mt-1 whitespace-pre-wrap text-[11px] text-red-700">
                          {message.errorDetail}
                        </div>
                      </details>
                    )}
                  </div>
                )}
                <CitationContent content={message.content} retrievals={message.retrievals} />
              </div>
              {/* 新的引用列表展示 */}
              {message.retrievals && message.retrievals.length > 0 && (
                <CitationList retrievals={message.retrievals} />
              )}
              {message.chartData && (
                <Suspense
                  fallback={
                    <div className="text-xs text-gray-500 mt-2">
                      图表组件加载中...
                    </div>
                  }
                >
                  <ChartViewer chartData={message.chartData} />
                </Suspense>
              )}
              {message.dataPreview && (
                <DataViewer preview={message.dataPreview} />
              )}
              {message.artifacts && message.artifacts.length > 0 && (
                <ArtifactDownload artifacts={message.artifacts} />
              )}
              {/* 图片展示 */}
              {message.images && message.images.length > 0 && (
                <div className="mt-3 space-y-2">
                  {message.images.map((url, idx) => (
                    <div
                      key={idx}
                      className="rounded-lg overflow-hidden border border-gray-200 bg-white"
                    >
                      <img
                        src={url}
                        alt={`图片 ${idx + 1}`}
                        className="w-full h-auto max-h-[600px] object-contain"
                        loading="lazy"
                      />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {showRetry && (isUser || message.isError) && (
          <button
            onClick={onRetry}
            disabled={retryDisabled}
            title={isUser ? "重试上一轮" : "重试本次请求"}
            className={`w-7 h-7 rounded-full border
                       flex items-center justify-center
                       ${
                         message.isError
                           ? "border-red-200 text-red-500 hover:bg-red-50 hover:text-red-700"
                           : "border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-700"
                       }
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors mb-0.5`}
          >
            <RotateCcw size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

// 带引用标记的内容渲染组件
function CitationContent({
  content,
  retrievals,
}: {
  content: string;
  retrievals?: RetrievalItem[];
}) {
  const { citations } = parseCitations(content);

  // 如果没有引用，直接渲染 Markdown
  if (citations.length === 0) {
    return <MarkdownContent content={content} />;
  }

  // 将内容按引用标记分割，插入 CitationMarker 组件
  const parts = content.split(/(\[\d+\])/g);

  return (
    <div>
      <div className="prose-content">
        {parts.map((part, idx) => {
          const match = part.match(/^\[(\d+)\]$/);
          if (match) {
            const citationIndex = parseInt(match[1], 10);
            const retrieval = retrievals?.[citationIndex - 1];
            return (
              <CitationMarker
                key={idx}
                index={citationIndex}
                retrieval={retrieval}
              />
            );
          }
          // 渲染普通文本
          return <MarkdownContent key={idx} content={part} />;
        })}
      </div>
    </div>
  );
}

export default React.memo(MessageBubble, (prevProps, nextProps) => {
  // 自定义比较函数：如果消息内容或关键字段变化，则重新渲染
  const prev = prevProps.message;
  const next = nextProps.message;

  // 基本字段比较
  if (prev.id !== next.id) return false;
  if (prev.content !== next.content) return false;
  if (prev.role !== next.role) return false;

  // 工具消息相关字段
  if (prev.toolName !== next.toolName) return false;
  if (prev.toolResult !== next.toolResult) return false;
  if (prev.toolStatus !== next.toolStatus) return false;
  if (prev.toolIntent !== next.toolIntent) return false;

  // 其他关键字段
  if (prev.isReasoning !== next.isReasoning) return false;
  if (prev.reasoningLive !== next.reasoningLive) return false;
  if (prev.chartData !== next.chartData) return false;
  if (prev.retrievals !== next.retrievals) return false;

  // 重试相关
  if (prevProps.showRetry !== nextProps.showRetry) return false;
  if (prevProps.retryDisabled !== nextProps.retryDisabled) return false;

  // 所有关键字段相同，跳过渲染
  return true;
});
