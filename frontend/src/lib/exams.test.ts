import { describe, expect, it } from 'vitest'
import { duelPath, otherSetPath } from '../games/session'
import { clock, examPlayUrl } from './exams'

describe('exam packs', () => {
  it('builds game urls', () => {
    expect(examPlayUrl('speed', 'goethe-a1')).toBe('/play/speed?source=exam&pack=goethe-a1')
    expect(examPlayUrl('match', 'goethe-a1', 'essen')).toBe('/play/match?source=exam&pack=goethe-a1&topic=essen')
    expect(examPlayUrl('speed', 'x', 'a,b', true)).toContain('source=examreview')
  })
  it('formats the timer', () => {
    expect(clock(600)).toBe('10:00')
    expect(clock(9)).toBe('0:09')
    expect(clock(-5)).toBe('0:00')
  })
  it('returns to the pack and duels from it', () => {
    const p = new URLSearchParams('source=exam&pack=ielts-academic')
    expect(otherSetPath('exam', p)).toBe('/exams/ielts-academic')
    expect(duelPath('exam', p)).toBe('/duel?source=exam&ref=ielts-academic')
  })
})
