import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    const sessionList = [
      {
        id: "session-a",
        title: "会话A",
        message_count: 0,
        source: "memory",
        created_at: "2026-03-16T00:00:00Z",
        updated_at: "2026-03-16T00:00:00Z",
        last_message_at: "2026-03-16T00:00:00Z",
      },
      {
        id: "session-b",
        title: "会话B",
        message_count: 0,
        source: "memory",
        created_at: "2026-03-16T00:00:00Z",
        updated_at: "2026-03-16T00:00:00Z",
        last_message_at: "2026-03-16T00:00:00Z",
      },
    ];

    const sessionMessages: Record<string, unknown[]> = {
      "session-a": [],
      "session-b": [],
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const rawUrl =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      const requestUrl = new URL(rawUrl, window.location.origin);
      const apiPath = `${requestUrl.pathname}${requestUrl.search}`;

      if (!requestUrl.pathname.startsWith("/api/")) {
        return originalFetch(input, init);
      }

      if (
        requestUrl.pathname.startsWith("/api/sessions") &&
        !requestUrl.pathname.includes("/messages") &&
        (!init?.method || init.method === "GET")
      ) {
        return new Response(
          JSON.stringify({
            success: true,
            data: sessionList,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (requestUrl.pathname === "/api/models/active") {
        return new Response(
          JSON.stringify({
            success: true,
            data: {
              provider_id: "mock-provider",
              provider_name: "Mock Provider",
              model: "mock-model",
              preferred_provider: "mock-provider",
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (
        requestUrl.pathname.startsWith("/api/sessions/") &&
        requestUrl.pathname.endsWith("/messages")
      ) {
        const match = requestUrl.pathname.match(/^\/api\/sessions\/([^/]+)\/messages$/);
        const sessionId = match?.[1] ?? "";
        return new Response(
          JSON.stringify({
            success: true,
            data: {
              session_id: sessionId,
              messages: sessionMessages[sessionId] ?? [],
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (requestUrl.pathname === "/api/intent/analyze") {
        return new Response(
          JSON.stringify({
            success: true,
            data: null,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (requestUrl.pathname.startsWith("/api/cost/session/")) {
        const sessionId = requestUrl.pathname.split("/").pop() || "";
        return new Response(
          JSON.stringify({
            session_id: sessionId,
            input_tokens: 0,
            output_tokens: 0,
            total_tokens: 0,
            estimated_cost_cny: 0,
            estimated_cost_usd: 0,
            model_breakdown: {},
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      return new Response(JSON.stringify({ success: true, data: { path: apiPath } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    class MockWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      readyState = MockWebSocket.CONNECTING;
      url: string;
      onopen: ((ev: Event) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;

      constructor(url: string) {
        this.url = url;
        this.readyState = MockWebSocket.OPEN;
        (window as unknown as { __mockWsInstance?: MockWebSocket }).__mockWsInstance = this;
        setTimeout(() => {
          this.onopen?.(new Event("open"));
        }, 0);
      }

      send(raw: string) {
        const payload = JSON.parse(raw) as Record<string, unknown>;
        if (payload.type === "ping") {
          this.emit({ type: "pong" });
          return;
        }

        if (payload.type === "chat") {
          const sessionId = String(payload.session_id ?? "");
          this.emit({
            type: "session",
            data: { session_id: sessionId },
            session_id: sessionId,
          });
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.(new CloseEvent("close"));
      }

      emit(payload: Record<string, unknown>) {
        this.onmessage?.(
          new MessageEvent("message", {
            data: JSON.stringify(payload),
          }),
        );
      }
    }

    (window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      MockWebSocket as unknown as typeof WebSocket;
  });

  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("status", { name: "已连接" })).toBeVisible({ timeout: 10000 });
});

function sessionItem(page: import("@playwright/test").Page, title: string) {
  return page.getByTitle(title);
}

async function switchSessionViaStore(
  page: import("@playwright/test").Page,
  targetSessionId: string,
) {
  await page.evaluate(async (sessionId) => {
    const store = (window as unknown as {
      __nini_store?: {
        getState: () => {
          switchSession: (nextSessionId: string) => Promise<void>;
        };
      };
    }).__nini_store;
    if (!store) throw new Error("store not ready");
    await store.getState().switchSession(sessionId);
  }, targetSessionId);
}

async function readStoreSnapshot(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const store = (window as unknown as {
      __nini_store?: {
        getState: () => Record<string, unknown>;
      };
    }).__nini_store;
    if (!store) throw new Error("store not ready");
    const state = store.getState() as Record<string, unknown>;
    const messages = Array.isArray(state.messages) ? state.messages : [];
    const tasks = Array.isArray(state.analysisTasks) ? state.analysisTasks : [];
    const streamingMetrics =
      typeof state._streamingMetrics === "object" && state._streamingMetrics
        ? (state._streamingMetrics as Record<string, unknown>)
        : {};

    return {
      sessionId: state.sessionId,
      isStreaming: state.isStreaming,
      messageContents: messages
        .map((message) =>
          typeof message === "object" && message && "content" in message
            ? String((message as Record<string, unknown>).content ?? "")
            : "",
        )
        .filter(Boolean),
      taskStates: tasks
        .map((task) => ({
          title:
            typeof task === "object" && task && "title" in task
              ? String((task as Record<string, unknown>).title ?? "")
              : "",
          status:
            typeof task === "object" && task && "status" in task
              ? String((task as Record<string, unknown>).status ?? "")
              : "",
        }))
        .filter((task) => task.title),
      tokenTotal:
        typeof streamingMetrics.totalTokens === "number" ? streamingMetrics.totalTokens : 0,
      hasTokenUsage: streamingMetrics.hasTokenUsage === true,
    };
  });
}

test("后台运行会话切回后应恢复消息、任务与运行指标", async ({ page }) => {
  await page.getByTitle("打开工作区").click();
  await expect(sessionItem(page, "会话A")).toBeVisible();
  await expect(sessionItem(page, "会话B")).toBeVisible();

  await page.getByPlaceholder("描述你的分析需求...").fill("启动会话A分析");
  await page.getByPlaceholder("描述你的分析需求...").press("Enter");

  await switchSessionViaStore(page, "session-b");

  await page.evaluate(() => {
    const ws = (window as unknown as {
      __mockWsInstance?: {
        emit: (payload: Record<string, unknown>) => void;
      };
    }).__mockWsInstance;
    if (!ws) throw new Error("mock ws not ready");

    ws.emit({ type: "iteration_start", session_id: "session-a", turn_id: "turn-a" });
    ws.emit({
      type: "analysis_plan",
      session_id: "session-a",
      turn_id: "turn-a",
      metadata: { seq: 1 },
      data: {
        raw_text: "1. 检查数据质量",
        steps: [
          {
            id: 1,
            title: "检查数据质量",
            tool_hint: "run_code",
            status: "pending",
            action_id: "task_1",
          },
        ],
      },
    });
    ws.emit({
      type: "plan_progress",
      session_id: "session-a",
      turn_id: "turn-a",
      metadata: { seq: 2 },
      data: {
        current_step_index: 1,
        total_steps: 1,
        step_title: "检查数据质量",
        step_status: "in_progress",
        next_hint: "完成后将结束流程。",
      },
    });
    ws.emit({
      type: "text",
      session_id: "session-a",
      turn_id: "turn-a",
      data: "后台会话仍在分析",
      metadata: {
        message_id: "session-a-msg-1",
        operation: "append",
      },
    });
    ws.emit({
      type: "token_usage",
      session_id: "session-a",
      turn_id: "turn-a",
      data: {
        model: "mock-model",
        input_tokens: 500,
        output_tokens: 320,
        total_tokens: 820,
        cost_usd: 0.01,
        session_total_tokens: 820,
        session_total_cost: 0.01,
      },
    });
  });

  await switchSessionViaStore(page, "session-a");

  await expect.poll(() => readStoreSnapshot(page)).toMatchObject({
    sessionId: "session-a",
    isStreaming: true,
    tokenTotal: 820,
    hasTokenUsage: true,
  });
  const runningSnapshot = await readStoreSnapshot(page);
  expect(runningSnapshot.messageContents).toContain("后台会话仍在分析");
  expect(runningSnapshot.taskStates).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        title: "检查数据质量",
        status: "in_progress",
      }),
    ]),
  );
});

test("后台会话在切走期间失败后，切回应恢复终态而非继续显示运行中", async ({ page }) => {
  await page.getByTitle("打开工作区").click();
  await page.getByPlaceholder("描述你的分析需求...").fill("启动会话A分析");
  await page.getByPlaceholder("描述你的分析需求...").press("Enter");

  await switchSessionViaStore(page, "session-b");

  await page.evaluate(() => {
    const ws = (window as unknown as {
      __mockWsInstance?: {
        emit: (payload: Record<string, unknown>) => void;
      };
    }).__mockWsInstance;
    if (!ws) throw new Error("mock ws not ready");

    ws.emit({ type: "iteration_start", session_id: "session-a", turn_id: "turn-a-error" });
    ws.emit({
      type: "analysis_plan",
      session_id: "session-a",
      turn_id: "turn-a-error",
      metadata: { seq: 1 },
      data: {
        raw_text: "1. 执行关键分析",
        steps: [
          {
            id: 1,
            title: "执行关键分析",
            tool_hint: "run_code",
            status: "pending",
            action_id: "task_error_1",
          },
        ],
      },
    });
    ws.emit({
      type: "plan_progress",
      session_id: "session-a",
      turn_id: "turn-a-error",
      metadata: { seq: 2 },
      data: {
        current_step_index: 1,
        total_steps: 1,
        step_title: "执行关键分析",
        step_status: "in_progress",
        next_hint: "完成后将结束流程。",
      },
    });
    ws.emit({
      type: "text",
      session_id: "session-a",
      turn_id: "turn-a-error",
      data: "后台会话执行中",
      metadata: {
        message_id: "session-a-msg-error",
        operation: "append",
      },
    });
    ws.emit({
      type: "error",
      session_id: "session-a",
      turn_id: "turn-a-error",
      data: "服务器内部错误，请重试",
    });
  });

  await switchSessionViaStore(page, "session-a");

  await expect.poll(() => readStoreSnapshot(page)).toMatchObject({
    sessionId: "session-a",
    isStreaming: false,
    tokenTotal: 0,
    hasTokenUsage: false,
  });
  const errorSnapshot = await readStoreSnapshot(page);
  expect(errorSnapshot.messageContents).toEqual(
    expect.arrayContaining([
      "后台会话执行中",
      "错误: 服务器内部错误，请重试",
    ]),
  );
  expect(errorSnapshot.taskStates).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        title: "执行关键分析",
        status: "failed",
      }),
    ]),
  );
});

test("后台会话在切走期间完成后，切回应恢复工具结果与最终回答", async ({ page }) => {
  await page.getByTitle("打开工作区").click();
  await page.getByPlaceholder("描述你的分析需求...").fill("启动会话A分析");
  await page.getByPlaceholder("描述你的分析需求...").press("Enter");

  await switchSessionViaStore(page, "session-b");

  await page.evaluate(() => {
    const ws = (window as unknown as {
      __mockWsInstance?: {
        emit: (payload: Record<string, unknown>) => void;
      };
    }).__mockWsInstance;
    if (!ws) throw new Error("mock ws not ready");

    ws.emit({ type: "iteration_start", session_id: "session-a", turn_id: "turn-a-done" });
    ws.emit({
      type: "analysis_plan",
      session_id: "session-a",
      turn_id: "turn-a-done",
      metadata: { seq: 1 },
      data: {
        raw_text: "1. 运行统计分析",
        steps: [
          {
            id: 1,
            title: "运行统计分析",
            tool_hint: "run_code",
            status: "pending",
            action_id: "task_done_1",
          },
        ],
      },
    });
    ws.emit({
      type: "plan_progress",
      session_id: "session-a",
      turn_id: "turn-a-done",
      metadata: { seq: 2 },
      data: {
        current_step_index: 1,
        total_steps: 1,
        step_title: "运行统计分析",
        step_status: "in_progress",
        next_hint: "完成后将结束流程。",
      },
    });
    ws.emit({
      type: "tool_call",
      session_id: "session-a",
      turn_id: "turn-a-done",
      tool_call_id: "tool-run-1",
      tool_name: "run_code",
      data: {
        name: "run_code",
        arguments: {
          code: "print('ok')",
          intent: "执行统计分析",
        },
      },
      metadata: {
        intent: "执行统计分析",
      },
    });
    ws.emit({
      type: "tool_result",
      session_id: "session-a",
      turn_id: "turn-a-done",
      tool_call_id: "tool-run-1",
      tool_name: "run_code",
      data: {
        status: "success",
        message: "统计分析完成",
      },
    });
    ws.emit({
      type: "text",
      session_id: "session-a",
      turn_id: "turn-a-done",
      data: "最终结论：差异显著。",
      metadata: {
        message_id: "session-a-msg-done",
        operation: "append",
      },
    });
    ws.emit({
      type: "done",
      session_id: "session-a",
      turn_id: "turn-a-done",
    });
  });

  await switchSessionViaStore(page, "session-a");

  await expect.poll(() => readStoreSnapshot(page)).toMatchObject({
    sessionId: "session-a",
    isStreaming: false,
    tokenTotal: 0,
    hasTokenUsage: false,
  });
  const doneSnapshot = await readStoreSnapshot(page);
  expect(doneSnapshot.messageContents).toEqual(
    expect.arrayContaining([
      "最终结论：差异显著。",
      "统计分析完成",
    ]),
  );
  expect(doneSnapshot.taskStates).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        title: "运行统计分析",
        status: "done",
      }),
    ]),
  );
});
