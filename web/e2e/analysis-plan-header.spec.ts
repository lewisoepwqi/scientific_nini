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
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
        }, 0)
      }

      send(raw: string) {
        const payload = JSON.parse(raw) as Record<string, unknown>
        if (payload.type === 'ping') {
          this.emit({ type: 'pong' })
          return
        }

        if (payload.type === 'chat') {
          setTimeout(() => {
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
          }, 0)
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
})

test('顶部分析进度头部可见并随事件更新', async ({ page }) => {
  const input = page.getByPlaceholder('描述你的分析需求...')
  await input.fill('请执行分析计划')
  await input.press('Enter')

  await expect(page.getByTestId('analysis-plan-header')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-index')).toHaveText('Step 2/2')
  await expect(page.getByTestId('analysis-plan-current-title')).toHaveText('汇总分析结论')
  await expect(page.getByTestId('analysis-plan-next-hint')).toHaveText('全部步骤已完成。')
  await expect(page.getByTestId('analysis-plan-step-1')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-2')).toBeVisible()
})

test('移动端默认摘要并可展开步骤列表', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })

  const input = page.getByPlaceholder('描述你的分析需求...')
  await input.fill('移动端计划展示')
  await input.press('Enter')

  await expect(page.getByTestId('analysis-plan-header')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-toggle')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-list')).toBeHidden()

  await page.getByTestId('analysis-plan-toggle').click()
  await expect(page.getByTestId('analysis-plan-step-list')).toBeVisible()
  await expect(page.getByTestId('analysis-plan-step-1')).toBeVisible()
})
