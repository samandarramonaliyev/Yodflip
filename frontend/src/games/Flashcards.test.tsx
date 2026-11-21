import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
vi.mock('../lib/api', () => ({ api: { post: (...a: unknown[]) => post(...a) } }))
vi.mock('../lib/fx', () => ({ burst: vi.fn(), feedbackCorrect: vi.fn(), feedbackWrong: vi.fn(), feedbackWin: vi.fn() }))

import Flashcards from './Flashcards'
import type { GameItem } from './types'

const item = (k: string, over: Partial<GameItem> = {}): GameItem => ({
  key: k,
  word_id: null,
  term: `der Hund${k}`,
  word: `Hund${k}`,
  article: 'der',
  definition: '',
  translation: `собака ${k}`,
  translation_lang: 'ru',
  pos: 'noun',
  example: 'Der Hund bellt.',
  example_uz: '',
  ...over,
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

let n = 0
post.mockImplementation(async (path: string) => (path.includes('answer') ? { answer_id: ++n } : { undone: true }))

describe('Flashcards', () => {
  it('shows the translation first; answer buttons only after the first flip', () => {
    render(<Flashcards items={[item('c11'), item('c12')]} track="de" reverse={false} onFinish={vi.fn()} />)
    expect(screen.getByTestId('card-front').textContent).toContain('собака c11')
    expect(screen.queryByTestId('answer-buttons')).toBeNull()
    fireEvent.keyDown(window, { key: 'ArrowRight' }) // ignored before flipping
    expect(post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('flash-card'))
    expect(screen.getByTestId('flash-card').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('answer-buttons')).toBeTruthy()
    const back = screen.getByTestId('card-back')
    expect(back.querySelector('.text-sky-600')?.textContent).toBe('der ') // article in colour
    expect(back.textContent).toContain('noun')
    fireEvent.click(screen.getByTestId('flash-card')) // flip back: unlimited, buttons stay
    expect(screen.getByTestId('flash-card').getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByTestId('answer-buttons')).toBeTruthy()
  })

  it('Topdim / Topa olmadim save each answer (deck card id included), progress and finish', async () => {
    const onFinish = vi.fn()
    render(<Flashcards items={[item('c11'), item('c12')]} track="de" reverse={false} onFinish={onFinish} />)
    expect(screen.getByTestId('flash-progress').textContent).toBe('1 / 2')
    fireEvent.keyDown(window, { code: 'Space' })
    fireEvent.click(screen.getByRole('button', { name: /Topdim/ }))
    expect(post).toHaveBeenCalledWith('/words/flash/answer/', expect.objectContaining({ known: true, card_id: 11, track: 'de' }))
    await waitFor(() => expect(screen.getByTestId('flash-progress').textContent).toBe('2 / 2'))
    expect(screen.queryByTestId('answer-buttons')).toBeNull() // new card: flip first again
    fireEvent.click(screen.getByTestId('flash-card'))
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(post).toHaveBeenLastCalledWith('/words/flash/answer/', expect.objectContaining({ known: false, card_id: 12 }))
    expect(onFinish).toHaveBeenCalledTimes(1)
    expect(onFinish.mock.calls[0][0].results.map((r: { correct: boolean }) => r.correct)).toEqual([true, false])
  })

  it('undo goes back and restores the previous state on the server', async () => {
    render(<Flashcards items={[item('w1', { word_id: 5 }), item('w2', { word_id: 6 })]} track="de" reverse={false} onFinish={vi.fn()} />)
    fireEvent.click(screen.getByTestId('flash-card'))
    fireEvent.click(screen.getByRole('button', { name: /Topa olmadim/ }))
    expect(post).toHaveBeenCalledWith('/words/flash/answer/', expect.objectContaining({ known: false, card_id: null, item: expect.objectContaining({ word_id: 5 }) }))
    await waitFor(() => expect(screen.getByTestId('flash-progress').textContent).toBe('2 / 2'))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Bekor qilish/ }))
    })
    await waitFor(() => expect(post).toHaveBeenLastCalledWith('/words/flash/undo/', { answer_id: expect.any(Number) }))
    await waitFor(() => expect(screen.getByTestId('flash-progress').textContent).toBe('1 / 2'))
  })

  it('"Teskari" shows the foreign word first', () => {
    render(<Flashcards items={[item('c1')]} track="de" reverse={false} onFinish={vi.fn()} />)
    fireEvent.click(screen.getByRole('switch', { name: /Teskari/ }))
    expect(screen.getAllByTestId('card-back')[0].closest('.flip-face')?.classList.contains('flip-back')).toBe(false)
  })
})
