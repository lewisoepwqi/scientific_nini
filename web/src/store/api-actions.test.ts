import { afterEach, describe, expect, it, vi } from "vitest";

import { buildMessagesFromHistory, buildSessionRestoreState, deleteSession } from "./api-actions";
import type { RawSessionMessage } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
});

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

  it("应忽略被工具参数污染的 reasoning 历史", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        content: "这是正文",
        event_type: "text",
        turn_id: "turn-polluted-1",
        _ts: "2026-03-09T10:00:00Z",
      },
      {
        role: "assistant",
        content: "content</arg_key><arg_value># 正文内容</arg_value></tool_call>",
        event_type: "reasoning",
        reasoning_id: "reason-polluted-1",
        turn_id: "turn-polluted-1",
        _ts: "2026-03-09T10:00:01Z",
      },
    ];

    const messages = buildMessagesFromHistory(rawMessages);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: "assistant",
      content: "这是正文",
    });
    expect(messages[0]?.isReasoning).not.toBe(true);
  });

  it("应优先将无 message_id 的 artifact 历史并入同轮 assistant 消息", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        content: "报告已更新",
        event_type: "text",
        turn_id: "turn-artifact-1",
        message_id: "turn-artifact-1-0",
        _ts: "2026-03-09T10:02:00Z",
      },
      {
        role: "assistant",
        event_type: "artifact",
        turn_id: "turn-artifact-1",
        artifacts: [
          {
            name: "report.html",
            type: "artifact",
            download_url: "/api/artifacts/sess/report.html",
          },
        ],
        _ts: "2026-03-09T10:02:01Z",
      },
    ];

    const messages = buildMessagesFromHistory(rawMessages);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: "assistant",
      content: "报告已更新",
      artifacts: [
        {
          name: "report.html",
          type: "artifact",
          download_url: "/api/artifacts/sess/report.html",
        },
      ],
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
    expect(restored.analysisPlanProgress).not.toBeNull();
    expect(restored.analysisPlanProgress?.steps.map((step) => step.title)).toEqual([
      "检查数据质量",
      "执行相关性分析",
    ]);
  });

  it("应从 task_state 历史中恢复任务列表", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        turn_id: "turn-state-1",
        _ts: "2026-03-04T10:00:00Z",
        tool_calls: [
          {
            id: "call-init-1",
            type: "function",
            function: {
              name: "task_state",
              arguments: JSON.stringify({
                operation: "init",
                tasks: [
                  { id: 1, title: "加载数据", status: "pending", tool_hint: "dataset_catalog" },
                  { id: 2, title: "执行建模", status: "pending", tool_hint: "stat_model" },
                ],
              }),
            },
          },
        ],
      },
      {
        role: "assistant",
        turn_id: "turn-state-1",
        _ts: "2026-03-04T10:00:05Z",
        tool_calls: [
          {
            id: "call-update-1",
            type: "function",
            function: {
              name: "task_state",
              arguments: JSON.stringify({
                operation: "update",
                tasks: [
                  { id: 1, title: "加载数据", status: "completed" },
                  { id: 2, title: "执行建模", status: "in_progress" },
                ],
              }),
            },
          },
        ],
      },
    ];

    const restored = buildSessionRestoreState(rawMessages);

    expect(restored.analysisTasks).toHaveLength(2);
    expect(restored.analysisTasks[0]).toMatchObject({
      turn_id: "turn-state-1",
      plan_step_id: 1,
      title: "加载数据",
      status: "done",
    });
    expect(restored.analysisTasks[1]).toMatchObject({
      turn_id: "turn-state-1",
      plan_step_id: 2,
      title: "执行建模",
      status: "in_progress",
      tool_hint: "stat_model",
    });
    expect(restored.analysisPlanProgress).not.toBeNull();
  });

  it("应跨 turn 继承最近计划链中的任务标题", () => {
    const rawMessages: RawSessionMessage[] = [
      {
        role: "assistant",
        turn_id: "turn-plan-1",
        _ts: "2026-03-09T10:10:00Z",
        tool_calls: [
          {
            id: "call-plan-init",
            type: "function",
            function: {
              name: "task_state",
              arguments: JSON.stringify({
                operation: "init",
                tasks: [
                  { id: 1, title: "读取工作区文章", status: "completed" },
                  { id: 2, title: "生成相关性热图", status: "completed" },
                  { id: 3, title: "更新文章图片引用", status: "pending" },
                  { id: 4, title: "整理最终稿", status: "pending" },
                ],
              }),
            },
          },
        ],
      },
      {
        role: "assistant",
        turn_id: "turn-plan-2",
        _ts: "2026-03-09T10:10:05Z",
        tool_calls: [
          {
            id: "call-plan-update",
            type: "function",
            function: {
              name: "task_state",
              arguments: JSON.stringify({
                operation: "update",
                tasks: [
                  { id: 3, status: "completed" },
                  { id: 4, status: "in_progress" },
                ],
              }),
            },
          },
        ],
      },
    ];

    const restored = buildSessionRestoreState(rawMessages);
    expect(restored.analysisTasks).toHaveLength(4);
    expect(restored.analysisTasks[2]).toMatchObject({
      plan_step_id: 3,
      title: "更新文章图片引用",
      status: "done",
    });
    expect(restored.analysisTasks[3]).toMatchObject({
      plan_step_id: 4,
      title: "整理最终稿",
      status: "in_progress",
    });
    expect(restored.analysisPlanProgress?.steps.map((step) => step.title)).toEqual([
      "读取工作区文章",
      "生成相关性热图",
      "更新文章图片引用",
      "整理最终稿",
    ]);
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

describe("deleteSession", () => {
  it("后端返回 success=false 时不应视为删除成功", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ success: false }),
    } as Response);

    await expect(deleteSession("sess-1")).resolves.toBe(false);
  });
});
