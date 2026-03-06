/**
 * 从 .plotly.json URL 拉取图表并渲染。
 */
import { useEffect, useMemo, useState } from 'react'
import { Suspense, lazy } from 'react'

const ChartViewer = lazy(() => import('./ChartViewer'))

interface Props {
  url: string
  alt?: string
}

export function buildPlotlyFetchUrl(url: string): string {
  const clean = url.split('#')[0]?.split('?')[0]?.toLowerCase() || ''
  if (!clean.endsWith('.plotly.json')) {
    return url
  }
  try {
    const parsed = new URL(url, window.location.origin)
    const isWorkspaceFileApi =
      parsed.pathname.includes('/api/workspace/') && parsed.pathname.includes('/files/')

    if (!parsed.searchParams.has('raw')) {
      parsed.searchParams.set('raw', '1')
    }
    if (isWorkspaceFileApi && !parsed.searchParams.has('download')) {
      // /api/workspace/{sid}/files/{path} 默认返回 JSON 包装，download=1 才返回原始文件内容。
      parsed.searchParams.set('download', '1')
    }
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return parsed.toString()
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    const separator = url.includes('?') ? '&' : '?'
    return `${url}${separator}raw=1`
  }
}

export function normalizePlotlyPayload(payload: unknown): unknown {
  if (typeof payload !== 'object' || payload === null) {
    return payload
  }
  const record = payload as Record<string, unknown>

  if (
    typeof record.success === 'boolean' &&
    typeof record.data === 'object' &&
    record.data !== null &&
    'content' in (record.data as Record<string, unknown>)
  ) {
    const content = (record.data as Record<string, unknown>).content
    if (typeof content === 'string') {
      try {
        return JSON.parse(content)
      } catch {
        return payload
      }
    }
    if (typeof content === 'object' && content !== null) {
      return content
    }
  }

  return payload
}

export default function PlotlyFromUrl({ url, alt }: Props) {
  const [chartData, setChartData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isValidUrl = useMemo(() => {
    return typeof url === 'string' && url.trim().length > 0
  }, [url])

  useEffect(() => {
    if (!isValidUrl) {
      setLoading(false)
      setError('图表地址无效')
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)

    const fetchUrl = buildPlotlyFetchUrl(url)
    fetch(fetchUrl, { signal: controller.signal })
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`)
        }
        return resp.json()
      })
      .then((payload) => {
        setChartData(normalizePlotlyPayload(payload))
      })
      .catch((err: unknown) => {
        if ((err as { name?: string }).name === 'AbortError') {
          return
        }
        setError('图表加载失败')
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [isValidUrl, url])

  if (loading) {
    return <div className="text-xs text-gray-500 mt-2">图表加载中...</div>
  }

  if (error) {
    return (
      <div className="text-xs text-red-500 mt-2">
        {error}
        {alt ? `：${alt}` : ''}
      </div>
    )
  }

  return (
    <Suspense fallback={<div className="text-xs text-gray-500 mt-2">图表组件加载中...</div>}>
      <ChartViewer chartData={chartData} />
    </Suspense>
  )
}
