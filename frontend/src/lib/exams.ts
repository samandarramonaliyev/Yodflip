import type { Track } from '../games/types'
import type { LevelProgress, UiLang, Word } from './types'

export type Names = Record<UiLang, string>

export interface ExamPackRow {
  slug: string
  track: Track
  emoji: string
  name: Names
  total: number
  topic_count: number
  found: number
  percent: number
}

export interface ExamTopic {
  slug: string
  emoji: string
  name: Names
  total: number
  found: number
  percent: number
}

export interface ExamGoal {
  slug: string
  track: Track
  emoji: string
  name: Names
  per_day: number
  done: number
  reached: boolean
}

export interface ExamPackDetail extends LevelProgress {
  slug: string
  track: Track
  emoji: string
  name: Names
  topics: ExamTopic[]
  next_topic: string | null
  goal: ExamGoal | null
  last_simulation: { score: number; total: number } | null
}

export type PackWord = Word & { translation: string; example_tr: string; collocations: string; word_family: string }

export interface SimQuestion {
  index: number
  kind: 'translation' | 'reverse' | 'definition'
  prompt: string
  options: string[]
}

export interface Simulation {
  id: number
  pack: string
  name: Names
  time_limit: number
  questions: SimQuestion[]
}

export interface SimResult {
  score: number
  total: number
  percent: number
  xp: number
  xp_total: number
  streak: number
  late: boolean
  duration_ms: number
  weak_topics: string[]
  topics: { slug: string; emoji: string; name: Names; correct: number; total: number; percent: number; weak: boolean }[]
  review: { prompt: string; answer: string; given: string | null; correct: boolean }[]
}

/** Game URL for words of a pack. Found words are left out unless `review` is set. */
export function examPlayUrl(game: string, slug: string, topic?: string | null, review = false): string {
  const q = new URLSearchParams({ source: review ? 'examreview' : 'exam', pack: slug })
  if (topic) q.set('topic', topic)
  return `/play/${game}?${q.toString()}`
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
