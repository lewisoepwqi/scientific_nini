import { describe, expect, it } from 'vitest'

import { buildPlotlyFetchUrl, normalizePlotlyPayload } from './PlotlyFromUrl'

describe('PlotlyFromUrl helpers', () => {
  it('should add raw=1 and download=1 for workspace plotly json url', () => {
    const url = '/api/workspace/sess-1/files/artifacts/chart.plotly.json'
    const result = buildPlotlyFetchUrl(url)

    expect(result).toContain('raw=1')
    expect(result).toContain('download=1')
  })

  it('should normalize workspace file api response envelope to plotly payload', () => {
    const payload = {
      success: true,
      data: {
        path: 'artifacts/chart.plotly.json',
        content: '{"data":[{"type":"scatter","x":[1],"y":[2]}],"layout":{"title":"demo"}}',
      },
    }

    const normalized = normalizePlotlyPayload(payload) as { data: unknown[]; layout: unknown }
    expect(Array.isArray(normalized.data)).toBe(true)
    expect(normalized.data.length).toBe(1)
    expect(normalized.layout).toBeDefined()
  })
})

