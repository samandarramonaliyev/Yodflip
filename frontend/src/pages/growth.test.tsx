// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setTelegramProtection, watermark } from '../lib/examGuard'
import { useApp } from '../store/app'
import DuelPage from './DuelPage'
import ExamPage from './ExamPage'
import ExamSim from './ExamSim'
import WordStudy from './WordStudy'

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

  const simQ = (index: number) => ({ index, kind: 'translation', prompt: `word${index}`, options: ['a', 'b', 'c', 'd'] })
  const simResult = { score: 1, total: 2, percent: 50, xp: 5, xp_total: 5, streak: 1, late: false, duration_ms: 5000, weak_topics: ['t1'], topics: [{ slug: 't1', emoji: '🍎', name: names('Food'), correct: 1, total: 2, percent: 50, weak: true }], review: [], terminated: false, violations: [] as { kind: string; at: string }[] }
  let violations = 0
  async function startSim() {
    violations = 0
    handler = (method, path, body) => {
      if (path.endsWith('/submit/')) return simResult
      if (path.endsWith('/answer/')) return body.index === 0 ? { done: false, question: simQ(1) } : { done: true, question: null }
      if (path.endsWith('/violation/')) {
        violations++
        const terminated = violations >= 3
        return { count: violations, max: 3, terminated, result: terminated ? { ...simResult, xp: 0, terminated, violations: [1, 2, 3].map(() => ({ kind: 'copy', at: '' })) } : null }
      }
      if (method === 'POST') return { id: 7, pack: 'mini', name: names('Mini pack'), time_limit: 600, total: 2, max_violations: 3, question: simQ(0) }
      return pack
    }
    page('/exams/mini/simulation', '/exams/:slug/simulation', <ExamSim />)
    await screen.findByText('Mini pack')
    fireEvent.click(screen.getByText('Start'))
    await screen.findByText('word0')
  }

  it('simulation: one question at a time, weak topics are offered', async () => {
    await startSim()
    expect(screen.queryByText('word1')).toBeNull()
    expect(screen.getByText(/10:00|9:59/)).toBeTruthy()
    fireEvent.click(screen.getByText('b'))
    fireEvent.click(screen.getByText('Next'))
    await screen.findByText('word1')
    fireEvent.click(screen.getByText('c'))
    fireEvent.click(screen.getByText(/Finish/))
    await screen.findByTestId('sim-result')
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/submit/')).length).toBe(1))
    expect(calls.filter((c) => c.path.endsWith('/answer/')).map((c) => c.body)).toEqual([
      { index: 0, choice: 1 },
      { index: 1, choice: 2 },
    ])
    expect(screen.getByText(/Practise weak topics/).closest('a')!.getAttribute('href')).toBe('/play/flashcards?source=examreview&pack=mini&topic=t1')
  })

  const prevented = (type: string, target: EventTarget = document.body) => {
    const e = new Event(type, { bubbles: true, cancelable: true })
    act(() => void target.dispatchEvent(e))
    return e.defaultPrevented
  }

  it('protection: copy and context menu are blocked only during the exam', async () => {
    expect(prevented('copy')).toBe(false)
    await startSim()
    expect(document.body.classList.contains('exam-mode')).toBe(true)
    for (const type of ['copy', 'contextmenu', 'dragstart', 'selectstart', 'paste']) expect(prevented(type)).toBe(true)
    const key = new KeyboardEvent('keydown', { key: 's', ctrlKey: true, cancelable: true, bubbles: true })
    window.dispatchEvent(key)
    expect(key.defaultPrevented).toBe(true)
    expect(screen.getByTestId('watermark')).toBeTruthy()
    expect(decodeURIComponent(watermark('Ali #7 · 2026'))).toContain('#7')
    cleanup()
    expect(document.body.classList.contains('exam-mode')).toBe(false)
    for (const type of ['copy', 'contextmenu']) expect(prevented(type)).toBe(false)
  })

  it('protection: overlay + warning on a tab switch, the 3rd violation finishes the exam', async () => {
    await startSim()
    const now = vi.spyOn(Date, 'now')
    const base = 5_000_000_000_000
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    now.mockReturnValue(base)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('blur')) // the same switch: counted once
    })
    expect(screen.getByTestId('exam-overlay').textContent).toContain('Tap to return')
    expect(screen.queryByText('word0')).toBeNull()
    await screen.findByText(/\(1\/3\)/)
    fireEvent.click(screen.getByTestId('exam-overlay'))
    expect(screen.queryByTestId('exam-overlay')).toBeNull()
    now.mockReturnValue(base + 5000)
    act(() => void window.dispatchEvent(new KeyboardEvent('keyup', { key: 'PrintScreen' })))
    await screen.findByText(/\(2\/3\)/)
    now.mockReturnValue(base + 10000)
    prevented('copy')
    await screen.findByTestId('terminated')
    expect(screen.getByTestId('violations').textContent).toContain('3')
    expect(calls.filter((c) => c.path.endsWith('/violation/')).map((c) => c.body.kind)).toEqual(['tab_switch', 'printscreen', 'copy'])
    expect(document.body.classList.contains('exam-mode')).toBe(false)
    now.mockRestore()
    Reflect.deleteProperty(document, 'hidden')
  })

  it('Telegram capture protection is feature-detected', () => {
    expect(setTelegramProtection(true, undefined)).toBe(false)
    expect(setTelegramProtection(true, { version: '6.0' })).toBe(false)
    const boom = { enableScreenCaptureProtection: () => { throw new Error('unsupported') }, disableScreenCaptureProtection: () => undefined } // prettier-ignore
    expect(setTelegramProtection(true, boom)).toBe(false)
    const log: string[] = []
    const ok = { enableScreenCaptureProtection: () => log.push('on'), disableScreenCaptureProtection: () => log.push('off') }
    expect(setTelegramProtection(true, ok) && setTelegramProtection(false, ok)).toBe(true)
    expect(log).toEqual(['on', 'off'])
  })
})

describe('word list', () => {
  const word = (n: number) => ({ id: n, term: `word${n}`, word: `word${n}`, article: '', pos: 'noun', definition: 'd', translation: `soz${n}`, translation_uz: `soz${n}`, example: `Ex ${n}.`, example_tr: `Misol ${n}.`, topic: 'food', learned: n === 1, want: false, userword_id: null })
  it('shows a lesson, hides and reveals, stars, switches language, offers flashcards', async () => {
    handler = (method, path) => {
      if (path.includes('translation-prefs')) return { en: { track: 'en', preferred_translation_lang: 'ru', preferred_direction: 'forward', remember_choice: true } }
      if (method === 'POST') return { id: 99 }
      return { track: 'en', lang: 'ru', lesson: 1, lessons: 5, lesson_size: 20, total: 100, topics: [], words: [word(1), word(2)] }
    }
    page('/levels/A1/words', '/levels/:level/words', <WordStudy />)
    await screen.findByText('word1')
    expect(screen.getAllByText('Lesson 2: 21–40').length).toBe(2)
    expect(screen.getAllByTestId('learned-badge').length).toBe(1)
    expect(screen.getByTestId('study-note')).toBeTruthy()
    expect(screen.getByTestId('lesson-flashcards').getAttribute('href')).toBe('/play/flashcards?source=lesson&level=A1&ids=1,2&tl=ru')
    const [hideTr, hideWord] = screen.getAllByRole('switch')
    fireEvent.click(hideTr)
    expect(screen.queryByText('soz1')).toBeNull()
    fireEvent.click(screen.getAllByTestId('study-row')[0])
    expect(screen.getByText('soz1')).toBeTruthy()
    expect(screen.queryByText('soz2')).toBeNull()
    fireEvent.click(hideWord)
    expect(screen.queryByText('word1')).toBeNull()
    expect(screen.getByText('soz2')).toBeTruthy()
    fireEvent.click(screen.getAllByLabelText('Add to Want to learn')[0])
    await waitFor(() => expect(calls.some((c) => c.path === '/words/lists/want/add/' && c.body.word_id === 1)).toBe(true))
    fireEvent.click(screen.getByText(/DE$/))
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body.preferred_translation_lang).toBe('de'))
    expect(calls.find((c) => c.method === 'PUT')?.body.remember_choice).toBe(true)
  })
})
