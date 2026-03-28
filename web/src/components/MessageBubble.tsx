/**
 * 消息气泡组件 —— 渲染用户和 AI 消息，支持工具消息折叠和产物下载。
 */
import React, { Suspense, lazy, useEffect, useState } from "react";
import { type Message, type RetrievalItem, useStore } from "../store";
import { useOnboardStore } from "../store/onboard-store";
import OutputLevelExplainer from "./OutputLevelExplainer";
import {
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
import LazyMarkdownContent from "./LazyMarkdownContent";
import Button from "./ui/Button";

interface Props {
 message: Message;
 showRetry?: boolean;
 onRetry?: () => void;
 retryDisabled?: boolean;
}

const ChartViewer = lazy(() => import("./ChartViewer"));
const PlotlyFromUrl = lazy(() => import("./PlotlyFromUrl"));
const ReasoningPanel = lazy(() => import("./ReasoningPanel"));
const CitationTooltip = lazy(() => import("./chat/CitationTooltip"));
const AgentMessageCard = lazy(() => import("./chat/AgentMessageCard"));
const CitationList = lazy(() => import("./CitationList"));
const WidgetRenderer = lazy(() => import("./WidgetRenderer"));
const TOOL_RESULT_PREVIEW_LIMIT = 72;

/** 工具标识符 → 中文友好名称映射 */
const TOOL_DISPLAY_NAMES: Record<string, string> = {
 // 统计分析
 t_test: "T 检验",
 mann_whitney: "Mann-Whitney U 检验",
 anova: "方差分析 (ANOVA)",
 kruskal_wallis: "Kruskal-Wallis H 检验",
 multiple_comparison_correction: "多重比较校正",
 stat_test: "统计检验",
 correlation: "相关分析",
 regression: "回归分析",
 stat_model: "统计建模",
 stat_interpret: "结果解读",
 sample_size: "样本量计算",
 interpret_statistical_result: "统计结果解读",

 // 可视化
 create_chart: "创建图表",
 export_chart: "导出图表",
 chart_session: "图表会话",
 generate_widget: "内嵌组件",

 // 数据操作
 load_dataset: "加载数据集",
 preview_data: "预览数据",
 data_summary: "数据摘要",
 clean_data: "数据清洗",
 recommend_cleaning_strategy: "清洗策略推荐",
 evaluate_data_quality: "数据质量评估",
 generate_quality_report: "数据质量报告",
 dataset_catalog: "数据集目录",
 dataset_transform: "数据变换",

 // 代码执行
 run_code: "执行 Python 代码",
 run_r_code: "执行 R 代码",
 code_session: "代码会话",

 // 报告与导出
 generate_report: "生成分析报告",
 export_report: "导出报告",
 export_document: "导出文档",
 report_session: "报告会话",
 collect_artifacts: "收集分析素材",

 // 工作区
 organize_workspace: "整理工作区",
 edit_file: "编辑文件",
 workspace_session: "工作区管理",
 list_workspace_files: "工作区文件列表",

 // 网络与多模态
 fetch_url: "获取网页内容",
 image_analysis: "图片分析",
 search_literature: "文献检索",

 // 任务与规划
 task_write: "任务管理",
 task_state: "任务状态",

 // 多 Agent
 dispatch_agents: "派发子 Agent",

 // 复合模板
 complete_comparison: "完整两组比较分析",
 complete_anova: "完整多组比较分析",
 correlation_analysis: "完整相关分析",
 regression_analysis: "完整回归分析",

 // 记忆与画像
 analysis_memory: "分析记忆查询",
 search_memory_archive: "历史记忆搜索",
 update_profile_notes: "更新研究画像",
 query_evidence: "证据链查询",

 // 工具发现
 search_tools: "工具发现",

 // 工作流
 save_workflow: "保存工作流",
 list_workflows: "工作流列表",
 apply_workflow: "应用工作流",

 // 阶段检测
 detect_phase: "研究阶段检测",
};

/** 输出等级含义说明 */
const OUTPUT_LEVEL_DESCRIPTIONS: Record<string, string> = {
 o1: "建议级：仅供参考的初步思路，未经验证",
 o2: "草稿级：初步分析结果，可能需要修正",
 o3: "可审阅级：经过验证的分析结果，建议人工审阅后使用",
 o4: "可导出级：最终成果，可直接用于报告或论文",
};

function getToolDisplayName(toolName?: string | null): string {
 if (!toolName) return "工具调用";
 return TOOL_DISPLAY_NAMES[toolName] || toolName;
}

function getOutputLevelMeta(outputLevel?: "o1" | "o2" | "o3" | "o4" | null) {
 switch (outputLevel) {
 case "o1":
 return { label: "建议级", className: "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)] dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-muted)]" };
 case "o2":
 return { label: "草稿级", className: "border-[var(--domain-profile)] bg-[var(--accent-subtle)] text-[var(--domain-profile)]" };
 case "o3":
 return { label: "可审阅级", className: "border-[var(--success)] bg-[var(--accent-subtle)] text-[var(--success)] dark:text-[var(--success)]" };
 case "o4":
 return { label: "可导出级", className: "border-[var(--domain-analysis)] bg-[var(--accent-subtle)] text-[var(--domain-analysis)]" };
 default:
 return null;
 }
}

function extractPlotlyJsonUrl(chartData: unknown): string | null {
 if (!chartData || typeof chartData !== "object") {
 return null;
 }
 const record = chartData as Record<string, unknown>;
 const rawUrl =
 (typeof record.url === "string" && record.url) ||
 (typeof record.download_url === "string" && record.download_url) ||
 "";
 if (!rawUrl) {
 return null;
 }
 const clean = rawUrl.split("#")[0]?.split("?")[0]?.toLowerCase() || "";
 if (!clean.endsWith(".plotly.json")) {
 return null;
 }
 return rawUrl;
}

function buildToolResultPreview(toolResult?: string): string | null {
 if (typeof toolResult !== "string") {
 return null;
 }

 const compact = toolResult
 .replace(/!\[([^\]]*)\]\([^)]+\)/g, (_, alt: string) => alt || "图片")
 .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
 .replace(/[`#>*_~]+/g, "")
 .replace(/\s+/g, "")
 .trim();

 if (!compact || compact === "工具执行完成" || compact === "工具执行失败") {
 return null;
 }

 if (compact.length <= TOOL_RESULT_PREVIEW_LIMIT) {
 return compact;
 }
 return `${compact.slice(0, TOOL_RESULT_PREVIEW_LIMIT).trimEnd()}...`;
}

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

function renderUserMessage(content: string) {
 if (content.startsWith("你正在以 Recipe 模式执行")) {
 const lines = content.split("\n");
 return (
 <div className="space-y-1">
 {lines.map((line, i) => {
 if (line.startsWith("你正在以 Recipe 模式执行")) {
 return (
 <div key={i} className="text-white dark:text-[var(--accent)] font-medium mb-3">
 {line}
 </div>
 );
 }
 if (line.endsWith("：")) {
 return (
 <div key={i} className="text-white/80 dark:text-[var(--text-muted)] text-xs mt-3 mb-1">
 {line}
 </div>
 );
 }
 if (line.trim() === "") {
 return null;
 }
 return (
 <div key={i} className="text-white dark:text-[var(--text-primary)] leading-relaxed text-[15px]">
 {line}
 </div>
 );
 })}
 </div>
 );
 }
 return <p className="whitespace-pre-wrap text-[15px]">{content}</p>;
}

function MessageBubble({
 message,
 showRetry = false,
 onRetry,
 retryDisabled = false,
}: Props) {
 const completedAgents = useStore((s) => s.completedAgents);
 const isUser = message.role === "user";
 const isTool = message.role === "tool";
 const isReasoning = !!message.isReasoning;
 const hasEmbeddedPlotly =
 typeof message.content === "string" &&
 message.content.includes(".plotly.json");
 const [toolExpanded, setToolExpanded] = useState(
 message.toolStatus === "error" || message.toolName === "generate_widget",
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
 const plotlyUrl = extractPlotlyJsonUrl(message.chartData);
 const outputLevelMeta = getOutputLevelMeta(message.outputLevel);
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
 // 结构化分析计划渲染为 AgentMessageCard 卡片
 if (message.analysisPlan) {
 return (
 <div className="my-2 max-w-[95%] lg:max-w-4xl xl:max-w-5xl">
 <div className="flex gap-3">
 <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-[var(--success)] bg-[var(--success)]/10">
 <Lightbulb size={16} />
 </div>
 <div className="flex-1 min-w-0">
 <AgentMessageCard message={message} />
 </div>
 </div>
 </div>
 );
 }

 // 尝试解析结构化推理数据
 const reasoningData = parseReasoningData(message.content);

 // 如果有结构化数据，使用 ReasoningPanel 组件
 if (reasoningData && reasoningData.step) {
 return (
 <div className="flex gap-3 mb-3">
 <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
 <Lightbulb size={14} />
 </div>
 <div className="flex-1 min-w-0">
 <Suspense
 fallback={
 <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] h-[100px] animate-pulse flex items-center justify-center text-xs text-[var(--text-muted)]">
 正在加载推理面板…
 </div>
 }
 >
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
 </Suspense>
 </div>
 </div>
 );
 }

 // 默认使用极简折叠显示 - 无背景无边框
 return (
 <div className="flex gap-3 mb-3">
 <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-[var(--bg-elevated)] text-[var(--text-muted)]">
 <Lightbulb size={14} />
 </div>
 <div className="flex-1 min-w-0">
 {reasoningExpanded ? (
 // 展开状态：显示完整内容和收起按钮
 <div className="max-w-[85%] lg:max-w-2xl">
 <button
 type="button"
 onClick={() => setReasoningExpanded(false)}
 aria-expanded="true"
 className="flex items-center gap-2 h-7 px-2 text-xs text-[var(--text-secondary)] bg-transparent border-none cursor-pointer focus:outline-none"
 >
 <span className={`font-medium ${thinkingLabelClass}`}>Thinking</span>
 <ChevronDown size={14} />
 </button>
 {/* 引用块样式容器：左边竖线 + 轻微背景 */}
 <div className="mt-1 pl-3 py-2 border-l-2 border-[var(--border-strong)] bg-[var(--bg-elevated)]/60 rounded-r">
 <div className="markdown-body reasoning-markdown text-[13px] text-[var(--text-secondary)]">
 <LazyMarkdownContent content={reasoningDisplay} />
 {showTypingCursor && (
 <span
 className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-[var(--bg-elevated)]0 align-middle"
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
            aria-expanded="false"
            className="flex items-center gap-1.5 h-7 px-2 text-xs text-[var(--text-secondary)] bg-transparent border-none cursor-pointer focus:outline-none"
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
 const widget = message.toolName === "generate_widget" ? message.widget : undefined;
 const resultPreview = buildToolResultPreview(message.toolResult);
 const statusLabel = hasResult
 ? isError
 ? resultPreview
 ? `执行失败：${resultPreview}`
 : "执行失败"
 : resultPreview
 ? `执行完成：${resultPreview}`
 : "执行完成"
 : null;

 // 根据状态确定颜色主题
  const themeColors = isError
    ? {
        icon: "text-[var(--error)]",
        bg: "bg-[var(--error-subtle)]",
        border: "border-[color-mix(in_srgb,var(--error)_30%,transparent)]",
        title: "text-[var(--error)]",
        resultHeader: "text-[var(--error)]",
        resultBg: "bg-[var(--bg-base)]",
        resultBorder: "ring-1 ring-inset ring-[color-mix(in_srgb,var(--error)_20%,transparent)] border-none",
        resultText: "text-[var(--error)]",
        statusText: "text-[var(--error)]",
        badge: "bg-[color-mix(in_srgb,var(--error)_15%,transparent)] text-[var(--error)]",
      }
    : {
        icon: "text-[var(--text-muted)]",
        bg: "bg-[var(--bg-elevated)]",
        border: "border-[var(--border-subtle)]",
        title: "text-[var(--text-secondary)]",
        resultHeader: "text-[var(--text-secondary)]",
        resultBg: "bg-[var(--bg-base)]",
        resultBorder: "ring-1 ring-inset ring-[color-mix(in_srgb,var(--border-subtle)_50%,transparent)] border-none",
        resultText: "text-[var(--text-primary)]",
        statusText: "text-[var(--success)]",
        badge: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
      };

 // dispatch_agents 工具：展示参与执行的子 Agent 来源标签
 const isDispatchAgents = message.toolName === "dispatch_agents";
 const sourceAgents = isDispatchAgents && completedAgents.length > 0
 ? completedAgents
 : [];

 return (
 <div className="flex gap-3 mb-3">
 <div
 className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${themeColors.badge}`}
 >
 <Wrench size={14} />
 </div>
 <div className="flex-1 min-w-0">
 {/* 子 Agent 来源标签（仅 dispatch_agents 工具结果展示） */}
 {sourceAgents.length > 0 && (
 <div className="mb-1 flex flex-wrap gap-1">
 {sourceAgents.map((agent) => (
 <span
 key={agent.agentId}
 className="inline-flex items-center rounded-full bg-[var(--accent-subtle)] px-2 py-0.5 text-[11px] font-medium text-[var(--domain-knowledge)] ring-1 ring-inset ring-indigo-200 dark:ring-indigo-800"
 title={agent.task}
 >
 [{agent.agentName}]
 </span>
 ))}
 </div>
 )}
 <div
 className={`rounded-lg border ${themeColors.border} ${themeColors.bg} overflow-hidden`}
 >
 {/* 标题栏 - 可点击展开/折叠 */}
 <button
 type="button"
 onClick={() => setToolExpanded(!toolExpanded)}
 aria-expanded={toolExpanded}
 className="w-full flex items-center justify-between px-3 py-2 text-sm bg-transparent border-none cursor-pointer focus:outline-none"
 >
 <div className="flex items-center gap-2 min-w-0 flex-1">
 {hasResult ? (
 isError ? (
 <XCircle size={14} className="text-[var(--error)] flex-shrink-0" />
 ) : (
 <CheckCircle2 size={14} className="text-[var(--success)] flex-shrink-0" />
 )
 ) : (
 <Play size={14} className={`${themeColors.icon} flex-shrink-0`} />
 )}
 <span
 className={`inline-flex items-center leading-none font-medium ${themeColors.title} shrink-0`}
 >
 {getToolDisplayName(message.toolName)}
 </span>
 {statusLabel && (
 <span
 className={`min-w-0 flex-1 text-left ${isError ? "text-[var(--error)]" : "text-[var(--success)]"}`}
 title={message.toolResult || statusLabel}
 >
 <span className="block w-full truncate whitespace-nowrap text-left text-xs leading-none">
 {statusLabel}
 </span>
 </span>
 )}
 {message.toolIntent && (
 <span
 className={`inline-flex items-center leading-none text-xs ${themeColors.title} opacity-80 truncate max-w-[260px]`}
 title={message.toolIntent}
 >
 {message.toolIntent}
 </span>
 )}
 </div>
 {toolExpanded ? (
 <ChevronDown size={14} className={`${themeColors.icon} ml-2 flex-shrink-0`} />
 ) : (
 <ChevronRight size={14} className={`${themeColors.icon} ml-2 flex-shrink-0`} />
 )}
 </button>

 {/* 展开内容 */}
            {toolExpanded && (
              <div className={`px-3 pb-3 border-t ${themeColors.border}`}>
 {/* 调用参数 */}
 {message.toolInput && (
 <div className="mt-2">
 <div
 className={`text-xs font-medium ${themeColors.title} mb-1`}
 >
 调用参数：
 </div>
 <pre
 className={`text-xs ${themeColors.resultBg} ${themeColors.resultBorder} rounded-lg px-3 py-2.5 overflow-x-auto ${themeColors.title}`}
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
 className={`text-xs ${themeColors.resultBg} ${themeColors.resultBorder} rounded-lg px-3 py-2.5 ${themeColors.resultText} markdown-body prose prose-sm max-w-none`}
 >
 <LazyMarkdownContent content={message.toolResult!} />
 </div>
 </div>
 )}

 {widget && (
 <Suspense
 fallback={
 <div className="mt-3 rounded-xl border border-cyan-100 bg-[var(--accent-subtle)]/60 px-3 py-2 text-xs text-[var(--accent)]">
 正在加载内嵌组件...
 </div>
 }
 >
 <WidgetRenderer
 title={widget.title}
 html={widget.html}
 description={widget.description}
 />
 </Suspense>
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
 isUser
 ? "bg-[var(--accent)] text-white dark:bg-[var(--bg-elevated)] dark:text-[var(--text-secondary)] dark:border dark:border-[var(--border-default)]"
 : "bg-[var(--accent-subtle)] text-[var(--success)] dark:bg-[var(--accent)] dark:text-white"
 }`}
 >
 {isUser ? <User size={16} /> : <span className="font-bold text-[14px] leading-none">N</span>}
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
 } rounded-2xl px-4 py-3 ${
 isUser
 ? "bg-[var(--accent)] text-white rounded-tr-md dark:bg-[var(--accent-subtle)] dark:text-[var(--text-primary)]"
 : "bg-[var(--bg-elevated)] text-[var(--text-primary)] rounded-tl-md dark:bg-[var(--bg-overlay)] dark:border dark:border-[var(--border-default)] dark:text-[var(--text-primary)]"
 }`}
 >
 {isUser ? (
 renderUserMessage(message.content)
 ) : (
 <>
 <div className="markdown-body prose prose-sm max-w-none">
 {message.isError && (
 <div className="mb-2 rounded-lg border border-[var(--error)] bg-[var(--bg-base)] px-3 py-2 text-xs text-[var(--error)]">
 <div className="font-medium">
 {message.errorHint || "模型调用异常，可重试上一轮。"}
 </div>
 {message.errorCode && (
 <div className="mt-1 text-[11px] text-[var(--error)]">
 错误码：{message.errorCode}
 </div>
 )}
 {message.errorDetail && (
 <details className="mt-1">
 <summary className="cursor-pointer text-[11px] text-[var(--error)] hover:text-[var(--error)] dark:text-[var(--error)]">
 查看详细错误
 </summary>
 <div className="mt-1 whitespace-pre-wrap text-[11px] text-[var(--error)]">
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
 <Suspense fallback={<div className="h-6" />}>
 <CitationList retrievals={message.retrievals} />
 </Suspense>
 )}
 {message.chartData && (
 plotlyUrl ? (
 <Suspense
 fallback={
 <div className="w-full h-[420px] rounded-xl bg-[var(--bg-elevated)] animate-pulse flex items-center justify-center text-sm text-[var(--text-muted)]">
 图表加载中…
 </div>
 }
 >
 <PlotlyFromUrl url={plotlyUrl} alt="图表" />
 </Suspense>
 ) : (
 <Suspense
 fallback={
 <div className="w-full h-[420px] rounded-xl bg-[var(--bg-elevated)] animate-pulse flex items-center justify-center text-sm text-[var(--text-muted)]">
 图表加载中…
 </div>
 }
 >
 <ChartViewer chartData={message.chartData} />
 </Suspense>
 )
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
 className="rounded-lg overflow-hidden border border-[var(--border-default)] bg-[var(--bg-base)] dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)]"
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
 {outputLevelMeta && (
 <div className="mt-3">
 <span
 title={OUTPUT_LEVEL_DESCRIPTIONS[message.outputLevel ?? ""] ?? ""}
 className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium cursor-help ${outputLevelMeta.className}`}
 >
 输出等级 {message.outputLevel?.toUpperCase()} · {outputLevelMeta.label}
 </span>
 {/* 首次出现输出等级时展示解释卡片 */}
 {!useOnboardStore((s) => s.isSeen("output_level")) && (
 <OutputLevelExplainer />
 )}
 </div>
 )}
 </>
 )}
 </div>

 {showRetry && (isUser || message.isError) && (
 <Button
 type="button"
 variant="ghost"
 onClick={onRetry}
 disabled={retryDisabled}
 title={isUser ? "重试上一轮" : "重试本次请求"}
 className={`w-8 h-8 rounded-full border
 flex items-center justify-center
 ${
 message.isError
 ? "border-[var(--error)] text-[var(--error)]"
 : "border-[var(--border-default)]"
 }
 mb-0.5`}
 >
 <RotateCcw size={12} />
 </Button>
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
 return <LazyMarkdownContent content={content} />;
 }

 // 将内容按引用标记分割，插入 CitationTooltip 组件
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
 <Suspense
 key={idx}
 fallback={
 <span className="mx-0.5 inline-flex min-w-[18px] items-center justify-center rounded bg-[var(--accent-subtle)] px-1 py-0 text-xs font-medium text-[var(--accent)] align-super leading-none">
 [{citationIndex}]
 </span>
 }
 >
 <CitationTooltip
 index={citationIndex}
 retrieval={retrieval}
 />
 </Suspense>
 );
 }
 // 渲染普通文本
 return <LazyMarkdownContent key={idx} content={part} />;
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
 if (prev.widget?.title !== next.widget?.title) return false;
 if (prev.widget?.html !== next.widget?.html) return false;
 if (prev.widget?.description !== next.widget?.description) return false;
 if (prev.toolStatus !== next.toolStatus) return false;
 if (prev.toolIntent !== next.toolIntent) return false;

 // 其他关键字段
 if (prev.isReasoning !== next.isReasoning) return false;
 if (prev.reasoningLive !== next.reasoningLive) return false;
 if (prev.chartData !== next.chartData) return false;
 if (prev.retrievals !== next.retrievals) return false;
 if (prev.outputLevel !== next.outputLevel) return false;

 // 重试相关
 if (prevProps.showRetry !== nextProps.showRetry) return false;
 if (prevProps.retryDisabled !== nextProps.retryDisabled) return false;

 // 所有关键字段相同，跳过渲染
 return true;
});
