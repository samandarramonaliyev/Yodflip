import { describe, expect, it } from 'vitest'
import { duelCodeOf, startParamPath } from './duel'

describe('duel deep links', () => {
  it('routes startapp=duel_<code> to the duel page', () => {
    expect(startParamPath('duel_AbC12345')).toBe('/duel/AbC12345')
  })
  it('ignores everything else', () => {
    for (const p of [null, undefined, '', 'duel_', 'deck_abc', 'duel_../x', 'duel_a b']) expect(startParamPath(p)).toBeNull()
  })
  it('finds the duel code in a path', () => {
    expect(duelCodeOf('/duel/AbC12345')).toBe('AbC12345')
    expect(duelCodeOf('/duel')).toBeUndefined()
    expect(duelCodeOf('/d/xyz')).toBeUndefined()
  })
})
