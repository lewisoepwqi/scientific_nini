import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window)
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url

      if (url.startsWith('/api/')) {
        if (url === '/api/sessions' && (!init?.method || init.method === 'GET')) {
          return new Response(JSON.stringify({ success: true, data: [] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url === '/api/models/active') {
          return new Response(
            JSON.stringify({
              success: true,
              data: {
                provider_id: 'mock-provider',
                provider_name: 'Mock Provider',
                model: 'mock-model',
                preferred_provider: 'mock-provider',
              },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        return new Response(JSON.stringify({ success: true, data: {} }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return originalFetch(input, init)
    }

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.CONNECTING
      url: string
      onopen: ((ev: Event) => void) | null = null
      onclose: ((ev: CloseEvent) => void) | null = null
      onerror: ((ev: Event) => void) | null = null
      onmessage: ((ev: MessageEvent) => void) | null = null

      constructor(url: string) {
        this.url = url
        ;(window as unknown as { __mockWsInstance?: MockWebSocket }).__mockWsInstance = this
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
        }, 0)
      }

      send(raw: string) {
        console.log('[MockWebSocket] send called:', raw)
        const payload = JSON.parse(raw) as Record<string, unknown>
        if (payload.type === 'ping') {
          this.emit({ type: 'pong' })
          return
        }

        if (payload.type === 'chat') {
          console.log('[MockWebSocket] handling chat')
          setTimeout(() => {
            console.log('[MockWebSocket] emitting events')
            this.emit({ type: 'session', data: { session_id: 'sess-plan' } })
            this.emit({ type: 'iteration_start', turn_id: 'turn-plan' })
            this.emit({ type: 'text', data: '开始执行分析计划', turn_id: 'turn-plan' })
            this.emit({
              type: 'analysis_plan',
              turn_id: 'turn-plan',
              data: {
                raw_text: '1. 加载并检查数据集\\n2. 汇总分析结论',
                steps: [
                  { id: 1, title: '加载并检查数据集', tool_hint: 'echo_tool', status: 'pending' },
                  { id: 2, title: '汇总分析结论', tool_hint: 'echo_tool', status: 'pending' },
                ],
              },
            })
            this.emit({
              type: 'plan_progress',
              turn_id: 'turn-plan',
              metadata: { seq: 1 },
              data: {
                current_step_index: 1,
                total_steps: 2,
                step_title: '加载并检查数据集',
                step_status: 'in_progress',
                next_hint: '完成后将进入：汇总分析结论',
              },
            })
            this.emit({
              type: 'plan_progress',
              turn_id: 'turn-plan',
              metadata: { seq: 2 },
              data: {
                current_step_index: 2,
                total_steps: 2,
                step_title: '汇总分析结论',
                step_status: 'done',
                next_hint: '全部步骤已完成。',
              },
            })
            this.emit({ type: 'done', turn_id: 'turn-plan' })
            console.log('[MockWebSocket] all events emitted')
          }, 100)
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }

      private emit(payload: Record<string, unknown>) {
        this.onmessage?.(
          new MessageEvent('message', {
            data: JSON.stringify(payload),
          }),
        )
      }
    }

    ;(window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      MockWebSocket as unknown as typeof WebSocket
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')

  // 等待 WebSocket 连接建立（使用更通用的指示器）
  await expect(page.locator('.text-emerald-500')).toBeVisible({ timeout: 10000 })
  // 额外等待确保应用完全初始化
  await page.waitForTimeout(300)
})

test('顶部分析进度头部可见并随事件更新', async ({ page }) => {
  // Trigger WebSocket events directly to avoid sendMessage race condition
  await page.evaluate(() => {
    const ws = (window as unknown as { __mockWsInstance?: WebSocket }).__mockWsInstance
    if (ws && ws.onmessage) {
      ws.onmessage(new MessageEvent('message', {
        data: JSON.stringify({
          type: 'analysis_plan',
          turn_id: 'test-turn',
          data: {
            raw_text: '1. 加载并检查数据集\n2. 汇总分析结论',
            steps: [
              { id: 1, title: '加载并检查数据集', tool_hint: 'echo_tool', status: 'done' },
              { id: 2, title: '汇总分析结论', tool_hint: 'echo_tool', status: 'done' },
            ],
          },
        }),
      }))
      ws.onmessage(new MessageEvent('message', {
        data: JSON.stringify({
          type: 'plan_progress',
          turn_id: 'test-turn',
          metadata: { seq: 1 },
          data: {
            current_step_index: 2,
            total_steps: 2,
            step_title: '汇总分析结论',
            step_status: 'done',
            next_hint: '全部步骤已完成。',
          },
        }),
      }))
    }
  })

  await page.waitForTimeout(300)

  await expect(page.getByTestId('analysis-plan-header')).toBeVisible({ timeout: 10000 })
  await expect(page.getByTestId('analysis-plan-step-index')).toHaveText('Step 2/2')
  await expect(page.getByTestId('analysis-plan-current-title')).toHaveText('汇总分析结论')
  await expect(page.getByTestId('analysis-plan-next-hint')).toHaveText('全部步骤已完成。')
  await expect(page.getByTestId('analysis-plan-step-1')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-2')).toBeVisible()
})

test('移动端默认摘要并可展开步骤列表', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })

  // Trigger WebSocket events directly
  await page.evaluate(() => {
    const ws = (window as unknown as { __mockWsInstance?: WebSocket }).__mockWsInstance
    if (ws && ws.onmessage) {
      ws.onmessage(new MessageEvent('message', {
        data: JSON.stringify({
          type: 'analysis_plan',
          turn_id: 'test-turn-mobile',
          data: {
            raw_text: '1. 加载数据\n2. 分析结果',
            steps: [
              { id: 1, title: '加载数据', tool_hint: 'tool1', status: 'done' },
              { id: 2, title: '分析结果', tool_hint: 'tool2', status: 'in_progress' },
            ],
          },
        }),
      }))
    }
  })

  await page.waitForTimeout(300)

  await expect(page.getByTestId('analysis-plan-header')).toBeVisible({ timeout: 10000 })
  await expect(page.getByTestId('analysis-plan-toggle')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-list')).toBeHidden()

  // Close workspace panel first on mobile by clicking outside
  await page.mouse.click(10, 10)
  await page.waitForTimeout(200)

  await page.getByTestId('analysis-plan-toggle').click()
  await expect(page.getByTestId('analysis-plan-step-list')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-1')).toBeVisible()
})
