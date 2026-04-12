/**
 * 自定义 Plotly 精简包。
 *
 * 仅注册当前前端会实际渲染的科研图表 trace，避免把 image 等
 * 需要 Node polyfill 的依赖带入 Vite 预构建流程。
 */
import PlotlyCore from 'plotly.js/lib/core'
import bar from 'plotly.js/lib/bar'
import box from 'plotly.js/lib/box'
import heatmap from 'plotly.js/lib/heatmap'
import histogram from 'plotly.js/lib/histogram'
import pie from 'plotly.js/lib/pie'
import scatter from 'plotly.js/lib/scatter'
import violin from 'plotly.js/lib/violin'

PlotlyCore.register([scatter, bar, box, violin, histogram, heatmap, pie] as never[])

export default PlotlyCore
