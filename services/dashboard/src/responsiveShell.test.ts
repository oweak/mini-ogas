import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

describe('mobile shell contract', () => {
  it('uses a compact horizontally scrollable primary navigation', () => {
    expect(source).toContain('/* compact-mobile-navigation */')
    expect(source).toMatch(/\.sidebar\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden/s)
    expect(source).toMatch(/\.nav-list\s*\{[^}]*display:\s*flex[^}]*overflow-x:\s*auto/s)
    expect(source).toMatch(/\.nav-button\s*\{[^}]*flex:\s*0 0 auto[^}]*white-space:\s*nowrap/s)
  })
})
