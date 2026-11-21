import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const prefs = { current: { preferred_translation_lang: 'uz', preferred_direction: 'forward', remember_choice: false } }
const get = vi.fn()
const post = vi.fn()
const request = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    request: (...a: unknown[]) => request(...a),
  },
  ApiError: class extends Error {},
  errorKey: () => 'err.generic',
}))
vi.mock('../lib/fx', () => ({ burst: vi.fn(), feedbackCorrect: vi.fn(), feedbackWrong: vi.fn(), feedbackWin: vi.fn() }))

import Play from './Play'

const item = (k: string, lang = 'uz') => ({
  key: k,
  word_id: Number(k.replace(/\D/g, '')) || 1,
  term: `word-${k}`,
  word: `word-${k}`,
  article: 'der',
  definition: `def ${k}`,
  translation: `${lang}-${k}`,
  translation_lang: lang,
  pos: 'noun',
  example: '',
  example_uz: '',
})

function wordsFor(query: Record<string, unknown>) {
  const lang = (query.translation_lang as string) || 'uz'
  return { items: ['w1', 'w2', 'w3', 'w4'].map((k) => item(k, lang)), translation_lang: lang }
}

beforeEach(() => {
  get.mockImplementation(async (path: string, query: Record<string, unknown> = {}) => {
    if (path === '/auth/translation-prefs/') return { en: { track: 'en', ...prefs.current }, de: { track: 'de', ...prefs.current } }
    if (path === '/games/words/') return wordsFor(query)
    if (path.includes('/round/'))
      return {
        session_id: 's1',
        completed: false,
        pool_done: false,
        words: wordsFor(query).items,
        progress: { level: 'A1', total: 100, found: 0, learned: 0, remaining: 100, percent: 0, unlock_target: 70, to_unlock: 70, unlocked: true, completed: false },
      }
    return {}
  })
  request.mockResolvedValue({})
  post.mockResolvedValue({})
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  prefs.current = { preferred_translation_lang: 'uz', preferred_direction: 'forward', remember_choice: false }
})

const renderAt = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/play/:game" element={<Play />} />
      </Routes>
    </MemoryRouter>,
  )

const wordCalls = () => get.mock.calls.filter((c) => c[0] === '/games/words/' || String(c[0]).includes('/round/'))

describe('translation picker before games', () => {
  it('memorization game: picker first (Uzbek pre-selected), then the round in the chosen language', async () => {
    renderAt('/play/speed?source=daily')
    expect(await screen.findByText('Qaysi tilga tarjima qilinsin?')).toBeTruthy()
    expect(screen.getByRole('button', { name: /O'zbekcha/ }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByRole('button', { name: /English/ })).toBeNull() // EN track: no en → en
    fireEvent.click(screen.getByRole('button', { name: /Русский/ }))
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getAllByRole('button', { name: /Boshlash/ })[0])
    await waitFor(() => expect(wordCalls().length).toBe(1))
    expect(wordCalls()[0][1]).toMatchObject({ translation_lang: 'ru', direction: 'forward' })
    expect(request).toHaveBeenCalledWith('PUT', '/auth/translation-prefs/', {
      body: { track: 'en', preferred_translation_lang: 'ru', preferred_direction: 'forward', remember_choice: true },
    })
  })

  it('a remembered choice skips the picker', async () => {
    prefs.current = { preferred_translation_lang: 'de', preferred_direction: 'reverse', remember_choice: true }
    renderAt('/play/speed?source=daily')
    await waitFor(() => expect(wordCalls().length).toBe(1))
    expect(screen.queryByText('Qaysi tilga tarjima qilinsin?')).toBeNull()
    expect(wordCalls()[0][1]).toMatchObject({ translation_lang: 'de', direction: 'reverse' })
  })

  it('never for a definition game or Der·Die·Das', async () => {
    renderAt('/play/match?source=level&level=A1')
    await waitFor(() => expect(wordCalls().length).toBe(1))
    expect(screen.queryByText('Qaysi tilga tarjima qilinsin?')).toBeNull()
    expect(screen.queryByTestId('lang-chip')).toBeNull()
    expect(get.mock.calls.some((c) => c[0] === '/auth/translation-prefs/')).toBe(false)
  })

  it('never for decks: the deck language is used', async () => {
    renderAt('/play/speed?source=deck&id=7')
    await waitFor(() => expect(wordCalls().length).toBe(1))
    expect(screen.queryByText('Qaysi tilga tarjima qilinsin?')).toBeNull()
    expect(wordCalls()[0][1]).toMatchObject({ source: 'deck', translation_lang: undefined })
  })

  it('the header chip changes the language and restarts the round', async () => {
    renderAt('/play/speed?source=daily&tl=ru&dir=forward')
    const chip = await screen.findByTestId('lang-chip')
    expect(chip.textContent).toContain('EN → RU')
    await waitFor(() => expect(wordCalls().length).toBe(1))
    fireEvent.click(chip)
    fireEvent.click(await screen.findByRole('button', { name: /O'zbekcha/ }))
    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: /Boshlash/ })[0])
    })
    await waitFor(() => expect(wordCalls().length).toBe(2))
    expect(wordCalls()[1][1]).toMatchObject({ translation_lang: 'uz' })
    expect((await screen.findByTestId('lang-chip')).textContent).toContain('EN → UZ')
  })
})
