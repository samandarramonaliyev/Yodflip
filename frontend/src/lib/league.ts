/** Weekly leagues: API types and pure helpers. */
import type { UiLang } from './types'

export interface Tier {
  code: string
  order: number
  emoji: string
  color: string
  name: Record<UiLang, string>
}

export type Zone = 'promote' | 'demote' | 'safe'

export interface LeagueRow {
  rank: number
  user_id: number
  name: string
  avatar_url: string
  xp: number
  is_me: boolean
  zone: Zone
}

export interface WeekResult {
  week: string
  tier: Tier
  new_tier: Tier | null
  rank: number | null
  xp: number
  result: 'promoted' | 'demoted' | 'stayed' | 'trophy' | ''
}

export interface LeagueState {
  tiers: Tier[]
  tier: Tier
  trophies: number
  week: { start: string; ends_at: string; seconds_left: number }
  joined: boolean
  group: LeagueRow[]
  zones: { promote: number; demote: number; size: number; top_tier: boolean } | null
  me: { rank: number; xp: number; zone: Zone; need_xp: number } | null
  last_result: WeekResult | null
}

/** Countdown parts from seconds ("3 kun 5 soat qoldi"). */
export function countdown(seconds: number): { days: number; hours: number; minutes: number } {
  const s = Math.max(0, Math.floor(seconds))
  return { days: Math.floor(s / 86400), hours: Math.floor((s % 86400) / 3600), minutes: Math.floor((s % 3600) / 60) }
}

/** Seconds left right now, given the server's answer and when it arrived (keeps ticking between refetches). */
export function secondsLeft(state: Pick<LeagueState, 'week'>, fetchedAt: number, now: number = Date.now()): number {
  return Math.max(0, state.week.seconds_left - Math.floor((now - fetchedAt) / 1000))
}

/** i18n key of a week result line. */
export function resultKey(r: WeekResult): string {
  if (r.result === 'trophy') return 'league.result_trophy'
  if (r.result === 'promoted') return 'league.result_up'
  if (r.result === 'demoted') return 'league.result_down'
  return 'league.result_stay'
}

export const LIVE_REFRESH_MS = 30_000
