/**
 * 前端特性开关。
 * 支持优先级：URL 参数 > localStorage > Vite 环境变量 > 默认值。
 */

const ANALYSIS_PLAN_HEADER_V2_KEY = 'nini_feature_analysis_plan_header_v2'

function parseBooleanFlag(raw: string | null): boolean | null {
  if (raw == null) return null
  const normalized = raw.trim().toLowerCase()
  if (['1', 'true', 'on', 'yes'].includes(normalized)) return true
  if (['0', 'false', 'off', 'no'].includes(normalized)) return false
  return null
}

function getDefaultAnalysisPlanHeaderV2(): boolean {
  const fromEnv = import.meta.env.VITE_ENABLE_ANALYSIS_PLAN_HEADER_V2
  const parsed = parseBooleanFlag(typeof fromEnv === 'string' ? fromEnv : null)
  return parsed ?? true
}

export function isAnalysisPlanHeaderV2Enabled(): boolean {
  if (typeof window === 'undefined') return getDefaultAnalysisPlanHeaderV2()

  const fromQuery = parseBooleanFlag(
    new URLSearchParams(window.location.search).get('analysisPlanHeaderV2'),
  )
  if (fromQuery != null) return fromQuery

  const fromStorage = parseBooleanFlag(window.localStorage.getItem(ANALYSIS_PLAN_HEADER_V2_KEY))
  if (fromStorage != null) return fromStorage

  return getDefaultAnalysisPlanHeaderV2()
}

export { ANALYSIS_PLAN_HEADER_V2_KEY }
