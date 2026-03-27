/**
 * 响应式布局 hooks —— 基于 matchMedia 的轻量断点检测。
 */
import { useSyncExternalStore } from 'react'

const mdQuery = '(min-width: 768px)'

function subscribeMd(callback: () => void) {
  const mql = window.matchMedia(mdQuery)
  mql.addEventListener('change', callback)
  return () => mql.removeEventListener('change', callback)
}

function getIsDesktop() {
  return window.matchMedia(mdQuery).matches
}

/**
 * 返回当前视口是否 ≥ md（768px）。
 * 使用 useSyncExternalStore 保证 SSR 一致性（getServerSnapshot 返回 false）。
 */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribeMd,
    getIsDesktop,
    () => false, // 服务端快照
  )
}
