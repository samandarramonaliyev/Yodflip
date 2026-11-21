import type { Track } from '../games/types'

export type UiLang = 'uz' | 'en' | 'ru'
export type Cefr = 'A1' | 'A2' | 'B1' | 'B2' | 'C1'

export interface User {
  id: number
  email: string | null
  display_name: string
  telegram_id: number | null
  telegram_username: string
  avatar_url: string
  active_track: Track
  cefr_level_en: Cefr
  cefr_level_de: Cefr
  ui_language: UiLang
  xp: number
  level: number
  streak: number
  best_streak: number
  last_active_date: string | null
  reminder_time: string | null
  has_password: boolean
  is_telegram_linked: boolean
}

export interface AuthResponse {
  access: string
  refresh: string
  user: User
}

export interface PackRow {
  id: number
  slug: string
  emoji: string
  name: Record<UiLang, string>
  total: number
  found: number
  learned: number
  percent: number
}

/** Server-side level progress (found words). */
export interface LevelProgress {
  level: Cefr
  total: number
  found: number
  learned: number
  remaining: number
  percent: number
  unlock_target: number
  to_unlock: number
  unlocked: boolean
  completed: boolean
}

export interface LevelRow extends LevelProgress {
  packs: PackRow[]
}

export interface LevelRoundOutcome {
  session_id: string
  new_found_count: number
  progress: LevelProgress
  completed_now: boolean
  bonus_xp: number
}

export interface Word {
  id: number
  track: Track
  level: Cefr
  pack_slug: string
  word: string
  article: string
  display: string
  part_of_speech: string
  definition: string
  translation_uz: string
  example: string
  example_uz: string
}

export interface UserWord {
  id: number
  track: Track
  term: string
  article: string
  translation_uz: string
  definition: string
  box: number
  correct_count: number
  miss_count: number
  want_to_learn: boolean
  is_learned: boolean
  is_missed: boolean
}

export interface Card {
  id: number
  term: string
  translation: string
  extra_translations?: Partial<Record<'uz' | 'ru' | 'en' | 'de', string>>
  definition: string
  example: string
  article: string
  image: string | null
  order: number
}

export interface Deck {
  id: number
  name: string
  track: Track
  description: string
  /** Language of the cards' translation side */
  translation_lang?: 'uz' | 'ru' | 'en' | 'de'
  is_public: boolean
  share_code: string
  card_count: number
  owner_name: string
  is_owner: boolean
  updated_at: string
  cards?: Card[]
}

export interface SetPair {
  id?: number
  word: string
  definition: string
  part_of_speech: string
  article: string | null
  translation_uz: string
  /** ru + the other track language from the scanner (editable) */
  translations?: Partial<Record<'ru' | 'en' | 'de', string>>
}

export interface WordSet {
  id: number
  name: string
  track: Track
  pair_count: number
  pairs?: SetPair[]
  /** Translation languages present in this set */
  available_langs?: ('uz' | 'ru' | 'en' | 'de')[]
  created_at: string
}

export interface ProfileStats {
  user: User
  track: Track
  xp: number
  level: number
  level_floor: number
  level_ceil: number
  streak: number
  best_streak: number
  played_today: boolean
  total_words: number
  learned: number
  missed: number
  want: number
  due: number
  accuracy: number
  translation_langs?: { lang: 'uz' | 'ru' | 'en' | 'de'; count: number; percent: number }[]
  cefr: Cefr
  chart: { date: string; xp: number; correct: number }[]
}

export interface Achievement {
  code: string
  emoji: string
  unlocked: boolean
  unlocked_at: string | null
}

export interface LeaderRow {
  rank: number
  user_id?: number
  name: string
  telegram_username: string
  avatar_url: string
  is_telegram: boolean
  score: number
  level?: number
  streak?: number
  is_me?: boolean
}

export interface ResultsResponse {
  xp_earned: number
  xp_total: number
  level: number
  streak: number
  correct: number
  attempts: number
  accuracy: number
  perfect: boolean
  learned_now: string[]
  new_achievements: string[]
  flips?: number
  daily?: { score: number; first_attempt: boolean }
  level_round?: LevelRoundOutcome
}

export interface PublicConfig {
  bot_username: string
  telegram_mock: boolean
  ocr_mock: boolean
  ocr_daily_limit: number
}
