import { describe, expect, it } from "vitest";

import { buildMessagesFromHistory, buildSessionRestoreState } from "./api-actions";
import type { RawSessionMessage } from "./types";

describe("buildMessagesFromHistory", () => {
  it("应基于 canonical 字段合并历史文本、reasoning 与工具结果", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "user",
        content: "请分析这份数据",
        turn_id: "turn-1",
        _ts: "2026-03-03T10:00:00Z",
      },
      {
        role: "assistant",
        content: "先给出初稿",
        event_type: "text",
        operation: "replace",
        message_id: "turn-1-0",
        turn_id: "turn-1",
        _ts: "2026-03-03T10:00:01Z",
      },
      {
        role: "assistant",
        content: "这是完整回答",
        event_type: "text",
        operation: "replace",
        message_id: "turn-1-0",
        turn_id: "turn-1",
        _ts: "2026-03-03T10:00:02Z",
      },
      {
        role: "assistant",
        content: "先检查变量",
        event_type: "reasoning",
        reasoning_id: "reason-1",
        turn_id: "turn-1",
        _ts: "2026-03-03T10:00:03Z",
      },
      {
        role: "assistant",
        content: "完整推理结论",
        event_type: "reasoning",
        reasoning_id: "reason-1",
        turn_id: "turn-1",
        _ts: "2026-03-03T10:00:04Z",
      },
      {
        role: "assistant",
        event_type: "tool_call",
        turn_id: "turn-1",
        tool_calls: [
          {
            id: "call-1",
            type: "function",
            function: {
              name: "run_code",
              arguments: '{"code":"print(1)","intent":"计算均值"}',
            },
          },
        ],
        _ts: "2026-03-03T10:00:05Z",
      },
      {
        role: "tool",
        content: '{"message":"执行成功"}',
        tool_call_id: "call-1",
        tool_name: "run_code",
        status: "success",
        intent: "计算均值",
        turn_id: "turn-1",
        _ts: "2026-03-03T10:00:06Z",
      },
    ];

    const messages = buildMessagesFromHistory(rawMessages);

    expect(messages).toHaveLength(4);
    expect(messages[0]).toMatchObject({
      role: "user",
      content: "请分析这份数据",
      turnId: "turn-1",
    });
    expect(messages[1]).toMatchObject({
      role: "assistant",
      content: "这是完整回答",
      messageId: "turn-1-0",
      turnId: "turn-1",
    });
    expect(messages[2]).toMatchObject({
      role: "assistant",
      content: "完整推理结论",
      isReasoning: true,
      reasoningId: "reason-1",
      reasoningLive: false,
      turnId: "turn-1",
    });
    expect(messages[3]).toMatchObject({
      role: "tool",
      toolCallId: "call-1",
      toolName: "run_code",
      toolIntent: "计算均值",
      toolResult: "执行成功",
      toolStatus: "success",
      turnId: "turn-1",
    });
  });

  it("应恢复历史 reasoning_live 状态", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        content: "流式推理片段",
        event_type: "reasoning",
        reasoning_id: "reason-live-1",
        reasoning_live: true,
        turn_id: "turn-live-1",
        _ts: "2026-03-05T10:00:00Z",
      },
    ];

    const messages = buildMessagesFromHistory(rawMessages);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: "assistant",
      isReasoning: true,
      reasoningId: "reason-live-1",
      reasoningLive: true,
      turnId: "turn-live-1",
    });
  });

  it("应从 task_write 历史中恢复任务列表", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        turn_id: "turn-restore-1",
        _ts: "2026-03-04T10:00:00Z",
        tool_calls: [
          {
            id: "call-init-1",
            type: "function",
            function: {
              name: "task_write",
              arguments: JSON.stringify({
                mode: "init",
                tasks: [
                  { id: 1, title: "检查数据质量", status: "pending", tool_hint: "data_summary" },
                  { id: 2, title: "执行相关性分析", status: "pending", tool_hint: "correlation" },
                ],
              }),
            },
          },
        ],
      },
      {
        role: "assistant",
        turn_id: "turn-restore-1",
        _ts: "2026-03-04T10:00:05Z",
        tool_calls: [
          {
            id: "call-update-1",
            type: "function",
            function: {
              name: "task_write",
              arguments: JSON.stringify({
                mode: "update",
                tasks: [
                  { id: 1, title: "检查数据质量", status: "completed" },
                  { id: 2, title: "执行相关性分析", status: "in_progress" },
                ],
              }),
            },
          },
        ],
      },
      {
        role: "assistant",
        turn_id: "turn-restore-2",
        _ts: "2026-03-04T10:01:00Z",
        tool_calls: [
          {
            id: "call-init-2",
            type: "function",
            function: {
              name: "task_write",
              arguments: JSON.stringify({
                mode: "init",
                tasks: [
                  { id: 1, title: "生成报告", status: "completed", tool_hint: "generate_report" },
                ],
              }),
            },
          },
        ],
      },
    ];

    const restored = buildSessionRestoreState(rawMessages);

    expect(restored.analysisTasks).toHaveLength(3);
    expect(restored.analysisTasks[0]).toMatchObject({
      turn_id: "turn-restore-1",
      plan_step_id: 1,
      title: "检查数据质量",
      status: "done",
    });
    expect(restored.analysisTasks[1]).toMatchObject({
      turn_id: "turn-restore-1",
      plan_step_id: 2,
      title: "执行相关性分析",
      status: "in_progress",
      current_activity: "步骤执行中",
    });
    expect(restored.analysisTasks[2]).toMatchObject({
      turn_id: "turn-restore-2",
      title: "生成报告",
      status: "done",
    });
    expect(restored.analysisPlanProgress).toBeNull();
  });

  it("应从 ask_user_question 历史中恢复用户选择与输入摘要", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        event_type: "tool_call",
        turn_id: "turn-ask-1",
        tool_calls: [
          {
            id: "call-ask-1",
            type: "function",
            function: {
              name: "ask_user_question",
              arguments: JSON.stringify({
                questions: [
                  {
                    question: "你更关注哪类结果？",
                    header: "分析偏好",
                  },
                  {
                    question: "请输入导出文件名",
                    header: "文件名",
                  },
                ],
              }),
            },
          },
        ],
        _ts: "2026-03-04T10:02:00Z",
      },
      {
        role: "tool",
        content: JSON.stringify({
          success: true,
          message: "已收到用户回答。",
          data: {
            questions: [
              {
                question: "你更关注哪类结果？",
                header: "分析偏好",
              },
              {
                question: "请输入导出文件名",
                header: "文件名",
              },
            ],
            answers: {
              "你更关注哪类结果？": "效应量",
              请输入导出文件名: "gsd_research_report.md",
            },
          },
        }),
        tool_call_id: "call-ask-1",
        tool_name: "ask_user_question",
        status: "success",
        turn_id: "turn-ask-1",
        _ts: "2026-03-04T10:02:01Z",
      },
    ];

    const messages = buildMessagesFromHistory(rawMessages);

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: "tool",
      toolCallId: "call-ask-1",
      toolName: "ask_user_question",
      toolStatus: "success",
    });
    expect(messages[0]?.toolResult).toContain("分析偏好：你更关注哪类结果？");
    expect(messages[0]?.toolResult).toContain("→ 效应量");
    expect(messages[0]?.toolResult).toContain("文件名：请输入导出文件名");
    expect(messages[0]?.toolResult).toContain("→ gsd_research_report.md");
  });
});
