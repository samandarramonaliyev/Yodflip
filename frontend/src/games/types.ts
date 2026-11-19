export type Track = 'en' | 'de'
export type Mode = 'definition' | 'memorize' | 'article'
export type GameId =
  | 'match'
  | 'speed'
  | 'builder'
  | 'falling'
  | 'review'
  | 'daily'
  | 'flashcards'
  | 'learn'
  | 'write'
  | 'memory'
  | 'derdiedas'

export type Source = 'level' | 'deck' | 'set' | 'missed' | 'want' | 'learned' | 'review' | 'daily'

/** A word item as returned by /api/games/words/ */
export interface GameItem {
  key: string
  word_id: number | null
  term: string // display form, German nouns include the article
  word: string // without article
  article: string
  definition: string // same language as term
  translation: string // Uzbek
  pos: string
  example: string
  example_uz: string
}

export interface ResultItem {
  term: string
  word_id?: number | null
  translation?: string
  definition?: string
  article?: string
  correct: boolean
}

export interface GameOutcome {
  results: ResultItem[]
  durationMs: number
  comboMax?: number
  /** Match game only */
  misses?: number
  flips?: number
}

export interface GameProps {
  items: GameItem[]
  track: Track
  reverse: boolean
  onFinish: (outcome: GameOutcome) => void
}

export function toResult(item: GameItem, correct: boolean): ResultItem {
  return {
    term: item.term,
    word_id: item.word_id,
    translation: item.translation,
    definition: item.definition,
    article: item.article,
    correct,
  }
}
