import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MessageBubble from "./MessageBubble";

vi.mock("./MarkdownContent", () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
vi.mock("./LazyMarkdownContent", () => ({
  default: ({ content }: { content: string }) => (
    <div className="whitespace-pre-wrap break-words">{content}</div>
  ),
}));
vi.mock("./PlotlyFromUrl", () => ({
  default: ({ url }: { url: string }) => <div data-testid="plotly-from-url">{url}</div>,
}));
vi.mock("./WidgetRenderer", () => ({
  default: ({
    title,
    description,
  }: {
    title: string;
    description?: string | null;
  }) => (
    <div data-testid="widget-renderer">
      {title}
      {description ? `:${description}` : ""}
    </div>
  ),
}));

afterEach(() => {
  vi.useRealTimers();
});

describe("MessageBubble reasoning", () => {
  it("Thinking 应默认折叠并在运行中显示扫光样式", () => {
    render(
      <MessageBubble
        message={{
          id: "reason-1",
          role: "assistant",
          content: "正在分析变量关系",
          isReasoning: true,
          reasoningLive: true,
          timestamp: Date.now(),
        }}
      />,
    );

    const thinking = screen.getByText("Thinking");
    expect(thinking).toHaveClass("nini-thinking-shimmer");
    expect(screen.queryByText("正在分析变量关系")).not.toBeInTheDocument();
  });

  it("点击 Thinking 后应展开内容，结束后移除扫光样式", () => {
    const { rerender } = render(
      <MessageBubble
        message={{
          id: "reason-2",
          role: "assistant",
          content: "先检查数据质量，再执行相关分析。",
          isReasoning: true,
          reasoningLive: true,
          timestamp: Date.now(),
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Thinking/u }));

    rerender(
      <MessageBubble
        message={{
          id: "reason-2",
          role: "assistant",
          content: "先检查数据质量，再执行相关分析。",
          isReasoning: true,
          reasoningLive: false,
          timestamp: Date.now(),
        }}
      />,
    );

    expect(screen.getByText("先检查数据质量，再执行相关分析。")).toBeInTheDocument();
    expect(screen.getByText("Thinking")).not.toHaveClass("nini-thinking-shimmer");
  });

  it("工具结果展开后应显示 ask_user_question 的回答摘要", () => {
    render(
      <MessageBubble
        message={{
          id: "tool-ask-1",
          role: "tool",
          content: "已收到用户回答：\n- 分析偏好：效应量\n- 文件名：gsd_research_report.md",
          toolName: "ask_user_question",
          toolCallId: "tool-ask-1",
          toolResult:
            "已收到用户回答：\n- 分析偏好：效应量\n- 文件名：gsd_research_report.md",
          toolStatus: "success",
          timestamp: Date.now(),
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /ask_user_question/u }));

    expect(screen.getAllByText(/分析偏好：效应量/u).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/文件名：gsd_research_report\.md/u).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("成功工具调用在折叠状态应显示结果摘要，展开后显示完整结果", () => {
    const fullResult =
      "已生成月度分析报告，包含数据概览、相关性分析、回归建模、异常值检查、稳健性检验、敏感性分析和结论建议，请继续导出 PDF 版本并同步保存 Markdown 副本。";

    render(
      <MessageBubble
        message={{
          id: "tool-report-1",
          role: "tool",
          content: fullResult,
          toolName: "generate_report",
          toolCallId: "tool-report-1",
          toolResult: fullResult,
          toolStatus: "success",
          timestamp: Date.now(),
        }}
      />,
    );

    expect(screen.getByText(/执行完成：已生成月度分析报告/u)).toBeInTheDocument();
    expect(screen.queryByText(fullResult)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /generate_report/u }));

    expect(screen.getByText(fullResult)).toBeInTheDocument();
  });

  it("chart 事件仅包含 plotly.json URL 时应走 URL 渲染分支", async () => {
    render(
      <MessageBubble
        message={{
          id: "chart-url-1",
          role: "assistant",
          content: "图表已生成",
          chartData: {
            chart_id: "chart_123",
            name: "示例图",
            url: "/api/artifacts/sess-1/demo.plotly.json",
            chart_type: "bar",
          },
          timestamp: Date.now(),
        }}
      />,
    );

    // lazy() 组件需要异步 resolve，等待 Suspense fallback 消失
    expect(
      await screen.findByTestId("plotly-from-url"),
    ).toBeInTheDocument();
    expect(screen.getByText("/api/artifacts/sess-1/demo.plotly.json")).toBeInTheDocument();
  });

  it("generate_widget 工具结果应渲染内嵌组件", async () => {
    render(
      <MessageBubble
        message={{
          id: "tool-widget-1",
          role: "tool",
          content: "已生成内嵌组件：统计摘要卡",
          toolName: "generate_widget",
          toolCallId: "tool-widget-1",
          toolResult: "已生成内嵌组件：统计摘要卡",
          toolStatus: "success",
          widget: {
            title: "统计摘要卡",
            html: "<section>demo</section>",
            description: "展示核心指标",
          },
          timestamp: Date.now(),
        }}
      />,
    );

    expect(await screen.findByTestId("widget-renderer")).toHaveTextContent(
      "统计摘要卡:展示核心指标",
    );
  });
});
