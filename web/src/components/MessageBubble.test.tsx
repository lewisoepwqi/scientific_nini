import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MessageBubble from "./MessageBubble";

vi.mock("./MarkdownContent", () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
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

    expect(screen.getByText(/分析偏好：效应量/u)).toBeInTheDocument();
    expect(
      screen.getByText(/文件名：gsd_research_report\.md/u),
    ).toBeInTheDocument();
  });
});
