/**
 * Plotly 图表渲染组件。
 */
import createPlotlyComponent from 'react-plotly.js/factory'
import type * as Plotly from 'plotly.js'
import React from 'react'
import PlotlyRuntime from '../lib/plotly'

const Plot = createPlotlyComponent(PlotlyRuntime)

import { isRecord } from '../store/utils'
import { CHART_COLORS, getPlotlyLayout } from '../utils/plotlyTheme'
import type { ThemeAxis } from '../utils/plotlyTheme'

import type { ChartDataPayload } from '../store/types'

interface Props {
 chartData: ChartDataPayload | unknown
}
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

function isDarkMode(): boolean {
 if (typeof document === 'undefined') return false
 return document.documentElement.classList.contains('dark')
}

function buildAxis(axis: unknown, themeAxis: ThemeAxis): Partial<Plotly.LayoutAxis> {
 const base = isRecord(axis) ? (axis as Partial<Plotly.LayoutAxis>) : {}
 return {
 showline: true,
 linecolor: themeAxis.linecolor,
 linewidth: 1,
 ticks: 'outside',
 tickcolor: themeAxis.tickcolor,
 gridcolor: themeAxis.gridcolor,
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

const ChartViewer = React.memo(function ChartViewer({ chartData }: Props) {
 const containerRef = React.useRef<HTMLDivElement | null>(null)
 const [containerWidth, setContainerWidth] = React.useState(0)

 React.useEffect(() => {
 const node = containerRef.current
 if (!node) return

 const updateWidth = () => {
 const nextWidth = Math.round(node.getBoundingClientRect().width)
 setContainerWidth((prev) => (prev === nextWidth ? prev : nextWidth))
 }

 updateWidth()

 if (typeof ResizeObserver !== 'undefined') {
 const observer = new ResizeObserver(() => {
 updateWidth()
 })
 observer.observe(node)
 return () => observer.disconnect()
 }

 window.addEventListener('resize', updateWidth)
 return () => window.removeEventListener('resize', updateWidth)
 }, [])

 const normalized = normalizeChartData(chartData)
 if (!normalized) {
 return <div className="text-xs text-[var(--error)]">图表数据格式无效</div>
 }

 const data = Array.isArray(normalized.data) ? (normalized.data as Plotly.Data[]) : []
 const baseLayout = isRecord(normalized.layout) ? (normalized.layout as Partial<Plotly.Layout>) : {}
 const baseConfig = isRecord(normalized.config) ? (normalized.config as Partial<Plotly.Config>) : {}

 if (data.length === 0) {
 return <div className="text-xs text-[var(--error)]">图表数据为空</div>
 }

 const isDark = isDarkMode()
 const theme = getPlotlyLayout(isDark)
 const baseFont = isRecord(baseLayout.font) ? (baseLayout.font as Partial<Plotly.Font>) : {}

 const layout: Partial<Plotly.Layout> = {
 ...baseLayout,
 ...theme,
 autosize: true,
 width: containerWidth > 0 ? containerWidth - 16 : undefined,
 height: typeof baseLayout.height === 'number' ? baseLayout.height : 420,
 colorway: Array.isArray(baseLayout.colorway) && baseLayout.colorway.length > 0
 ? baseLayout.colorway
 : CHART_COLORS,
 paper_bgcolor: baseLayout.paper_bgcolor ?? theme.paper_bgcolor,
 plot_bgcolor: baseLayout.plot_bgcolor ?? theme.plot_bgcolor,
 font: {
 ...theme.font,
 ...baseFont,
 family: withChineseFallback(typeof baseFont.family === 'string' ? baseFont.family : ''),
 },
 margin: isRecord(baseLayout.margin)
 ? ({ l: 56, r: 24, t: 56, b: 48, ...(baseLayout.margin as Partial<Plotly.Margin>) })
 : { l: 56, r: 24, t: 56, b: 48 },
 xaxis: buildAxis(baseLayout.xaxis, theme.xaxis as ThemeAxis),
 yaxis: buildAxis(baseLayout.yaxis, theme.yaxis as ThemeAxis),
 }

 const config: Partial<Plotly.Config> = {
 responsive: true,
 displaylogo: false,
 ...baseConfig,
 }

 return (
 <div
 ref={containerRef}
 className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] p-2 mt-2"
 style={{ minHeight: '420px' }}
 >
 <Plot
 data={data}
 layout={layout}
 config={config}
 revision={containerWidth}
 style={{ width: '100%', height: '100%', minHeight: '400px' }}
 useResizeHandler
 />
 </div>
 )
})

export default ChartViewer
