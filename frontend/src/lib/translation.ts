/**
 * Translation language for memorization games (separate from the interface language).
 *   EN track → uz / ru / de      DE track → uz / ru / en      never a word into its own language.
 * Definition games (Match) and Der·Die·Das never show the picker; decks use their own language.
 */
import { modeFor } from '../games/direction'
import type { GameId, Source, Track } from '../games/types'

export type TrLang = 'uz' | 'ru' | 'en' | 'de'
export type Direction = 'forward' | 'reverse'

export const LANG_META: Record<TrLang, { flag: string; name: string; short: string; voice: string }> = {
  uz: { flag: '🇺🇿', name: "O'zbekcha", short: 'UZ', voice: 'uz-UZ' },
  ru: { flag: '🇷🇺', name: 'Русский', short: 'RU', voice: 'ru-RU' },
  en: { flag: '🇬🇧', name: 'English', short: 'EN', voice: 'en-US' },
  de: { flag: '🇩🇪', name: 'Deutsch', short: 'DE', voice: 'de-DE' },
}

export const ALL_LANGS: TrLang[] = ['uz', 'ru', 'en', 'de']

export function allowedLangs(track: Track): TrLang[] {
  return ['uz', 'ru', track === 'en' ? 'de' : 'en']
}

export function isValidPair(track: Track, lang: string | null | undefined): lang is TrLang {
  return Boolean(lang) && (allowedLangs(track) as string[]).includes(lang as string)
}

/** The picker is shown before memorization games only; decks always use the deck's language. */
export function needsPicker(game: GameId, source: Source | null): boolean {
  return modeFor(game) === 'memorize' && source !== 'deck'
}

export function chipLabel(track: Track, lang: TrLang, direction: Direction = 'forward'): string {
  const a = track.toUpperCase()
  const b = LANG_META[lang].short
  return direction === 'reverse' ? `${b} → ${a}` : `${a} → ${b}`
}

export interface TranslationPref {
  track: Track
  preferred_translation_lang: TrLang
  preferred_direction: Direction
  remember_choice: boolean
}

export const DEFAULT_PREF = (track: Track): TranslationPref => ({
  track,
  preferred_translation_lang: 'uz',
  preferred_direction: 'forward',
  remember_choice: false,
})

/** With "Tanlovimni eslab qol" on, start directly with the saved choice (if still valid). */
export function autoStartChoice(pref: TranslationPref | null | undefined, track: Track): { tl: TrLang; dir: Direction } | null {
  if (!pref?.remember_choice || !isValidPair(track, pref.preferred_translation_lang)) return null
  return { tl: pref.preferred_translation_lang, dir: pref.preferred_direction === 'reverse' ? 'reverse' : 'forward' }
}
