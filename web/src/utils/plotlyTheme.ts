/**
 * Plotly 图表主题配置，跟随暗色/亮色模式动态切换。
 */

export const CHART_COLORS = [
  '#5E6AD2', // accent blue-purple
  '#4D9A6A', // success green
  '#C4874A', // warning orange
  '#C45A5A', // error red
  '#7C3AED', // purple
  '#0284C7', // sky blue
]

export interface ThemeAxis {
  gridcolor: string
  linecolor: string
  tickcolor: string
  zerolinecolor: string
}

export interface PlotlyTheme {
  paper_bgcolor: string
  plot_bgcolor: string
  font: { color: string; size: number }
  xaxis: ThemeAxis
  yaxis: ThemeAxis
}

export function getPlotlyLayout(isDark: boolean): PlotlyTheme {
  return {
    paper_bgcolor: isDark ? '#141415' : '#FFFFFF',
    plot_bgcolor:  isDark ? '#141415' : '#FFFFFF',
    font: {
      color:  isDark ? '#8A8A8F' : '#6A6A6F',
      size: 12,
    },
    xaxis: {
      gridcolor:    isDark ? '#2A2A2C' : '#E8E8EA',
      linecolor:    isDark ? '#2A2A2C' : '#DCDCE0',
      tickcolor:    isDark ? '#5A5A5F' : '#9A9AA0',
      zerolinecolor: isDark ? '#3A3A3D' : '#C8C8CE',
    },
    yaxis: {
      gridcolor:    isDark ? '#2A2A2C' : '#E8E8EA',
      linecolor:    isDark ? '#2A2A2C' : '#DCDCE0',
      tickcolor:    isDark ? '#5A5A5F' : '#9A9AA0',
      zerolinecolor: isDark ? '#3A3A3D' : '#C8C8CE',
    },
  }
}
