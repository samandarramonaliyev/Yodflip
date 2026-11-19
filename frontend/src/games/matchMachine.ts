/**
 * Match Game state machine (pure).
 *
 * Board: TOP = word cards, BOTTOM = definition cards, all face-down, each area shuffled on its own.
 * Player flips one word card and one definition card.
 *  - MATCH    → both cards leave the board (matched), log a correct answer.
 *  - NO MATCH → phase "mismatch" (UI shows both ~1.2s), then RESOLVE flips ALL remaining cards
 *               face-down; the flipped word is logged as a miss.
 * Round ends when every card is matched.
 */

export type Side = 'word' | 'def'

export interface MatchCard {
  id: string
  pairId: string
  side: Side
  text: string
  faceUp: boolean
  matched: boolean
}

export type Phase = 'idle' | 'mismatch' | 'done'

export interface MatchState {
  cards: MatchCard[]
  selectedWord: string | null
  selectedDef: string | null
  phase: Phase
  matches: number
  misses: number
  flips: number
  /** Ordered answer log; pairId refers to the word card's pair */
  log: { pairId: string; correct: boolean }[]
  lastEvent: 'match' | 'miss' | null
}

export type MatchAction = { type: 'FLIP'; id: string } | { type: 'RESOLVE' } | { type: 'RESET'; state: MatchState }

export interface PairInput {
  pairId: string
  word: string
  definition: string
}

export function shuffle<T>(arr: T[], rand: () => number = Math.random): T[] {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

export function createBoard(pairs: PairInput[], rand: () => number = Math.random): MatchState {
  const words: MatchCard[] = pairs.map((p) => ({
    id: `w-${p.pairId}`,
    pairId: p.pairId,
    side: 'word',
    text: p.word,
    faceUp: false,
    matched: false,
  }))
  const defs: MatchCard[] = pairs.map((p) => ({
    id: `d-${p.pairId}`,
    pairId: p.pairId,
    side: 'def',
    text: p.definition,
    faceUp: false,
    matched: false,
  }))
  return {
    cards: [...shuffle(words, rand), ...shuffle(defs, rand)],
    selectedWord: null,
    selectedDef: null,
    phase: pairs.length ? 'idle' : 'done',
    matches: 0,
    misses: 0,
    flips: 0,
    log: [],
    lastEvent: null,
  }
}

function setCards(cards: MatchCard[], ids: string[], patch: Partial<MatchCard>): MatchCard[] {
  return cards.map((c) => (ids.includes(c.id) ? { ...c, ...patch } : c))
}

export function matchReducer(state: MatchState, action: MatchAction): MatchState {
  switch (action.type) {
    case 'RESET':
      return action.state
    case 'FLIP': {
      if (state.phase !== 'idle') return state
      const card = state.cards.find((c) => c.id === action.id)
      if (!card || card.matched || card.faceUp) return state
      if (card.side === 'word' && state.selectedWord) return state
      if (card.side === 'def' && state.selectedDef) return state

      let next: MatchState = {
        ...state,
        cards: setCards(state.cards, [card.id], { faceUp: true }),
        flips: state.flips + 1,
        selectedWord: card.side === 'word' ? card.id : state.selectedWord,
        selectedDef: card.side === 'def' ? card.id : state.selectedDef,
        lastEvent: null,
      }
      if (!next.selectedWord || !next.selectedDef) return next

      const w = next.cards.find((c) => c.id === next.selectedWord)!
      const d = next.cards.find((c) => c.id === next.selectedDef)!
      if (w.pairId === d.pairId) {
        const cards = setCards(next.cards, [w.id, d.id], { matched: true, faceUp: true })
        const matches = next.matches + 1
        next = {
          ...next,
          cards,
          matches,
          selectedWord: null,
          selectedDef: null,
          log: [...next.log, { pairId: w.pairId, correct: true }],
          lastEvent: 'match',
          phase: cards.every((c) => c.matched) ? 'done' : 'idle',
        }
      } else {
        next = {
          ...next,
          phase: 'mismatch',
          misses: next.misses + 1,
          log: [...next.log, { pairId: w.pairId, correct: false }],
          lastEvent: 'miss',
        }
      }
      return next
    }
    case 'RESOLVE': {
      if (state.phase !== 'mismatch') return state
      return {
        ...state,
        cards: state.cards.map((c) => (c.matched ? c : { ...c, faceUp: false })),
        selectedWord: null,
        selectedDef: null,
        phase: 'idle',
        lastEvent: null,
      }
    }
    default:
      return state
  }
}

export function accuracy(state: Pick<MatchState, 'matches' | 'misses'>): number {
  const turns = state.matches + state.misses
  return turns ? Math.round((100 * state.matches) / turns) : 0
}

/** Unique pairIds that were missed at least once. */
export function missedPairs(state: MatchState): string[] {
  return [...new Set(state.log.filter((l) => !l.correct).map((l) => l.pairId))]
}

export const BOARD_SIZES = { easy: 4, medium: 6, hard: 8 } as const
export type Difficulty = keyof typeof BOARD_SIZES

/** Split a long set into rounds of `size` pairs (4–8). A tiny tail is merged into the last round. */
export function splitRounds<T>(items: T[], size: number): T[][] {
  const s = Math.max(4, Math.min(8, size))
  const rounds: T[][] = []
  for (let i = 0; i < items.length; i += s) rounds.push(items.slice(i, i + s))
  if (rounds.length > 1 && rounds[rounds.length - 1].length < 3) {
    const tail = rounds.pop()!
    rounds[rounds.length - 1] = [...rounds[rounds.length - 1], ...tail]
  }
  return rounds
}
