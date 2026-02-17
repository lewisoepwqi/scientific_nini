/**
 * 消息气泡组件 —— 渲染用户和 AI 消息，支持工具消息折叠和产物下载。
 */
import React, { Suspense, lazy, useEffect, useState } from "react";
import { type Message } from "../store";
import {
  Bot,
  User,
  Wrench,
  ChevronDown,
  ChevronRight,
  Play,
  CheckCircle2,
  XCircle,
  RotateCcw,
} from "lucide-react";
import DataViewer from "./DataViewer";
import ArtifactDownload from "./ArtifactDownload";
import AnalysisPlanCard from "./AnalysisPlanCard";
import MarkdownContent from "./MarkdownContent";
import { isAnalysisPlanHeaderV2Enabled } from "../featureFlags";

interface Props {
  message: Message;
  showRetry?: boolean;
  onRetry?: () => void;
  retryDisabled?: boolean;
}

const ChartViewer = lazy(() => import("./ChartViewer"));

function MessageBubble({
  message,
  showRetry = false,
  onRetry,
  retryDisabled = false,
}: Props) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const isReasoning = !!message.isReasoning;
  const planHeaderEnabled = isAnalysisPlanHeaderV2Enabled();
  const hasEmbeddedPlotly =
    typeof message.content === "string" &&
    message.content.includes(".plotly.json");
  const [toolExpanded, setToolExpanded] = useState(
    message.toolStatus === "error",
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

  // 分析思路消息使用专用卡片
  if (isReasoning) {
    if (planHeaderEnabled && message.analysisPlan) {
      return null;
    }
    return (
      <AnalysisPlanCard
        content={message.content}
        analysisPlan={message.analysisPlan}
      />
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
                <MarkdownContent content={message.content} />
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

        {isUser && showRetry && (
          <button
            onClick={onRetry}
            disabled={retryDisabled}
            title="重试上一轮"
            className="w-7 h-7 rounded-full border border-gray-200 text-gray-500
                       flex items-center justify-center
                       hover:bg-gray-50 hover:text-gray-700
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors mb-0.5"
          >
            <RotateCcw size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

export default React.memo(MessageBubble);
