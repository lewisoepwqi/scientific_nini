/**
 * 会话生命周期事件（创建/删除/重命名/刷新）。
 * 提供类型化的单点 emit/listen，避免散落字符串与 detail 结构不一致。
 */

export const SESSIONS_CHANGED_EVENT = 'nini:sessions-changed'

export type SessionLifecycleReason = 'create' | 'delete' | 'rename' | 'refresh'

export interface SessionLifecyclePayload {
  reason: SessionLifecycleReason
  sessionId?: string
  title?: string
}

export function emitSessionsChanged(payload: SessionLifecyclePayload): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<SessionLifecyclePayload>(SESSIONS_CHANGED_EVENT, {
      detail: payload,
    }),
  )
}

export function onSessionsChanged(
  handler: (payload: SessionLifecyclePayload) => void,
): () => void {
  const listener: EventListener = (event) => {
    const customEvent = event as CustomEvent<SessionLifecyclePayload>
    const detail = customEvent.detail
    if (!detail || !detail.reason) return
    handler(detail)
  }
  window.addEventListener(SESSIONS_CHANGED_EVENT, listener)
  return () => window.removeEventListener(SESSIONS_CHANGED_EVENT, listener)
}

