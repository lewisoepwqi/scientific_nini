import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;

      if (url.startsWith("/api/")) {
        // GET /api/sessions - 返回已创建的会话列表
        if (
          url === "/api/sessions" &&
          (!init?.method || init.method.toUpperCase() === "GET")
        ) {
          const mockSession = (window as unknown as { __mockSessionId?: string }).__mockSessionId;
          return new Response(
            JSON.stringify({
              success: true,
              data: mockSession
                ? [{ session_id: mockSession, title: "测试会话", created_at: Date.now() }]
                : [],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }

        // POST /api/sessions - 创建新会话
        if (url === "/api/sessions" && init?.method?.toUpperCase() === "POST") {
          const sessionId = "test-session-" + Date.now();
          (window as unknown as { __mockSessionId?: string }).__mockSessionId = sessionId;
          return new Response(
            JSON.stringify({
              success: true,
              data: { session_id: sessionId },
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

        return new Response(JSON.stringify({ success: true, data: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return originalFetch(input, init);
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
        // Store instance for test access
        (window as unknown as { __mockWsInstance?: MockWebSocket }).__mockWsInstance = this;
        // Set readyState immediately so sendMessage can use it
        this.readyState = MockWebSocket.OPEN;
        setTimeout(() => {
          this.onopen?.(new Event("open"));
        }, 50);
      }

      send(raw: string) {
        const payload = JSON.parse(raw) as Record<string, unknown>;
        if (payload.type === "ping") {
          this.emit({ type: "pong" });
          return;
        }

        if (payload.type !== "chat") return;

        const content = String(payload.content ?? "");
        if (content.includes("recover-from-failure")) {
          this.emitRecoverFlow();
          return;
        }

        if (content.includes("converge-done")) {
          this.emitConvergeDoneFlow();
          return;
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.(new CloseEvent("close"));
      }

      private emitRecoverFlow() {
        setTimeout(() => {
          this.emit({ type: "session", data: { session_id: "sess-task-recover" } });
          this.emit({ type: "iteration_start", turn_id: "turn-task-recover" });
          this.emit({
            type: "analysis_plan",
            turn_id: "turn-task-recover",
            metadata: { seq: 1 },
            data: {
              raw_text: "1. 执行关键分析",
              steps: [
                {
                  id: 1,
                  title: "执行关键分析",
                  tool_hint: "run_code",
                  status: "pending",
                  action_id: "task_1",
                },
              ],
            },
          });
          this.emit({
            type: "plan_progress",
            turn_id: "turn-task-recover",
            metadata: { seq: 2 },
            data: {
              current_step_index: 1,
              total_steps: 1,
              step_title: "执行关键分析",
              step_status: "in_progress",
              next_hint: "完成后将结束流程。",
            },
          });
          this.emit({
            type: "task_attempt",
            turn_id: "turn-task-recover",
            metadata: { seq: 3 },
            data: {
              step_id: 1,
              action_id: "task_1",
              tool_name: "run_code",
              attempt: 1,
              max_attempts: 2,
              status: "failed",
              error: "第一次执行失败",
              note: "第 1/2 次尝试失败",
            },
          });
          this.emit({
            type: "task_attempt",
            turn_id: "turn-task-recover",
            metadata: { seq: 4 },
            data: {
              step_id: 1,
              action_id: "task_1",
              tool_name: "run_code",
              attempt: 2,
              max_attempts: 2,
              status: "in_progress",
              note: "第 2/2 次尝试执行中",
            },
          });
          this.emit({
            type: "task_attempt",
            turn_id: "turn-task-recover",
            metadata: { seq: 5 },
            data: {
              step_id: 1,
              action_id: "task_1",
              tool_name: "run_code",
              attempt: 2,
              max_attempts: 2,
              status: "success",
              note: "第 2/2 次尝试成功",
            },
          });
          this.emit({
            type: "text",
            turn_id: "turn-task-recover",
            data: "任务重试后执行成功。",
          });
        }, 50);
      }

      private emitConvergeDoneFlow() {
        setTimeout(() => {
          this.emit({ type: "session", data: { session_id: "sess-task-done" } });
          this.emit({ type: "iteration_start", turn_id: "turn-task-done" });
          this.emit({
            type: "analysis_plan",
            turn_id: "turn-task-done",
            metadata: { seq: 1 },
            data: {
              raw_text: "1. 生成最终结论",
              steps: [
                {
                  id: 1,
                  title: "生成最终结论",
                  tool_hint: "run_code",
                  status: "pending",
                  action_id: "task_1",
                },
              ],
            },
          });
          this.emit({
            type: "plan_progress",
            turn_id: "turn-task-done",
            metadata: { seq: 2 },
            data: {
              current_step_index: 1,
              total_steps: 1,
              step_title: "生成最终结论",
              step_status: "in_progress",
              next_hint: "完成后将结束流程。",
            },
          });
          this.emit({
            type: "task_attempt",
            turn_id: "turn-task-done",
            metadata: { seq: 3 },
            data: {
              step_id: 1,
              action_id: "task_1",
              tool_name: "run_code",
              attempt: 1,
              max_attempts: 1,
              status: "success",
              note: "第 1/1 次尝试成功",
            },
          });
          this.emit({
            type: "plan_step_update",
            turn_id: "turn-task-done",
            metadata: { seq: 4 },
            data: {
              id: 1,
              title: "生成最终结论",
              tool_hint: "run_code",
              status: "completed",
              action_id: "task_1",
            },
          });
          this.emit({
            type: "plan_progress",
            turn_id: "turn-task-done",
            metadata: { seq: 5 },
            data: {
              current_step_index: 1,
              total_steps: 1,
              step_title: "生成最终结论",
              step_status: "done",
              next_hint: "全部步骤已完成。",
            },
          });
          this.emit({ type: "done", turn_id: "turn-task-done" });
        }, 50);
      }

      private emit(payload: Record<string, unknown>) {
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

  // 等待 WebSocket 连接建立（使用更通用的指示器）
  await expect(page.getByRole('status', { name: '已连接' })).toBeVisible({ timeout: 10000 });

  // 如果没有会话，创建一个
  await page.getByText('新建会话').click()
  await page.waitForTimeout(800)
});

test("失败后成功会恢复到进行中，不再卡在失败", async ({ page }) => {
  // 等待 WebSocket 连接建立
  await page.waitForTimeout(500);

  // 通过模拟发送消息触发 recover flow
  await page.evaluate(() => {
    const ws = (window as unknown as { __mockWsInstance?: WebSocket }).__mockWsInstance;
    if (ws && ws.readyState === WebSocket.OPEN) {
      // 触发 recover flow
      ws.send(JSON.stringify({ type: 'chat', content: 'recover-from-failure' }));
    }
  });

  // 等待事件处理完成
  await page.waitForTimeout(1000);

  // Directly emit the WebSocket events to simulate the recover flow
  await page.evaluate(() => {
    const ws = (window as unknown as { __mockWsInstance?: MockWebSocket }).__mockWsInstance;
    if (ws?.emitRecoverFlow) {
      ws.emitRecoverFlow();
    }
  });

  // 在工作区任务面板中验证任务状态
  await expect(page.getByText("执行关键分析").first()).toBeVisible({ timeout: 10000 });
  // 验证任务最终状态为"已完成"
  await expect(page.getByText("已完成").first()).toBeVisible();
});

test("工具成功后收到步骤完成事件，状态最终收敛为已完成", async ({ page }) => {
  // 等待 WebSocket 连接建立
  await page.waitForTimeout(500);

  // 通过模拟发送消息触发 converge-done flow
  await page.evaluate(() => {
    const ws = (window as unknown as { __mockWsInstance?: WebSocket }).__mockWsInstance;
    if (ws && ws.readyState === WebSocket.OPEN) {
      // 触发 converge-done flow
      ws.send(JSON.stringify({ type: 'chat', content: 'converge-done' }));
    }
  });

  // 等待事件处理完成
  await page.waitForTimeout(1000);

  // Directly emit the WebSocket events to simulate the converge-done flow
  await page.evaluate(() => {
    const ws = (window as unknown as { __mockWsInstance?: MockWebSocket }).__mockWsInstance;
    if (ws?.emitConvergeDoneFlow) {
      ws.emitConvergeDoneFlow();
    }
  });

  // 在工作区任务面板中验证任务状态
  await expect(page.getByText("生成最终结论").first()).toBeVisible({ timeout: 10000 });
  // 验证任务最终状态为"已完成"
  await expect(page.getByText("已完成").first()).toBeVisible();
  // 验证步骤已完成
  await expect(page.getByText("全部步骤已完成。").first()).toBeVisible();
});
