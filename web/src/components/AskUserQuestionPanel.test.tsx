import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AskUserQuestionPanel from "./AskUserQuestionPanel";
import type { PendingAskUserQuestion } from "../store";

function getOptionRadio(label: string) {
  return screen.getByRole("radio", { name: new RegExp(`^${label}`) });
}

function buildPending(): PendingAskUserQuestion {
  return {
    sessionId: "session-1",
    sessionTitle: "测试会话",
    toolCallId: "tool-1",
    questionCount: 3,
    createdAt: Date.now(),
    attentionRequestedAt: Date.now(),
    questions: [
      {
        question: "你希望分析哪个数据范围？",
        header: "数据范围",
        options: [
          { label: "最近30天", description: "适合快速观察近期变化" },
          { label: "最近90天", description: "适合看中期趋势" },
        ],
      },
      {
        question: "结果需要什么输出格式？",
        header: "输出格式",
        options: [
          { label: "Markdown 报告", description: "适合直接阅读" },
          { label: "图表导出", description: "适合演示材料" },
        ],
        allowTextInput: true,
      },
      {
        question: "是否确认覆盖现有文件？",
        header: "风险确认",
        question_type: "risk_confirmation",
        options: [
          { label: "确认覆盖", description: "会替换现有内容" },
          { label: "取消", description: "保留现有文件" },
        ],
        allowTextInput: false,
      },
    ],
  };
}

describe("AskUserQuestionPanel", () => {
  it("应使用换行 tab 并且一次只展示一个问题", () => {
    render(<AskUserQuestionPanel pending={buildPending()} onSubmit={vi.fn()} />);

    expect(screen.getByRole("tablist")).toHaveClass("flex-wrap");
    expect(screen.getByText("你希望分析哪个数据范围？")).toBeInTheDocument();
    expect(screen.queryByText("结果需要什么输出格式？")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /输出格式/u }));

    expect(screen.getByText("结果需要什么输出格式？")).toBeInTheDocument();
    expect(screen.queryByText("你希望分析哪个数据范围？")).not.toBeInTheDocument();
  });

  it("切换问题后应保留已填写答案", () => {
    render(<AskUserQuestionPanel pending={buildPending()} onSubmit={vi.fn()} />);

    fireEvent.click(getOptionRadio("最近30天"));
    fireEvent.click(screen.getByRole("tab", { name: /输出格式/u }));

    const customInput = screen.getByPlaceholderText("或输入自定义回答");
    fireEvent.change(customInput, { target: { value: "请附带 SVG 图表" } });

    fireEvent.click(screen.getByRole("tab", { name: /数据范围/u }));
    expect(getOptionRadio("最近30天")).toBeChecked();

    fireEvent.click(screen.getByRole("tab", { name: /输出格式/u }));
    expect(screen.getByDisplayValue("请附带 SVG 图表")).toBeInTheDocument();
  });

  it("提交时若存在未完成题应跳转到首个未完成题", () => {
    render(<AskUserQuestionPanel pending={buildPending()} onSubmit={vi.fn()} />);

    fireEvent.click(getOptionRadio("最近30天"));
    fireEvent.click(screen.getByRole("button", { name: "提交回答并继续" }));

    expect(screen.getByText("结果需要什么输出格式？")).toBeInTheDocument();
    expect(screen.getByText("请先完成该问题")).toBeInTheDocument();
  });

  it("全部回答后应提交所有答案", () => {
    const onSubmit = vi.fn();
    render(<AskUserQuestionPanel pending={buildPending()} onSubmit={onSubmit} />);

    fireEvent.click(getOptionRadio("最近90天"));
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    fireEvent.click(getOptionRadio("Markdown 报告"));
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    fireEvent.click(getOptionRadio("确认覆盖"));
    fireEvent.click(screen.getByRole("button", { name: "提交回答并继续" }));

    expect(onSubmit).toHaveBeenCalledWith({
      "你希望分析哪个数据范围？": "最近90天",
      "结果需要什么输出格式？": "Markdown 报告",
      "是否确认覆盖现有文件？": "确认覆盖",
    });
  });
});
