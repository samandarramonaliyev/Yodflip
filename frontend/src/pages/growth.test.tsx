// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useApp } from '../store/app'
import DuelPage from './DuelPage'
import ExamPage from './ExamPage'
import ExamSim from './ExamSim'

vi.mock('canvas-confetti', () => ({ default: () => null })) // no canvas in jsdom

type Handler = (method: string, path: string, body: Record<string, unknown>) => unknown
let handler: Handler
const calls: { method: string; path: string; body: Record<string, unknown>; headers: Record<string, string> }[] = []

beforeEach(() => {
  calls.length = 0
  window.scrollTo = () => undefined
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const path = String(url).replace('/api', '').split('?')[0]
    const body = init.body ? JSON.parse(String(init.body)) : {}
    calls.push({ method: init.method!, path, body, headers: init.headers as Record<string, string> })
    const data = handler(init.method!, path, body)
    return new Response(JSON.stringify(data), { status: 200 })
  })
  localStorage.clear()
  useApp.setState({ user: null, lang: 'en', track: 'en' })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

function page(path: string, route: string, el: JSX.Element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={el} />
        <Route path="*" element={<div>elsewhere</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const duel = {
  code: 'abc',
  track: 'en',
  mode: 'speed',
  source: 'level',
  source_ref: 'A1',
  source_label: 'A1',
  translation_lang: 'uz',
  status: 'open',
  total: 2,
  expires_at: '2030-01-01T00:00:00Z',
  web_link: 'https://x/duel/abc',
  telegram_link: 'https://t.me/bot/app?startapp=duel_abc',
  challenger: { name: 'Ali', avatar_url: '' },
  creator: { name: 'Ali', avatar_url: '', is_guest: false, finished: true, role: 'creator', score: 1, time_ms: 9000, accuracy: 50 },
  opponent: null,
  is_draw: false,
  me: null,
}
const me = { role: 'opponent', finished: false, is_guest: true, answered: [], score: 0, time_ms: 0 }

describe('duel page', () => {
  it('a guest plays, wins and is invited to save the result', async () => {
    const questions = [
      { index: 0, prompt: 'apple', options: ['olma', 'non', 'suv', 'choy'] },
      { index: 1, prompt: 'bread', options: ['olma', 'non', 'suv', 'choy'] },
    ]
    handler = (_, path, body) => {
      if (path.endsWith('/start/')) return { ...duel, me, questions, guest_token: 'tok' }
      if (path.endsWith('/answer/')) return { index: body.index, correct: true, correct_index: body.choice, answered: 1 }
      if (path.endsWith('/finish/'))
        return {
          ...duel,
          status: 'completed',
          me: { ...me, finished: true, score: 2 },
          opponent: { ...duel.creator, name: '', is_guest: true, role: 'opponent', score: 2, accuracy: 100 },
          outcome: 'win',
          xp: 30,
          review: [{ term: 'apple', answer: 'olma', correct: true }],
        }
      return duel
    }
    page('/duel/abc', '/duel/:code', <DuelPage />)
    expect(await screen.findByText('Ali challenges you!')).toBeTruthy()
    expect(screen.getByText(/To beat: 1\/2, 9s/)).toBeTruthy()
    fireEvent.click(screen.getByText('Start'))
    for (const [word, answer] of [
      ['apple', 'olma'],
      ['bread', 'non'],
    ]) {
      await screen.findByText(word)
      await act(() => new Promise((r) => setTimeout(r, 400)))
      fireEvent.click(screen.getByText(answer))
      await act(() => new Promise((r) => setTimeout(r, 700)))
    }
    await screen.findByTestId('duel-result')
    expect(screen.getByText('You won!')).toBeTruthy()
    expect(screen.getByText('Save the result').closest('a')!.getAttribute('href')).toBe('/login?next=/duel/abc')
    const answers = calls.filter((c) => c.path.endsWith('/answer/'))
    expect(answers.map((c) => [c.body.index, c.body.choice])).toEqual([
      [0, 0],
      [1, 1],
    ])
    expect(answers[0].headers['X-Duel-Guest']).toBe('tok')
    expect(Number(answers[0].body.client_ms)).toBeGreaterThanOrEqual(300)
  })

  it('the creator gets a share card', async () => {
    handler = () => ({ ...duel, me: { ...me, role: 'creator', finished: true, is_guest: false, score: 2, time_ms: 42000 }, review: [] })
    page('/duel/abc', '/duel/:code', <DuelPage />)
    await screen.findByTestId('duel-share')
    expect(screen.getByText('🃏 Ali challenges you to a Yodflip duel! Their result: 2/2, 42s. Can you beat it?')).toBeTruthy()
  })
})

const names = (x: string) => ({ uz: x, en: x, ru: x })
const pack = {
  level: 'mini',
  exam: 'mini',
  slug: 'mini',
  track: 'en',
  emoji: '📘',
  name: names('Mini pack'),
  total: 20,
  found: 5,
  learned: 5,
  remaining: 15,
  percent: 25,
  unlock_target: 0,
  to_unlock: 0,
  unlocked: true,
  completed: false,
  topics: [{ slug: 't1', emoji: '🍎', name: names('Food'), total: 20, found: 5, percent: 25 }],
  next_topic: 't1',
  goal: null,
  last_simulation: null,
}

describe('exam pack', () => {
  it('shows the disclaimer, progress and the games of a topic', async () => {
    handler = () => pack
    page('/exams/mini', '/exams/:slug', <ExamPage />)
    expect((await screen.findByTestId('exam-disclaimer')).textContent).toContain('Unofficial preparation pack')
    fireEvent.click(screen.getByText('Continue'))
    expect(await screen.findByText('Speed Match')).toBeTruthy()
    expect(screen.getByText('Falling Words')).toBeTruthy()
  })

  it('simulation: answers are sent once, weak topics are offered', async () => {
    const questions = [0, 1].map((index) => ({ index, kind: 'translation', prompt: `word${index}`, options: ['a', 'b', 'c', 'd'] }))
    handler = (method, path) => {
      if (path.endsWith('/submit/'))
        return {
          score: 1,
          total: 2,
          percent: 50,
          xp: 5,
          xp_total: 5,
          streak: 1,
          late: false,
          duration_ms: 5000,
          weak_topics: ['t1'],
          topics: [{ slug: 't1', emoji: '🍎', name: names('Food'), correct: 1, total: 2, percent: 50, weak: true }],
          review: [],
        }
      if (method === 'POST') return { id: 7, pack: 'mini', name: names('Mini pack'), time_limit: 600, questions }
      return pack
    }
    page('/exams/mini/simulation', '/exams/:slug/simulation', <ExamSim />)
    await screen.findByText('Mini pack')
    fireEvent.click(screen.getByText('Start'))
    await screen.findByText('word0')
    expect(screen.getByText(/10:00|9:59/)).toBeTruthy()
    fireEvent.click(screen.getByText('b'))
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('c'))
    fireEvent.click(screen.getByText(/Finish/))
    await screen.findByTestId('sim-result')
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/submit/')).length).toBe(1))
    expect(calls.find((c) => c.path.endsWith('/submit/'))!.body.answers).toEqual([
      { index: 0, choice: 1 },
      { index: 1, choice: 2 },
    ])
    expect(screen.getByText(/Practise weak topics/).closest('a')!.getAttribute('href')).toBe('/play/flashcards?source=examreview&pack=mini&topic=t1')
  })
})
