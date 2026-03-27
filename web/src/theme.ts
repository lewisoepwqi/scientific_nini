/**
 * 暗色模式管理工具 —— 基于 Tailwind darkMode: 'class' 策略。
 *
 * 在 <html> 元素上切换 `dark` class 来控制主题。
 * 持久化到 localStorage，支持 'light' | 'dark' | 'system' 三种模式。
 */

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'nini-theme'

function getSystemPreference(): 'light' | 'dark' {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(mode: ThemeMode): void {
  if (typeof document === 'undefined') return
  const resolved = mode === 'system' ? getSystemPreference() : mode
  if (resolved === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

export function getStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'system'
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // localStorage 不可用
  }
  return 'system'
}

export function setTheme(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // localStorage 不可用
  }
  applyTheme(mode)
}

export function initTheme(): () => void {
  const mode = getStoredTheme()
  applyTheme(mode)

  // 监听系统主题变化（当用户选择 system 模式时自动响应）
  const mql = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => {
    if (getStoredTheme() === 'system') {
      applyTheme('system')
    }
  }
  mql.addEventListener('change', handler)
  return () => mql.removeEventListener('change', handler)
}

/** 返回当前模式解析后的实际主题 */
export function getResolvedTheme(): 'light' | 'dark' {
  const mode = getStoredTheme()
  return mode === 'system' ? getSystemPreference() : mode
}
