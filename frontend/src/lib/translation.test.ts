import { describe, expect, it } from 'vitest'
import { checkAnswer } from './fuzzy'
import { allowedLangs, autoStartChoice, chipLabel, DEFAULT_PREF, isValidPair, needsPicker } from './translation'

describe('translation language rules', () => {
  it('the picker is for memorization games only, never definition games or Der·Die·Das', () => {
    for (const g of ['speed', 'builder', 'falling', 'memory', 'review', 'daily'] as const) expect(needsPicker(g, 'level')).toBe(true)
    expect(needsPicker('match', 'level')).toBe(false)
    expect(needsPicker('derdiedas', 'level')).toBe(false)
  })

  it('decks use their own language: no picker', () => {
    expect(needsPicker('speed', 'deck')).toBe(false)
    expect(needsPicker('speed', 'set')).toBe(true)
  })

  it('allowed pairs never translate into the word language', () => {
    expect(allowedLangs('en')).toEqual(['uz', 'ru', 'de'])
    expect(allowedLangs('de')).toEqual(['uz', 'ru', 'en'])
    expect(isValidPair('en', 'en')).toBe(false)
    expect(isValidPair('de', 'de')).toBe(false)
    expect(isValidPair('en', 'xx')).toBe(false)
    expect(isValidPair('en', 'de')).toBe(true)
  })

  it('the remembered choice starts directly; otherwise the picker is shown', () => {
    expect(autoStartChoice(DEFAULT_PREF('en'), 'en')).toBeNull()
    expect(autoStartChoice({ ...DEFAULT_PREF('en'), preferred_translation_lang: 'ru', remember_choice: true }, 'en')).toEqual({ tl: 'ru', dir: 'forward' })
    expect(autoStartChoice({ ...DEFAULT_PREF('de'), preferred_translation_lang: 'de', remember_choice: true }, 'de')).toBeNull()
  })

  it('chip label shows the pair and direction', () => {
    expect(chipLabel('en', 'ru')).toBe('EN → RU')
    expect(chipLabel('de', 'uz', 'reverse')).toBe('UZ → DE')
  })
})

describe('answer checking across languages', () => {
  it('accepts any listed alternative', () => {
    expect(checkAnswer('путешествие', 'поездка, путешествие')).toBe('exact')
    expect(checkAnswer('trip', 'journey, trip')).toBe('exact')
  })
  it('tolerates small typos (1 edit ≤ 6 letters, 2 edits longer)', () => {
    expect(checkAnswer('yablko', 'yabloko')).toBe('typo')
    expect(checkAnswer('приключене', 'приключение')).toBe('typo')
    expect(checkAnswer('hous', 'house')).toBe('typo')
    expect(checkAnswer('hxxse', 'house')).toBe('wrong')
  })
  it('treats Russian ё and е as equal', () => {
    expect(checkAnswer('еж', 'ёж')).toBe('exact')
    expect(checkAnswer('зелёный', 'зеленый')).toBe('exact')
  })
  it('accepts ae/oe/ue/ss for ä/ö/ü/ß and optional articles', () => {
    expect(checkAnswer('Maedchen', 'das Mädchen')).toBe('exact')
    expect(checkAnswer('Strasse', 'die Straße')).toBe('exact')
    expect(checkAnswer('schoen', 'schön')).toBe('exact')
    expect(checkAnswer('Apfel', 'der Apfel')).toBe('exact')
    expect(checkAnswer('the dog', 'dog')).toBe('exact')
    expect(checkAnswer('CAT ', 'cat')).toBe('exact')
  })
})
