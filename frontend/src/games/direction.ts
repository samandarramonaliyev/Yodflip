/**
 * Game Direction Rules (strict, mirrors backend games/rules.py)
 *
 * 1. DEFINITION games: word ↔ same-language definition. Never Uzbek. No reverse.
 * 2. MEMORIZATION games: word ↔ translation in the chosen language (uz / ru / en / de, never the
 *    word's own language). Reverse = translation → word.
 * 3. ARTICLE game (Der·Die·Das): German noun → article. German track only.
 */
import type { GameId, GameItem, Mode, Track } from './types'

export const GAME_MODES: Record<GameId, Mode> = {
  match: 'definition',
  speed: 'memorize',
  builder: 'memorize',
  falling: 'memorize',
  review: 'memorize',
  daily: 'memorize',
  flashcards: 'memorize',
  learn: 'memorize',
  write: 'memorize',
  memory: 'memorize',
  derdiedas: 'article',
}

export function modeFor(game: GameId): Mode {
  return GAME_MODES[game]
}

export function isAvailable(game: GameId, track: Track): boolean {
  if (game === 'derdiedas') return track === 'de'
  return true
}

/** Whether the reverse toggle (Uzbek → word) is offered for a game. */
export function supportsReverse(game: GameId): boolean {
  return GAME_MODES[game] === 'memorize'
}

export type SideLang = Track | 'uz' | 'ru'

export interface Sides {
  /** What the player sees / is asked about */
  prompt: string
  /** The expected answer */
  answer: string
  promptLang: SideLang
  answerLang: SideLang
}

/** Resolve prompt/answer for an item according to the rules. */
export function sidesFor(item: GameItem, game: GameId, track: Track, reverse = false): Sides {
  const mode = modeFor(game)
  if (mode === 'definition') {
    // Same language on both sides. Reverse never applies.
    return { prompt: item.term, answer: item.definition, promptLang: track, answerLang: track }
  }
  if (mode === 'article') {
    return { prompt: item.word, answer: item.article, promptLang: 'de', answerLang: 'de' }
  }
  const trLang: SideLang = item.translation_lang ?? 'uz'
  if (reverse && supportsReverse(game)) {
    return { prompt: item.translation, answer: item.term, promptLang: trLang, answerLang: track }
  }
  return { prompt: item.term, answer: item.translation, promptLang: track, answerLang: trLang }
}

/** Items that can actually be used in a game (has the needed back side). */
export function usableItems(items: GameItem[], game: GameId): GameItem[] {
  const mode = modeFor(game)
  return items.filter((i) =>
    mode === 'definition'
      ? Boolean(i.definition)
      : mode === 'article'
        ? ['der', 'die', 'das'].includes(i.article)
        : Boolean(i.translation),
  )
}
