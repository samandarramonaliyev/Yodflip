import { describe, expect, it } from 'vitest'
import { checkAnswer, levenshtein, normalize } from './fuzzy'

describe('fuzzy answer checking', () => {
  it('normalises apostrophes and case', () => {
    expect(normalize(" O‘zbek  Tili! ")).toBe("o'zbek tili")
  })
  it('levenshtein', () => {
    expect(levenshtein('kitten', 'sitting')).toBe(3)
  })
  it('accepts exact answers and alternatives', () => {
    expect(checkAnswer('olma', 'olma')).toBe('exact')
    expect(checkAnswer('safar', 'sayohat, safar')).toBe('exact')
    expect(checkAnswer('aka', 'aka / uka')).toBe('exact')
  })
  it('accepts small typos', () => {
    expect(checkAnswer('sayohta', 'sayohat')).toBe('typo')
    expect(checkAnswer('mehmonxna', 'mehmonxona')).toBe('typo')
  })
  it('rejects wrong answers and very short typos', () => {
    expect(checkAnswer('non', 'olma')).toBe('wrong')
    expect(checkAnswer('it', 'ot')).toBe('wrong')
    expect(checkAnswer('', 'olma')).toBe('wrong')
  })
  it('ignores a leading "to" or article', () => {
    expect(checkAnswer('borrow', 'to borrow')).toBe('exact')
    expect(checkAnswer('Hund', 'der Hund')).toBe('exact')
  })
})
