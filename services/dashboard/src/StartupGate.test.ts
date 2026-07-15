import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./StartupGate.vue', import.meta.url), 'utf8')

describe('startup gate password contract', () => {
  it('does not invite browser credential autofill before administrator input', () => {
    expect(source).toContain('autocomplete="new-password"')
    expect(source).not.toMatch(/(?:^|\s)value=["'][^"']*(?:miniogas|password)[^"']*["']/i)
  })
})
