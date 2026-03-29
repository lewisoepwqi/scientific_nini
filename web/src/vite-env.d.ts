/// <reference types="vite/client" />

// Plotly.js partial bundle — 没有独立类型声明
declare module 'plotly.js/lib/index-basic' {
  import Plotly from 'plotly.js'
  export default Plotly
}

declare module 'react-plotly.js/factory' {
  import type { ComponentType } from 'react'
  interface PlotParams {
    data: unknown[]
    layout?: Record<string, unknown>
    config?: Record<string, unknown>
    revision?: number
    style?: React.CSSProperties
    useResizeHandler?: boolean
    [key: string]: unknown
  }
  export default function createPlotlyComponent(
    plotly: unknown
  ): ComponentType<PlotParams>
}
