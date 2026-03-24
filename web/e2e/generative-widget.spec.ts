import { expect, test } from '@playwright/test'

const widgetHtml = `
  <section class="widget-shell" style="padding: 20px;">
    <h2 id="widget-title" style="margin: 0 0 12px; color: var(--color-significant);">
      显著性提示
    </h2>
    <p id="widget-description" style="margin: 0 0 12px;">
      这里展示 generate_widget 的内嵌结果。
    </p>
    <div style="height: 320px; border-radius: 16px; background: rgba(15, 118, 110, 0.08);"></div>
    <p id="counter-value" style="margin: 12px 0 0;">counter:0</p>
    <div style="display: flex; gap: 10px; margin-top: 12px;">
      <button
        id="counter-button"
        onclick="window.__counter = (window.__counter || 0) + 1; document.getElementById('counter-value').textContent = 'counter:' + window.__counter;"
      >
        增加计数
      </button>
      <button id="prompt-button" onclick="window.sendPrompt('test')">发送 test</button>
    </div>
  </section>
`

test.beforeEach(async ({ page }) => {
  await page.addInitScript((html) => {
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
          return new Response(
            JSON.stringify({
              success: true,
              data: [
                {
                  id: 'sess-widget',
                  title: 'Widget Session',
                  message_count: 0,
                  source: 'disk',
                },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )
        }

        if (url === '/api/sessions/sess-widget/messages') {
          return new Response(
            JSON.stringify({
              success: true,
              data: { messages: [] },
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )
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
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )
        }

        if (url === '/api/models/providers') {
          return new Response(JSON.stringify({ success: true, data: [] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (
          url === '/api/skills' ||
          url === '/api/datasets/sess-widget' ||
          url === '/api/workspace/sess-widget/executions' ||
          url === '/api/workspace/sess-widget/folders'
        ) {
          return new Response(JSON.stringify({ success: true, data: [] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
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

      readyState = MockWebSocket.OPEN
      url: string
      onopen: ((event: Event) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor(url: string) {
        this.url = url
        ;(window as unknown as { __mockWsInstance?: MockWebSocket }).__mockWsInstance = this
        setTimeout(() => this.onopen?.(new Event('open')), 0)
      }

      send(raw: string) {
        let payload: Record<string, unknown>
        try {
          payload = JSON.parse(raw) as Record<string, unknown>
        } catch {
          payload = { type: 'raw', raw }
        }
        const sent = (window as Record<string, unknown>).__wsSent as Array<Record<string, unknown>>
        sent.push(payload)

        if (payload.type === 'ping') {
          this.emit({ type: 'pong' })
          return
        }

        if (payload.type === 'chat') {
          this.emit({ type: 'iteration_start', turn_id: 'turn-chat' })
          this.emit({ type: 'text', data: `收到：${String(payload.content ?? '')}` })
          this.emit({ type: 'done' })
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }

      emit(payload: Record<string, unknown>) {
        this.onmessage?.(
          new MessageEvent('message', {
            data: JSON.stringify(payload),
          }),
        )
      }
    }

    ;(window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      MockWebSocket as unknown as typeof WebSocket
    ;(window as Record<string, unknown>).__widgetHtml = html
  }, widgetHtml)
})

test('generate_widget 应在聊天中渲染并支持桥接交互', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  await page.evaluate(() => {
    const ws = (window as unknown as {
      __mockWsInstance?: { emit: (payload: Record<string, unknown>) => void }
      __widgetHtml?: string
    }).__mockWsInstance
    const html = (window as Record<string, unknown>).__widgetHtml as string
    ws?.emit({
      type: 'tool_result',
      session_id: 'sess-widget',
      tool_call_id: 'tool-widget-1',
      tool_name: 'generate_widget',
      data: {
        status: 'success',
        result: {
          success: true,
          data: {
            title: '统计摘要卡',
            html,
            description: '展示显著性与交互入口',
          },
        },
      },
    })
  })

  const iframe = page.locator('iframe[title="统计摘要卡"]')
  await expect(iframe).toBeVisible()
  await expect(page.getByText('统计摘要卡', { exact: true }).last()).toBeVisible()

  const height = await iframe.evaluate((node) => node.style.height)
  expect(parseInt(height, 10)).toBeGreaterThan(200)

  const frame = page.frameLocator('iframe[title="统计摘要卡"]')
  await expect(frame.locator('#widget-title')).toHaveText('显著性提示')

  const significantColor = await frame.locator('#widget-title').evaluate((node) => {
    return window.getComputedStyle(node).color
  })
  expect(significantColor).toBe('rgb(15, 118, 110)')

  await frame.locator('#counter-button').click()
  await expect(frame.locator('#counter-value')).toHaveText('counter:1')

  await page.evaluate(() => {
    const ws = (window as unknown as {
      __mockWsInstance?: { emit: (payload: Record<string, unknown>) => void }
    }).__mockWsInstance
    ws?.emit({
      type: 'text',
      session_id: 'sess-widget',
      turn_id: 'turn-rerender',
      data: '父组件重渲染测试',
    })
  })

  await expect(page.getByText('父组件重渲染测试')).toBeVisible()
  await expect(frame.locator('#counter-value')).toHaveText('counter:1')

  await frame.locator('#prompt-button').click()
  await expect(page.getByText('test', { exact: true }).last()).toBeVisible()
})
