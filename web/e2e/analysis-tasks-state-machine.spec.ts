import { expect, test, type Page } from "@playwright/test";

function visibleByTestId(page: Page, id: string) {
  return page.locator(`[data-testid="${id}"]:visible`);
}

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
        if (
          url === "/api/sessions" &&
          (!init?.method || init.method.toUpperCase() === "GET")
        ) {
          return new Response(JSON.stringify({ success: true, data: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
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
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN;
          this.onopen?.(new Event("open"));
        }, 0);
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
        }, 0);
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
        }, 0);
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
});

test("失败后成功会恢复到进行中，不再卡在失败", async ({ page }) => {
  const input = page.getByPlaceholder("描述你的分析需求...");
  await input.fill("recover-from-failure");
  await input.press("Enter");

  await expect(visibleByTestId(page, "analysis-task-item-1")).toBeVisible();
  await expect(visibleByTestId(page, "analysis-task-attempt-status-1")).toHaveText(
    "失败",
  );
  await expect(visibleByTestId(page, "analysis-task-attempt-status-2")).toHaveText(
    "成功",
  );
  await expect(visibleByTestId(page, "analysis-task-status-1")).toHaveText("进行中");
  await expect(visibleByTestId(page, "analysis-task-status-1")).not.toHaveText("失败");
});

test("工具成功后收到步骤完成事件，状态最终收敛为已完成", async ({ page }) => {
  const input = page.getByPlaceholder("描述你的分析需求...");
  await input.fill("converge-done");
  await input.press("Enter");

  await expect(visibleByTestId(page, "analysis-task-item-1")).toBeVisible();
  await expect(visibleByTestId(page, "analysis-task-attempt-status-1")).toHaveText(
    "成功",
  );
  await expect(visibleByTestId(page, "analysis-task-status-1")).toHaveText("已完成");
  await expect(visibleByTestId(page, "analysis-task-activity-1")).toContainText(
    "步骤已完成",
  );
});
