/**
 * Plotly 图表渲染组件。
 */
import Plot from 'react-plotly.js'
import type * as Plotly from 'plotly.js'

interface Props {
  chartData: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

const SCIENTIFIC_COLORWAY = ['#1B3A57', '#2C7FB8', '#4DAF7C', '#D98E04', '#C03D3E', '#8A63D2', '#5F7D95', '#A5A58D']
const CJK_FONT_FAMILY = 'Noto Sans CJK SC, Source Han Sans SC, Microsoft YaHei, PingFang SC, Hiragino Sans GB, WenQuanYi Micro Hei, SimHei, Arial Unicode MS, Helvetica Neue, Arial, sans-serif'

function withChineseFallback(family: string): string {
  const trimmed = family.trim()
  if (!trimmed) return CJK_FONT_FAMILY
  const lower = trimmed.toLowerCase()
  const hasCjkFont = [
    'noto sans cjk',
    'source han',
    'microsoft yahei',
    'pingfang',
    'hiragino',
    'wenquanyi',
    'simhei',
    'heiti',
    'arial unicode',
  ].some((keyword) => lower.includes(keyword))
  return hasCjkFont ? trimmed : `${trimmed}, ${CJK_FONT_FAMILY}`
}

function buildAxis(axis: unknown): Partial<Plotly.LayoutAxis> {
  const base = isRecord(axis) ? (axis as Partial<Plotly.LayoutAxis>) : {}
  return {
    showline: true,
    linecolor: '#9CA3AF',
    linewidth: 1,
    ticks: 'outside',
    tickcolor: '#9CA3AF',
    gridcolor: '#E5E7EB',
    zeroline: false,
    automargin: true,
    ...base,
  }
}

function normalizeChartData(chartData: unknown): Record<string, unknown> | null {
  if (!isRecord(chartData)) return null
  if (isRecord(chartData.figure)) {
    const figure = chartData.figure as Record<string, unknown>
    const merged: Record<string, unknown> = { ...figure }
    if (!('config' in merged) && isRecord(chartData.config)) {
      merged.config = chartData.config
    }
    if (typeof chartData.schema_version === 'string') {
      merged.schema_version = chartData.schema_version
    }
    return merged
  }
  return chartData
}

export default function ChartViewer({ chartData }: Props) {
  const normalized = normalizeChartData(chartData)
  if (!normalized) {
    return <div className="text-xs text-red-500">图表数据格式无效</div>
  }

  const data = Array.isArray(normalized.data) ? (normalized.data as Plotly.Data[]) : []
  const baseLayout = isRecord(normalized.layout) ? (normalized.layout as Partial<Plotly.Layout>) : {}
  const baseConfig = isRecord(normalized.config) ? (normalized.config as Partial<Plotly.Config>) : {}

  if (data.length === 0) {
    return <div className="text-xs text-red-500">图表数据为空</div>
  }

  const baseFont = isRecord(baseLayout.font) ? (baseLayout.font as Partial<Plotly.Font>) : {}

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    autosize: true,
    height: typeof baseLayout.height === 'number' ? baseLayout.height : 420,
    colorway: Array.isArray(baseLayout.colorway) && baseLayout.colorway.length > 0
      ? baseLayout.colorway
      : SCIENTIFIC_COLORWAY,
    paper_bgcolor: baseLayout.paper_bgcolor ?? '#FFFFFF',
    plot_bgcolor: baseLayout.plot_bgcolor ?? '#FFFFFF',
    font: {
      ...baseFont,
      family: withChineseFallback(typeof baseFont.family === 'string' ? baseFont.family : ''),
      size: typeof baseFont.size === 'number' ? baseFont.size : 12,
      color: typeof baseFont.color === 'string' ? baseFont.color : '#111827',
    },
    margin: isRecord(baseLayout.margin)
      ? ({ l: 56, r: 24, t: 56, b: 48, ...(baseLayout.margin as Partial<Plotly.Margin>) })
      : { l: 56, r: 24, t: 56, b: 48 },
    xaxis: buildAxis(baseLayout.xaxis),
    yaxis: buildAxis(baseLayout.yaxis),
  }

  const config: Partial<Plotly.Config> = {
    responsive: true,
    displaylogo: false,
    ...baseConfig,
  }

  return (
    <div 
      className="rounded-xl border border-gray-200 bg-white p-2 mt-2"
      style={{ minHeight: '420px' }}
    >
      <Plot
        data={data}
        layout={layout}
        config={config}
        style={{ width: '100%', height: '100%', minHeight: '400px' }}
        useResizeHandler
      />
    </div>
  )
}
