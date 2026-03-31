/**
 * 响应式布局 hooks —— 基于 matchMedia 的轻量断点检测。
 *
 * - md (768px): 平板以上覆盖式侧边栏
 * - lg (1024px): 全三栏 inline 布局
 *
 * useIsDesktop() → ≥768px（非移动端，含平板）
 * useIsWide()    → ≥1024px（桌面端，inline 三栏）
 */
import { useSyncExternalStore } from 'react'

const mdQuery = '(min-width: 768px)'
const lgQuery = '(min-width: 1024px)'

function subscribeMd(callback: () => void) {
  const mql = window.matchMedia(mdQuery)
  mql.addEventListener('change', callback)
  return () => mql.removeEventListener('change', callback)
}

function subscribeLg(callback: () => void) {
  const mql = window.matchMedia(lgQuery)
  mql.addEventListener('change', callback)
  return () => mql.removeEventListener('change', callback)
}

function getIsDesktop() {
  return window.matchMedia(mdQuery).matches
}

function getIsWide() {
  return window.matchMedia(lgQuery).matches
}

/**
 * 返回当前视口是否 ≥ md（768px）。
 * 平板和桌面端均返回 true。
 */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(subscribeMd, getIsDesktop, () => false)
}

/**
 * 返回当前视口是否 ≥ lg（1024px）。
 * 仅桌面端返回 true，平板（768-1023px）返回 false。
 */
export function useIsWide(): boolean {
  return useSyncExternalStore(subscribeLg, getIsWide, () => false)
}
