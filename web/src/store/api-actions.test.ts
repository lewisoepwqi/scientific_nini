import { describe, expect, it } from "vitest";

import { buildMessagesFromHistory } from "./api-actions";
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
});
