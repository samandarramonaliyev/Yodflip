import { describe, expect, it } from 'vitest'
import { GAME_MODES, isAvailable, modeFor, sidesFor, supportsReverse, usableItems } from './direction'
import type { GameId, GameItem } from './types'

const en: GameItem = {
  key: 'w1',
  word_id: 1,
  term: 'apple',
  word: 'apple',
  article: '',
  definition: 'a round fruit with red or green skin',
  translation: 'olma',
  pos: 'noun',
  example: '',
  example_uz: '',
}

const de: GameItem = {
  ...en,
  key: 'w2',
  term: 'der Apfel',
  word: 'Apfel',
  article: 'der',
  definition: 'eine runde Frucht',
  translation: 'olma',
}

const memorizationGames: GameId[] = ['speed', 'builder', 'falling', 'review', 'daily', 'flashcards', 'learn', 'write', 'memory']

describe('Game Direction Rules', () => {
  it('match game is a definition game in the same language, never Uzbek', () => {
    expect(modeFor('match')).toBe('definition')
    const s = sidesFor(en, 'match', 'en')
    expect(s).toEqual({ prompt: 'apple', answer: en.definition, promptLang: 'en', answerLang: 'en' })
    const sd = sidesFor(de, 'match', 'de')
    expect(sd.answer).toBe('eine runde Frucht')
    expect(sd.answer).not.toBe(de.translation)
    expect([sd.promptLang, sd.answerLang]).not.toContain('uz')
  })

  it('reverse toggle never applies to definition games', () => {
    expect(supportsReverse('match')).toBe(false)
    expect(sidesFor(en, 'match', 'en', true).answer).toBe(en.definition)
  })

  it.each(memorizationGames)('%s is a memorization game: word ↔ Uzbek', (g) => {
    expect(modeFor(g)).toBe('memorize')
    expect(supportsReverse(g)).toBe(true)
    expect(sidesFor(en, g, 'en')).toMatchObject({ prompt: 'apple', answer: 'olma', answerLang: 'uz' })
    expect(sidesFor(de, g, 'de', true)).toMatchObject({ prompt: 'olma', answer: 'der Apfel', promptLang: 'uz', answerLang: 'de' })
  })

  it('Der·Die·Das is German-only: noun → article', () => {
    expect(isAvailable('derdiedas', 'en')).toBe(false)
    expect(isAvailable('derdiedas', 'de')).toBe(true)
    expect(sidesFor(de, 'derdiedas', 'de', true)).toMatchObject({ prompt: 'Apfel', answer: 'der' })
    expect(supportsReverse('derdiedas')).toBe(false)
  })

  it('every game has a mode', () => {
    expect(Object.keys(GAME_MODES)).toHaveLength(11)
  })

  it('filters items that lack the needed back side', () => {
    const noDef = { ...en, key: 'x', definition: '' }
    const noUz = { ...en, key: 'y', translation: '' }
    expect(usableItems([en, noDef, noUz], 'match').map((i) => i.key)).toEqual(['w1', 'y'])
    expect(usableItems([en, noDef, noUz], 'speed').map((i) => i.key)).toEqual(['w1', 'x'])
    expect(usableItems([en, de], 'derdiedas').map((i) => i.key)).toEqual(['w2'])
  })
})
