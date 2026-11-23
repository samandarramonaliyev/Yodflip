/** Friend duels: API types, guest identity, deep links. */
import type { Track } from '../games/types'
import { request } from './api'
import { load, save } from './storage'
import type { TrLang } from './translation'

export interface DuelSide {
  name: string
  avatar_url: string
  is_guest: boolean
  finished: boolean
  role: 'creator' | 'opponent'
  score?: number
  time_ms?: number
  accuracy?: number
}

export interface DuelQuestion {
  index: number
  prompt: string
  options: string[]
  board?: number
}

export type DuelOutcome = 'win' | 'draw' | 'loss'

export interface Duel {
  code: string
  track: Track
  mode: 'speed' | 'match'
  source: 'level' | 'exam' | 'deck'
  source_ref: string
  source_label: string
  translation_lang: TrLang
  status: 'pending' | 'open' | 'completed' | 'expired'
  total: number
  expires_at: string
  web_link: string
  telegram_link: string
  challenger: { name: string; avatar_url: string }
  creator: DuelSide | null
  opponent: DuelSide | null
  is_draw: boolean
  me: { role: 'creator' | 'opponent'; finished: boolean; is_guest: boolean; answered: number[]; score: number; time_ms: number } | null
  outcome?: DuelOutcome
  xp?: number
  review?: { term: string; answer: string; correct: boolean }[]
  questions?: DuelQuestion[]
  guest_token?: string
}

export interface DuelStats {
  wins: number
  losses: number
  draws: number
  invited: number
  recent: { code: string; mode: string; track: Track; outcome: DuelOutcome; my_score: number; other_score: number; total: number; other: { name: string; avatar_url: string; is_guest: boolean } }[]
  rivals: { name: string; avatar_url: string; played: number; wins: number; losses: number }[]
  open: { code: string; mode: string; track: Track; status: string; source_label: string }[]
}

export interface AnswerResult {
  index: number
  correct: boolean
  correct_index: number
  answered: number
}

const key = (code: string) => `wf.duel.${code}`
export const guestToken = (code: string) => load<string | null>(key(code), null)
export const setGuestToken = (code: string, token: string | null) => save(key(code), token)

function call<T>(method: string, code: string, action = '', body?: unknown): Promise<T> {
  const token = guestToken(code)
  return request<T>(method, `/duels/${code}/${action}`, { body, headers: token ? { 'X-Duel-Guest': token } : undefined })
}

export const duelApi = {
  get: (code: string) => call<Duel>('GET', code),
  start: async (code: string) => {
    const d = await call<Duel>('POST', code, 'start/')
    if (d.guest_token) setGuestToken(code, d.guest_token)
    return d
  },
  answer: (code: string, index: number, choice: number, clientMs: number) =>
    call<AnswerResult>('POST', code, 'answer/', { index, choice, client_ms: Math.round(clientMs) }),
  finish: (code: string) => call<Duel>('POST', code, 'finish/'),
  claim: (code: string) => call<Duel>('POST', code, 'claim/'),
  rematch: (code: string) => call<Duel>('POST', code, 'rematch/'),
}

/** Telegram `startapp=duel_<code>` → in-app path (null when it is something else). */
export function startParamPath(param: string | null | undefined): string | null {
  const m = /^duel_([A-Za-z0-9]{1,16})$/.exec(param ?? '')
  return m ? `/duel/${m[1]}` : null
}

/** Duel code of an in-app path ("/duel/AbC" → "AbC"), used to record who invited a new user. */
export function duelCodeOf(path: string | null | undefined): string | undefined {
  return /^\/duel\/([A-Za-z0-9]{1,16})/.exec(path ?? '')?.[1]
}

export const seconds = (ms: number) => Math.round(ms / 1000)
