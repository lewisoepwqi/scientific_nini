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

export default function ChartViewer({ chartData }: Props) {
  if (!isRecord(chartData)) {
    return <div className="text-xs text-red-500">图表数据格式无效</div>
  }

  const data = Array.isArray(chartData.data) ? (chartData.data as Plotly.Data[]) : []
  const baseLayout = isRecord(chartData.layout) ? (chartData.layout as Partial<Plotly.Layout>) : {}
  const baseConfig = isRecord(chartData.config) ? (chartData.config as Partial<Plotly.Config>) : {}

  if (data.length === 0) {
    return <div className="text-xs text-red-500">图表数据为空</div>
  }

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    autosize: true,
    height: typeof baseLayout.height === 'number' ? baseLayout.height : 420,
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
