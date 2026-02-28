/**
 * 消息气泡组件 —— 渲染用户和 AI 消息，支持工具消息折叠和产物下载。
 */
import React, { Suspense, lazy, useEffect, useState } from "react";
import { type Message } from "../store";
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
  BookOpen,
} from "lucide-react";
import DataViewer from "./DataViewer";
import ArtifactDownload from "./ArtifactDownload";
import MarkdownContent from "./MarkdownContent";
import ReasoningPanel from "./ReasoningPanel";

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
    isReasoning ? message.reasoningLive || message.content.length <= 160 : true,
  );
  const hasWideContent =
    !!message.chartData ||
    (!!message.images && message.images.length > 0) ||
    hasEmbeddedPlotly;

  useEffect(() => {
    if (message.toolStatus === "error") {
      setToolExpanded(true);
    }
  }, [message.toolStatus]);

  useEffect(() => {
    if (!isReasoning) return;
    setReasoningDisplay(message.reasoningLive ? "" : message.content);
  }, [isReasoning, message.id, message.reasoningLive]);

  useEffect(() => {
    if (!isReasoning) return;
    setReasoningExpanded(message.reasoningLive || message.content.length <= 160);
  }, [isReasoning, message.id, message.reasoningLive, message.content.length]);

  useEffect(() => {
    if (!isReasoning || !message.reasoningLive) return;
    setReasoningExpanded(true);
  }, [isReasoning, message.reasoningLive]);

  useEffect(() => {
    if (!isReasoning) return;
    if (!message.reasoningLive) {
      setReasoningDisplay(message.content);
      return;
    }
    if (!message.content.startsWith(reasoningDisplay)) {
      setReasoningDisplay(message.content);
      return;
    }
    if (reasoningDisplay.length >= message.content.length) {
      return;
    }
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
  }, [isReasoning, message.content, reasoningDisplay, message.reasoningLive]);

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
        <div className="flex gap-3 mb-4">
          <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-amber-100 text-amber-700">
            <Lightbulb size={16} />
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
              defaultExpanded={reasoningExpanded}
            />
          </div>
        </div>
      );
    }

    // 默认使用简单的折叠显示
    return (
      <div className="flex gap-3 mb-4">
        <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-amber-100 text-amber-700">
          <Lightbulb size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="max-w-[85%] lg:max-w-2xl rounded-2xl rounded-tl-md border border-amber-300/90 bg-gradient-to-br from-amber-50 to-orange-50 px-4 py-3 shadow-sm">
            <button
              type="button"
              onClick={() => setReasoningExpanded((prev) => !prev)}
              className="mb-2 flex w-full items-center justify-between text-left text-xs font-semibold tracking-wide text-amber-700 hover:text-amber-800"
            >
              <span className="flex items-center gap-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500" />
                思考过程
              </span>
              <span className="flex items-center gap-1">
                {reasoningExpanded ? "收起" : "展开"}
                {reasoningExpanded ? (
                  <ChevronDown size={14} />
                ) : (
                  <ChevronRight size={14} />
                )}
              </span>
            </button>
            <div className="markdown-body reasoning-markdown prose prose-sm max-w-none text-amber-950">
              {reasoningExpanded ? (
                <>
                  <MarkdownContent content={reasoningDisplay} />
                  {showTypingCursor && (
                    <span
                      className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-amber-700 align-middle"
                      aria-hidden="true"
                    />
                  )}
                </>
              ) : (
                <p className="m-0 text-xs text-amber-700/90">
                  已折叠，点击"展开"查看完整思考过程。
                </p>
              )}
            </div>
          </div>
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
                <CitationContent content={message.content} />
              </div>
              {message.retrievals && message.retrievals.length > 0 && (
                <div className="mt-2 space-y-2">
                  {message.retrievals.map((item, idx) => (
                    <div
                      key={`${item.source}-${idx}`}
                      className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2 text-violet-700">
                        <span className="font-medium truncate">
                          {item.source}
                        </span>
                        <span className="text-[10px] whitespace-nowrap">
                          {typeof item.score === "number"
                            ? `score=${item.score.toFixed(2)}`
                            : ""}
                          {typeof item.hits === "number"
                            ? ` hits=${item.hits}`
                            : ""}
                        </span>
                      </div>
                      <div className="mt-1 text-violet-900 whitespace-pre-wrap">
                        {item.snippet}
                      </div>
                    </div>
                  ))}
                </div>
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
function CitationContent({ content }: { content: string }) {
  const [showCitations, setShowCitations] = useState(false);
  const { citations } = parseCitations(content);

  // 如果没有引用，直接渲染 Markdown
  if (citations.length === 0) {
    return <MarkdownContent content={content} />;
  }

  // 将引用标记转换为可点击的链接
  const processedContent = content.replace(
    /\[(\d+)\]/g,
    (_, index) => {
      return `<sup class="citation-marker" data-index="${index}">[${index}]</sup>`;
    }
  );

  return (
    <div>
      <div
        className="prose-content"
        dangerouslySetInnerHTML={{
          __html: processedContent,
        }}
      />
      <style>{`
        .citation-marker {
          color: #3b82f6;
          cursor: pointer;
          font-weight: 500;
          font-size: 0.75em;
          vertical-align: super;
          margin-left: 1px;
        }
        .citation-marker:hover {
          color: #2563eb;
          text-decoration: underline;
        }
      `}</style>

      {/* 引用列表 */}
      {citations.length > 0 && (
        <button
          onClick={() => setShowCitations(!showCitations)}
          className="mt-2 flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
        >
          <BookOpen size={12} />
          {showCitations ? "隐藏引用" : `查看 ${citations.length} 条引用`}
        </button>
      )}

      {showCitations && (
        <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
          <div className="text-xs text-blue-700 dark:text-blue-300 font-medium mb-1">
            知识引用
          </div>
          <ul className="space-y-1">
            {citations.map((citation) => (
              <li
                key={citation.index}
                className="text-xs text-blue-600 dark:text-blue-400"
              >
                [{citation.index}] 来自知识库
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default React.memo(MessageBubble);
