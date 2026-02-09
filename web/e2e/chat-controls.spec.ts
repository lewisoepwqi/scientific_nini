import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    ;(window as Record<string, unknown>).__wsSent = []
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
      private slowTimer: ReturnType<typeof setInterval> | null = null
      private slowIndex = 0

      constructor(url: string) {
        this.url = url
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
        }, 0)
      }

      send(raw: string) {
        let payload: Record<string, unknown> | null = null
        try {
          payload = JSON.parse(raw) as Record<string, unknown>
        } catch {
          payload = { type: 'raw', raw }
        }

        const sent = (window as Record<string, unknown>).__wsSent as Array<Record<string, unknown>>
        sent.push(payload)

        const messageType = payload.type
        if (messageType === 'ping') {
          this.emit({ type: 'pong' })
          return
        }

        if (messageType === 'chat') {
          this.defer(() => {
            this.emit({ type: 'session', data: { session_id: 'sess-e2e' } })
            this.emit({ type: 'iteration_start', turn_id: 'turn-chat' })

            const content = String(payload.content ?? '')
            if (content.includes('slow')) {
              this.startSlowStream()
            } else if (content.includes('chart')) {
              this.emit({ type: 'text', data: '图表说明文本' })
              this.emit({
                type: 'chart',
                data: {
                  data: [
                    {
                      type: 'bar',
                      x: ['A', 'B'],
                      y: [1, 3],
                    },
                  ],
                  layout: {
                    title: 'E2E Chart',
                  },
                },
              })
              this.emit({ type: 'done' })
            } else {
              this.emit({ type: 'text', data: '快速回答内容' })
              this.emit({ type: 'done' })
            }
          })
          return
        }

        if (messageType === 'stop') {
          this.stopSlowStream()
          this.emit({ type: 'stopped', data: '已停止当前请求' })
          return
        }

        if (messageType === 'retry') {
          this.stopSlowStream()
          this.emit({ type: 'session', data: { session_id: 'sess-e2e' } })
          this.emit({ type: 'iteration_start', turn_id: 'turn-retry' })
          this.emit({ type: 'text', data: '重试后的新回答' })
          this.emit({ type: 'done' })
        }
      }

      close() {
        this.stopSlowStream()
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }

      private startSlowStream() {
        const chunks = ['旧回答片段-1', '旧回答片段-2', '旧回答片段-3']
        this.stopSlowStream()
        this.slowTimer = setInterval(() => {
          const chunk = chunks[this.slowIndex % chunks.length]
          this.slowIndex += 1
          this.emit({ type: 'text', data: chunk, turn_id: 'turn-chat' })
        }, 120)
      }

      private stopSlowStream() {
        if (this.slowTimer) {
          clearInterval(this.slowTimer)
          this.slowTimer = null
        }
      }

      private emit(payload: Record<string, unknown>) {
        this.onmessage?.(
          new MessageEvent('message', {
            data: JSON.stringify(payload),
          }),
        )
      }

      private defer(fn: () => void) {
        setTimeout(fn, 0)
      }
    }

    ;(window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      MockWebSocket as unknown as typeof WebSocket
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')
})

test('停止按钮可中断流式输出，重试确认后清空旧回答并重新生成', async ({ page }) => {
  const input = page.getByPlaceholder('描述你的分析需求...')
  await input.fill('slow e2e test')
  await input.press('Enter')

  await expect(page.getByTitle('停止生成')).toBeVisible()
  await expect(page.getByText('旧回答片段-1')).toBeVisible()

  await page.getByTitle('停止生成').click()
  await expect(page.getByTitle('停止生成')).toHaveCount(0)

  await page.evaluate(() => {
    window.confirm = () => true
  })
  await page.getByTitle('重试上一轮').click()

  await expect(page.getByText('旧回答片段-1')).toHaveCount(0)
  await expect(page.getByText('重试后的新回答')).toBeVisible()

  const sentTypes = await page.evaluate(() => {
    const sent = (window as Record<string, unknown>).__wsSent as Array<Record<string, unknown>>
    return sent.map((item) => item.type)
  })
  expect(sentTypes).toContain('stop')
  expect(sentTypes).toContain('retry')
})

test('重试二次确认取消时，不发送 retry 且保留旧回答', async ({ page }) => {
  const input = page.getByPlaceholder('描述你的分析需求...')
  await input.fill('quick e2e test')
  await input.press('Enter')

  await expect(page.getByText('快速回答内容')).toBeVisible()

  await page.evaluate(() => {
    window.confirm = () => false
  })

  const retryButton = page.getByTitle('重试上一轮')
  await expect(retryButton).toBeEnabled()

  const beforeRetryCount = await page.evaluate(() => {
    const sent = (window as Record<string, unknown>).__wsSent as Array<Record<string, unknown>>
    return sent.filter((item) => item.type === 'retry').length
  })

  await retryButton.click()

  const afterRetryCount = await page.evaluate(() => {
    const sent = (window as Record<string, unknown>).__wsSent as Array<Record<string, unknown>>
    return sent.filter((item) => item.type === 'retry').length
  })

  expect(afterRetryCount).toBe(beforeRetryCount)
  await expect(page.getByText('快速回答内容')).toBeVisible()
})

test('图表气泡应使用宽布局，不随文字长度收缩', async ({ page }) => {
  const input = page.getByPlaceholder('描述你的分析需求...')

  // 先生成普通文本消息（窄气泡）
  await input.fill('quick e2e test')
  await input.press('Enter')
  await expect(page.getByText('快速回答内容')).toBeVisible()

  // 再生成带图表消息（宽气泡）
  await input.fill('chart e2e test')
  await input.press('Enter')
  await expect(page.getByText('图表说明文本')).toBeVisible()
  await expect(page.locator('svg.main-svg').first()).toBeVisible()

  const widths = await page.evaluate(() => {
    const bubbles = Array.from(
      document.querySelectorAll<HTMLElement>('.bg-gray-100.text-gray-900'),
    )
    const textBubble = bubbles.find((el) => el.textContent?.includes('快速回答内容')) || null
    const chartSvg = document.querySelector<SVGElement>('svg.main-svg')
    const chartBubble = chartSvg?.closest<HTMLElement>('.bg-gray-100.text-gray-900') || null
    if (!textBubble || !chartBubble) {
      return { textWidth: 0, chartWidth: 0 }
    }
    return {
      textWidth: textBubble.getBoundingClientRect().width,
      chartWidth: chartBubble.getBoundingClientRect().width,
    }
  })

  expect(widths.textWidth).toBeGreaterThan(0)
  expect(widths.chartWidth).toBeGreaterThan(0)
  // 图表气泡应显著宽于普通文本气泡，避免仅微小浮动导致误判
  expect(widths.chartWidth).toBeGreaterThan(widths.textWidth + 80)
})
