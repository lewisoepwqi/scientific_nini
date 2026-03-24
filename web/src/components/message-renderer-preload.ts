/**
 * 会话恢复时按需预加载消息渲染器，避免已有气泡先出现、内容后补齐。
 */
import type { Message } from "../store";
import { contentNeedsMarkdownRenderer, preloadMarkdownRenderer } from "./LazyMarkdownContent";

function hasPlotlyUrl(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  const rawUrl =
    (typeof record.url === "string" && record.url) ||
    (typeof record.download_url === "string" && record.download_url) ||
    "";
  return rawUrl.toLowerCase().split("#")[0]?.split("?")[0]?.endsWith(".plotly.json") || false;
}

function shouldPreloadMarkdownForMessage(message: Message): boolean {
  if (contentNeedsMarkdownRenderer(message.content || "")) return true;
  if (typeof message.toolResult === "string" && contentNeedsMarkdownRenderer(message.toolResult)) {
    return true;
  }
  return false;
}

export async function preloadRenderersForMessages(messages: Message[]): Promise<void> {
  const loaders: Array<Promise<unknown>> = [];

  const needsMarkdown = messages.some(shouldPreloadMarkdownForMessage);
  const needsCitation = messages.some((message) => (message.retrievals?.length || 0) > 0);
  const needsReasoningPanel = messages.some(
    (message) => Boolean(message.isReasoning && message.content?.trim().startsWith("{")),
  );
  const needsChartViewer = messages.some(
    (message) => Boolean(message.chartData && !hasPlotlyUrl(message.chartData)),
  );
  const needsPlotlyFromUrl = messages.some(
    (message) =>
      Boolean(
        (typeof message.content === "string" && message.content.includes(".plotly.json")) ||
        hasPlotlyUrl(message.chartData),
      ),
  );
  const needsWidgetRenderer = messages.some((message) => Boolean(message.widget?.html));

  if (needsMarkdown) {
    loaders.push(preloadMarkdownRenderer());
  }
  if (needsCitation) {
    loaders.push(import("./CitationMarker"), import("./CitationList"));
  }
  if (needsReasoningPanel) {
    loaders.push(import("./ReasoningPanel"));
  }
  if (needsChartViewer) {
    loaders.push(import("./ChartViewer"));
  }
  if (needsPlotlyFromUrl) {
    loaders.push(import("./PlotlyFromUrl"));
  }
  if (needsWidgetRenderer) {
    loaders.push(import("./WidgetRenderer"));
  }

  if (loaders.length === 0) return;
  await Promise.all(loaders);
}
