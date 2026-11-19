import { describe, expect, it } from 'vitest'
import { createSession, otherSetPath, sessionReducer, totals, type SessionState } from './session'
import type { GameItem, ResultItem } from './types'

const item = (k: string): GameItem => ({
  key: k,
  word_id: null,
  term: k,
  word: k,
  article: '',
  definition: `${k} def`,
  translation: `${k} uz`,
  pos: '',
  example: '',
  example_uz: '',
})
const ok = (k: string): ResultItem => ({ term: k, correct: true })
const bad = (k: string): ResultItem => ({ term: k, correct: false })

const rounds = [[item('a'), item('b')], [item('c'), item('d')], [item('e'), item('f')]]

describe('game session state machine', () => {
  it('all pairs of a round matched → round_complete', () => {
    let s = createSession(rounds)
    expect(s.status).toBe('playing')
    s = sessionReducer(s, { type: 'ROUND_DONE', results: [ok('a'), ok('b')], durationMs: 5000, flips: 4 })
    expect(s.status).toBe('round_complete')
    expect(s.index).toBe(0)
    expect(s.stats).toHaveLength(1)
  })

  it('NEXT_ROUND loads the next round; last round → game_complete', () => {
    let s: SessionState = createSession(rounds)
    for (let r = 0; r < 3; r++) {
      expect(s.index).toBe(r)
      s = sessionReducer(s, { type: 'ROUND_DONE', results: [ok('x')], durationMs: 1000, flips: 2 })
      if (r < 2) {
        expect(s.status).toBe('round_complete')
        s = sessionReducer(s, { type: 'NEXT_ROUND' })
        expect(s.status).toBe('playing')
      }
    }
    expect(s.status).toBe('game_complete')
    expect(s.stats.map((x) => x.round)).toEqual([0, 1, 2])
  })

  it('a round can only finish once (no double save)', () => {
    let s = createSession(rounds)
    s = sessionReducer(s, { type: 'ROUND_DONE', results: [ok('a')], durationMs: 1, flips: 2 })
    const again = sessionReducer(s, { type: 'ROUND_DONE', results: [ok('a')], durationMs: 1, flips: 2 })
    expect(again).toBe(s)
    expect(sessionReducer(createSession(rounds), { type: 'NEXT_ROUND' }).index).toBe(0)
  })

  it('single-round games go straight to game_complete', () => {
    const s = sessionReducer(createSession([[item('a')]]), { type: 'ROUND_DONE', results: [ok('a')], durationMs: 1 })
    expect(s.status).toBe('game_complete')
  })

  it('RESTART starts again from round 1 with a new playId; stale saves are ignored', () => {
    let s = createSession(rounds)
    s = sessionReducer(s, { type: 'ROUND_DONE', results: [ok('a')], durationMs: 1, flips: 2 })
    const oldId = s.playId
    s = sessionReducer(s, { type: 'RESTART', rounds })
    expect(s).toMatchObject({ index: 0, status: 'playing', stats: [] })
    expect(s.playId).toBe(oldId + 1)
    expect(sessionReducer(s, { type: 'SAVED', playId: oldId, round: 0, xp: 10 })).toBe(s)
  })

  it('totals aggregate time, flips, accuracy, XP and unique missed words', () => {
    let s = createSession(rounds)
    s = sessionReducer(s, { type: 'ROUND_DONE', results: [bad('a'), ok('a'), ok('b')], durationMs: 3000, flips: 6 })
    s = sessionReducer(s, { type: 'SAVED', playId: s.playId, round: 0, xp: 20, learnedNow: 1, newAchievements: ['first_game'] })
    s = sessionReducer(s, { type: 'NEXT_ROUND' })
    s = sessionReducer(s, { type: 'ROUND_DONE', results: [ok('c'), bad('d'), bad('d'), ok('d')], durationMs: 2000, flips: 8 })
    let sum = totals(s)
    expect(sum.saving).toBe(true)
    expect(sum.xp).toBeNull()
    s = sessionReducer(s, { type: 'SAVED', playId: s.playId, round: 1, xp: 20 })
    sum = totals(s)
    expect(sum).toMatchObject({ durationMs: 5000, flips: 14, accuracy: 57, xp: 40, saving: false, learnedNow: 1, newAchievements: ['first_game'] })
    expect(sum.missed.map((m) => m.key)).toEqual(['a', 'd'])
  })

  it('"Boshqa to\'plam" goes back to the right page', () => {
    expect(otherSetPath('level', new URLSearchParams('level=B1'))).toBe('/levels/B1')
    expect(otherSetPath('set', new URLSearchParams())).toBe('/sets')
    expect(otherSetPath('deck', new URLSearchParams('id=5'))).toBe('/decks/5')
    expect(otherSetPath('missed', new URLSearchParams())).toBe('/lists/missed')
  })
})
