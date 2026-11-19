import { describe, expect, it } from 'vitest'
import {
  accuracy,
  createBoard,
  matchReducer,
  missedPairs,
  splitRounds,
  type MatchState,
  type PairInput,
} from './matchMachine'

const pairs: PairInput[] = [
  { pairId: 'a', word: 'apple', definition: 'a round fruit' },
  { pairId: 'b', word: 'bread', definition: 'food made from flour' },
  { pairId: 'c', word: 'milk', definition: 'white drink from cows' },
  { pairId: 'd', word: 'tea', definition: 'hot drink from leaves' },
]

const flip = (s: MatchState, id: string) => matchReducer(s, { type: 'FLIP', id })

describe('match game state machine', () => {
  it('creates words on top and definitions at the bottom, all face-down', () => {
    const s = createBoard(pairs)
    expect(s.cards).toHaveLength(8)
    expect(s.cards.slice(0, 4).every((c) => c.side === 'word')).toBe(true)
    expect(s.cards.slice(4).every((c) => c.side === 'def')).toBe(true)
    expect(s.cards.every((c) => !c.faceUp && !c.matched)).toBe(true)
    expect(s.phase).toBe('idle')
  })

  it('shuffles each area independently', () => {
    let seed = 1
    const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
    const s = createBoard(pairs, rand)
    const wordOrder = s.cards.slice(0, 4).map((c) => c.pairId).join('')
    const defOrder = s.cards.slice(4).map((c) => c.pairId).join('')
    expect(wordOrder).not.toBe(defOrder)
  })

  it('a correct match removes both cards and logs a correct answer', () => {
    let s = createBoard(pairs)
    s = flip(s, 'w-a')
    expect(s.cards.find((c) => c.id === 'w-a')!.faceUp).toBe(true)
    s = flip(s, 'd-a')
    expect(s.cards.filter((c) => c.matched)).toHaveLength(2)
    expect(s.matches).toBe(1)
    expect(s.lastEvent).toBe('match')
    expect(s.log).toEqual([{ pairId: 'a', correct: true }])
    expect(s.phase).toBe('idle')
  })

  it('a wrong match enters mismatch, then RESOLVE flips ALL remaining cards face-down', () => {
    let s = createBoard(pairs)
    s = flip(s, 'w-a')
    s = flip(s, 'd-a') // matched
    s = flip(s, 'w-b')
    s = flip(s, 'd-c') // wrong
    expect(s.phase).toBe('mismatch')
    expect(s.misses).toBe(1)
    expect(s.log.at(-1)).toEqual({ pairId: 'b', correct: false }) // the word is recorded as miss
    // input is locked while showing the mismatch
    expect(flip(s, 'w-d')).toBe(s)
    s = matchReducer(s, { type: 'RESOLVE' })
    expect(s.phase).toBe('idle')
    const remaining = s.cards.filter((c) => !c.matched)
    expect(remaining.every((c) => !c.faceUp)).toBe(true)
    expect(s.cards.filter((c) => c.matched).every((c) => c.faceUp)).toBe(true)
  })

  it('only one word card and one definition card can be selected at a time', () => {
    let s = createBoard(pairs)
    s = flip(s, 'w-a')
    const before = s
    s = flip(s, 'w-b')
    expect(s).toBe(before)
    s = flip(s, 'w-a') // already face up
    expect(s).toBe(before)
  })

  it('round ends when the board is empty; counts flips and accuracy', () => {
    let s = createBoard(pairs)
    s = flip(s, 'w-a')
    s = flip(s, 'd-b')
    s = matchReducer(s, { type: 'RESOLVE' })
    for (const id of ['a', 'b', 'c', 'd']) {
      s = flip(s, `w-${id}`)
      s = flip(s, `d-${id}`)
    }
    expect(s.phase).toBe('done')
    expect(s.flips).toBe(10)
    expect(s.matches).toBe(4)
    expect(accuracy(s)).toBe(80)
    expect(missedPairs(s)).toEqual(['a'])
  })

  it('splits long sets into rounds of 4–8 pairs', () => {
    const items = Array.from({ length: 20 }, (_, i) => i)
    expect(splitRounds(items, 6).map((r) => r.length)).toEqual([6, 6, 8])
    expect(splitRounds(items, 8).map((r) => r.length)).toEqual([8, 8, 4])
    expect(splitRounds(items, 2).map((r) => r.length)).toEqual([4, 4, 4, 4, 4])
    expect(splitRounds([1, 2, 3], 6)).toEqual([[1, 2, 3]])
  })
})
