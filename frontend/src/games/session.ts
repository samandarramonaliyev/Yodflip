/**
 * Game session state machine (pure), shared by every game.
 *
 *   playing ──ROUND_DONE──▶ round_complete ──NEXT_ROUND──▶ playing      (more rounds left)
 *   playing ──ROUND_DONE──▶ game_complete                                 (last round)
 *   any     ──RESTART─────▶ playing (round 1, new rounds, new playId)
 *
 * ROUND_DONE is accepted only while "playing" and only once per round, so a round can never
 * be finished (or saved) twice. Single-round games simply go straight to game_complete.
 */
import type { GameItem, ResultItem } from './types'

export type SessionStatus = 'playing' | 'round_complete' | 'game_complete'

export interface RoundStat {
  round: number
  results: ResultItem[]
  durationMs: number
  flips?: number
  comboMax?: number
  /** null until the backend confirmed the round */
  xp: number | null
  newAchievements: string[]
  learnedNow: number
}

export interface SessionState {
  rounds: GameItem[][]
  index: number
  status: SessionStatus
  stats: RoundStat[]
  /** Changes on every restart; used as React key and to save each round exactly once. */
  playId: number
}

export type SessionAction =
  | { type: 'ROUND_DONE'; results: ResultItem[]; durationMs: number; flips?: number; comboMax?: number }
  | { type: 'NEXT_ROUND' }
  | { type: 'RESTART'; rounds: GameItem[][] }
  | { type: 'SAVED'; playId: number; round: number; xp: number; newAchievements?: string[]; learnedNow?: number }

export function createSession(rounds: GameItem[][], playId = 1): SessionState {
  return { rounds, index: 0, status: 'playing', stats: [], playId }
}

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case 'ROUND_DONE': {
      if (state.status !== 'playing' || state.stats.some((s) => s.round === state.index)) return state
      const stat: RoundStat = {
        round: state.index,
        results: action.results,
        durationMs: action.durationMs,
        flips: action.flips,
        comboMax: action.comboMax,
        xp: null,
        newAchievements: [],
        learnedNow: 0,
      }
      const last = state.index >= state.rounds.length - 1
      return { ...state, stats: [...state.stats, stat], status: last ? 'game_complete' : 'round_complete' }
    }
    case 'NEXT_ROUND':
      if (state.status !== 'round_complete') return state
      return { ...state, index: state.index + 1, status: 'playing' }
    case 'RESTART':
      return createSession(action.rounds, state.playId + 1)
    case 'SAVED':
      if (action.playId !== state.playId) return state
      return {
        ...state,
        stats: state.stats.map((s) =>
          s.round === action.round ? { ...s, xp: action.xp, newAchievements: action.newAchievements || [], learnedNow: action.learnedNow || 0 } : s,
        ),
      }
    default:
      return state
  }
}

export function accuracyOf(results: ResultItem[]): number {
  return results.length ? Math.round((100 * results.filter((r) => r.correct).length) / results.length) : 0
}

export interface Totals {
  durationMs: number
  flips?: number
  accuracy: number
  xp: number | null
  saving: boolean
  missed: GameItem[]
  newAchievements: string[]
  learnedNow: number
}

/** Aggregate stats over all finished rounds (final results screen). */
export function totals(state: SessionState, stats: RoundStat[] = state.stats): Totals {
  const results = stats.flatMap((s) => s.results)
  const anyFlips = stats.some((s) => s.flips !== undefined)
  const wrong = new Set(results.filter((r) => !r.correct).map((r) => r.term))
  const pool = state.rounds.flat()
  const seen = new Set<string>()
  const missed = pool.filter((i) => wrong.has(i.term) && !seen.has(i.term) && seen.add(i.term))
  return {
    durationMs: stats.reduce((a, s) => a + s.durationMs, 0),
    flips: anyFlips ? stats.reduce((a, s) => a + (s.flips || 0), 0) : undefined,
    accuracy: accuracyOf(results),
    xp: stats.every((s) => s.xp !== null) ? stats.reduce((a, s) => a + (s.xp || 0), 0) : null,
    saving: stats.some((s) => s.xp === null),
    missed,
    newAchievements: [...new Set(stats.flatMap((s) => s.newAchievements))],
    learnedNow: stats.reduce((a, s) => a + s.learnedNow, 0),
  }
}

/** Where "Boshqa to'plam" (choose another set) should go for a given source. */
export function otherSetPath(source: string, params: URLSearchParams): string {
  if (source === 'level') return params.get('level') ? `/levels/${params.get('level')}` : '/levels'
  if (source === 'set') return '/sets'
  if (source === 'deck') return params.get('id') ? `/decks/${params.get('id')}` : '/decks'
  if (source === 'missed' || source === 'want' || source === 'learned') return `/lists/${source}`
  return '/levels'
}
