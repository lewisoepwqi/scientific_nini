import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    ;(window as Record<string, unknown>).__batchDownloadBodies = []
    ;(window as Record<string, unknown>).__downloads = []

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
                  id: 'sess-e2e',
                  title: 'E2E Session',
                  message_count: 0,
                  source: 'disk',
                },
              ],
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
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
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/messages') {
          return new Response(
            JSON.stringify({
              success: true,
              data: { messages: [] },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/datasets') {
          return new Response(
            JSON.stringify({
              success: true,
              data: { session_id: 'sess-e2e', datasets: [] },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/workspace/executions') {
          return new Response(
            JSON.stringify({
              success: true,
              data: { session_id: 'sess-e2e', executions: [] },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/workspace/folders') {
          return new Response(
            JSON.stringify({
              success: true,
              data: { session_id: 'sess-e2e', folders: [] },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/workspace/files') {
          return new Response(
            JSON.stringify({
              success: true,
              data: {
                session_id: 'sess-e2e',
                files: [
                  {
                    id: 'art-1',
                    name: 'chart_a.png',
                    kind: 'artifact',
                    size: 2048,
                    created_at: '2026-02-10T00:00:00Z',
                    download_url: '/api/artifacts/sess-e2e/chart_a.png',
                    meta: { type: 'chart', format: 'png' },
                  },
                  {
                    id: 'art-2',
                    name: 'report_b.md',
                    kind: 'artifact',
                    size: 4096,
                    created_at: '2026-02-10T00:00:01Z',
                    download_url: '/api/artifacts/sess-e2e/report_b.md',
                    meta: { type: 'report', format: 'md' },
                  },
                ],
              },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/workspace/files/art-1/preview') {
          return new Response(
            JSON.stringify({
              success: true,
              data: {
                id: 'art-1',
                kind: 'artifact',
                preview_type: 'text',
                name: 'chart_a.png',
                ext: 'txt',
                content: 'preview-content-art-1',
                total_lines: 1,
                preview_lines: 1,
              },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/workspace/files/art-2/preview') {
          return new Response(
            JSON.stringify({
              success: true,
              data: {
                id: 'art-2',
                kind: 'artifact',
                preview_type: 'text',
                name: 'report_b.md',
                ext: 'md',
                content: '# report_b',
                total_lines: 1,
                preview_lines: 1,
              },
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        if (url === '/api/sessions/sess-e2e/workspace/batch-download' && init?.method === 'POST') {
          const rawBody = typeof init.body === 'string' ? init.body : '{}'
          try {
            const parsed = JSON.parse(rawBody) as Record<string, unknown>
            const calls = (window as Record<string, unknown>).__batchDownloadBodies as Array<Record<string, unknown>>
            calls.push(parsed)
          } catch {
            // 忽略解析错误，测试用例中会断言请求结构
          }
          return new Response('mock-zip-content', {
            status: 200,
            headers: {
              'Content-Type': 'application/zip',
              'Content-Disposition': 'attachment; filename="mock_workspace_bundle.zip"',
            },
          })
        }

        return new Response(JSON.stringify({ success: true, data: {} }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return originalFetch(input, init)
    }

    const originalClick = HTMLAnchorElement.prototype.click
    HTMLAnchorElement.prototype.click = function () {
      const downloads = (window as Record<string, unknown>).__downloads as Array<Record<string, unknown>>
      downloads.push({
        href: this.href,
        download: this.download,
      })
      return originalClick.call(this)
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
        let payload: Record<string, unknown> | null = null
        try {
          payload = JSON.parse(raw) as Record<string, unknown>
        } catch {
          payload = { type: 'raw', raw }
        }
        if (payload.type === 'ping') {
          this.onmessage?.(
            new MessageEvent('message', {
              data: JSON.stringify({ type: 'pong' }),
            }),
          )
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }
    }

    ;(window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      MockWebSocket as unknown as typeof WebSocket
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')
})

test('工作区画廊支持多选并触发 ZIP 批量下载', async ({ page }) => {
  await page.getByTitle('打开工作区').click()

  await page.locator('button[title="切换到目录树视图"]:visible').click()
  await page.locator('button[title="切换到画廊视图"]:visible').click()

  const cardA = page.locator('div.relative.rounded-lg.border').filter({ hasText: 'chart_a.png' }).first()
  const cardB = page.locator('div.relative.rounded-lg.border').filter({ hasText: 'report_b.md' }).first()

  await cardA.locator('button').first().click()
  await cardB.locator('button').first().click()

  await expect(page.getByText('已选 2 个')).toBeVisible()
  await page.getByRole('button', { name: '批量下载' }).click()

  await expect.poll(async () => {
    return await page.evaluate(() => {
      const calls = (window as Record<string, unknown>).__batchDownloadBodies as Array<Record<string, unknown>>
      return calls.length
    })
  }).toBeGreaterThan(0)

  const requestFileIds = await page.evaluate(() => {
    const calls = (window as Record<string, unknown>).__batchDownloadBodies as Array<Record<string, unknown>>
    const last = calls[calls.length - 1] as Record<string, unknown>
    return Array.isArray(last.file_ids) ? (last.file_ids as string[]) : []
  })
  expect(new Set(requestFileIds)).toEqual(new Set(['art-1', 'art-2']))

  const downloadName = await page.evaluate(() => {
    const downloads = (window as Record<string, unknown>).__downloads as Array<Record<string, unknown>>
    const last = downloads[downloads.length - 1] as Record<string, unknown> | undefined
    return (last?.download as string | undefined) || ''
  })
  expect(downloadName).toBe('mock_workspace_bundle.zip')

  await expect(page.getByText('已选 2 个')).toHaveCount(0)
})

test('文件预览以动态标签页打开并可关闭', async ({ page }) => {
  await page.getByTitle('打开工作区').click()
  await page.getByText('chart_a.png').first().click()

  const previewTab = page.locator('button:visible').filter({ hasText: 'chart_a.png' }).first()
  await expect(previewTab).toBeVisible()
  await expect(page.getByText('preview-content-art-1').first()).toBeVisible()

  const closeTab = page.locator('[title="关闭标签"]:visible').first()
  await closeTab.click()

  await expect(previewTab).toHaveCount(0)
  await expect(page.getByText('preview-content-art-1').first()).toHaveCount(0)
})
