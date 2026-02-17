/**
 * 轻量埋点出口：先通过自定义事件暴露，后续可由宿主统一收集。
 */

export type PlanTelemetryEventName =
  | 'plan_header_rendered'
  | 'plan_step_changed'
  | 'plan_expand_toggled'
  | 'plan_blocked_exposed'

export function emitPlanTelemetry(
  event: PlanTelemetryEventName,
  payload: Record<string, unknown> = {},
): void {
  if (typeof window === 'undefined') return

  const detail = {
    event,
    payload,
    ts: Date.now(),
  }

  window.dispatchEvent(new CustomEvent('nini:telemetry', { detail }))

  if (import.meta.env.DEV) {
    // 开发期保留可观测输出，便于联调验证。
    console.debug('[telemetry]', detail)
  }
}
