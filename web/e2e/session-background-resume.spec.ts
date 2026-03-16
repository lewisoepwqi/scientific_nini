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
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;

      if (!url.startsWith("/api/")) {
        return originalFetch(input, init);
      }

      if (
        url.startsWith("/api/sessions") &&
        !url.includes("/messages") &&
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

      if (url === "/api/models/active") {
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

      if (url.startsWith("/api/sessions/") && url.endsWith("/messages")) {
        const match = url.match(/^\/api\/sessions\/([^/]+)\/messages$/);
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

      if (url.startsWith("/api/cost/session/")) {
        const sessionId = url.split("/").pop() || "";
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

      return new Response(JSON.stringify({ success: true, data: {} }), {
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
  await expect(page.locator(".text-emerald-500")).toBeVisible({ timeout: 10000 });
});

test("后台运行会话切回后应恢复消息、任务与运行指标", async ({ page }) => {
  await page.getByTitle("打开工作区").click();
  await expect(page.getByRole("button", { name: "会话A" })).toBeVisible();
  await expect(page.getByRole("button", { name: "会话B" })).toBeVisible();

  await page.getByPlaceholder("描述你的分析需求...").fill("启动会话A分析");
  await page.getByPlaceholder("描述你的分析需求...").press("Enter");

  await page.getByRole("button", { name: "会话B" }).click();

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

  await page.getByRole("button", { name: "会话A" }).click();

  await expect(page.getByText("后台会话仍在分析")).toBeVisible();
  await expect(page.getByTestId("streaming-token-usage")).toContainText("820");
  await expect(page.getByText(/^\d+s$/)).toBeVisible();
  await expect(page.getByRole("button", { name: /任务/ })).toContainText("1");
  await expect(
    page.locator("p").filter({ hasText: "检查数据质量" }).first(),
  ).toBeVisible();
});

test("后台会话在切走期间失败后，切回应恢复终态而非继续显示运行中", async ({ page }) => {
  await page.getByTitle("打开工作区").click();
  await page.getByPlaceholder("描述你的分析需求...").fill("启动会话A分析");
  await page.getByPlaceholder("描述你的分析需求...").press("Enter");

  await page.getByRole("button", { name: "会话B" }).click();

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

  await page.getByRole("button", { name: "会话A" }).click();

  await expect(page.getByText("后台会话执行中")).toBeVisible();
  await expect(page.getByText("错误: 服务器内部错误，请重试")).toBeVisible();
  await expect(page.getByText("Nini is working...")).toHaveCount(0);
  await expect(page.getByTestId("streaming-token-usage")).toHaveCount(0);
  await expect(page.locator("p").filter({ hasText: "执行关键分析" }).first()).toBeVisible();
});

test("后台会话在切走期间完成后，切回应恢复工具结果与最终回答", async ({ page }) => {
  await page.getByTitle("打开工作区").click();
  await page.getByPlaceholder("描述你的分析需求...").fill("启动会话A分析");
  await page.getByPlaceholder("描述你的分析需求...").press("Enter");

  await page.getByRole("button", { name: "会话B" }).click();

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

  await page.getByRole("button", { name: "会话A" }).click();

  await expect(page.getByText("最终结论：差异显著。")).toBeVisible();
  await expect(page.getByText("run_code")).toBeVisible();
  await expect(page.getByText("执行完成：统计分析完成")).toBeVisible();
  await expect(page.getByText("Nini is working...")).toHaveCount(0);
  await expect(page.getByTestId("streaming-token-usage")).toHaveCount(0);
  await expect(page.locator("p").filter({ hasText: "运行统计分析" }).first()).toBeVisible();
});
