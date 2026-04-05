import { describe, expect, it } from 'vitest'

import { ensureBrowserGlobalAlias } from './browserCompat'

describe('browserCompat', () => {
  it('should create global alias for browser-like target', () => {
    const target: { global?: unknown; marker: string } = { marker: 'demo' }

    ensureBrowserGlobalAlias(target)

    expect(target.global).toBe(target)
  })

  it('should keep existing global alias unchanged', () => {
    const existing = { stable: true }
    const target: { global?: unknown } = { global: existing }

    ensureBrowserGlobalAlias(target)

    expect(target.global).toBe(existing)
  })
})
