/**
 * 浏览器兼容层：为仍依赖 Node 风格 global 的第三方库补齐别名。
 * 典型场景是 Plotly 依赖链中的 has-hover，会在浏览器里直接读取 global.matchMedia。
 */
export interface GlobalAliasTarget {
  global?: unknown
}

export function ensureBrowserGlobalAlias(target: GlobalAliasTarget = globalThis): void {
  if (typeof target.global !== 'undefined') {
    return
  }

  Object.defineProperty(target, 'global', {
    value: target,
    configurable: true,
    writable: true,
  })
}
