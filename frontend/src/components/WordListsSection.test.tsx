import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
vi.mock('../lib/api', () => ({ api: { get: (...a: unknown[]) => get(...a), del: vi.fn(), patch: vi.fn() } }))

import { WordListsSection } from './WordListsSection'

const TOTAL = 248
const row = (i: number) => ({ id: i, track: 'en', term: `word${i}`, article: '', translation_uz: `tarjima${i}`, definition: '', box: 5, correct_count: 1, miss_count: 0, want_to_learn: false, is_learned: true, is_missed: false, level: 'A1' })

beforeEach(() => {
  try {
    sessionStorage.clear()
  } catch {
    /* ignore */
  }
  get.mockImplementation(async (path: string, q: Record<string, unknown>) => {
    if (path === '/decks/') return []
    const size = Number(q.page_size)
    const page = Number(q.page)
    const all = q.search ? [row(7)] : Array.from({ length: TOTAL }, (_, i) => row(i + 1))
    const slice = all.slice((page - 1) * size, page * size)
    return { count: all.length, has_more: page * size < all.length, counts: { learned: TOTAL, want: 3, missed: 0 }, results: slice }
  })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const meCalls = () => get.mock.calls.filter((c) => c[0] === '/me/words/')

describe('profile word lists', () => {
  it('collapsed: 6 recent words + the right total; expand pages 30 at a time; search; Yopish collapses', async () => {
    render(
      <MemoryRouter>
        <WordListsSection track="en" />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getAllByTestId('word-chip')).toHaveLength(6))
    expect(meCalls()[0][1]).toMatchObject({ list: 'learned', page_size: 6, page: 1 })
    expect(screen.getByTestId('count-learned').textContent).toBe(`(${TOTAL})`)
    expect(screen.getByTestId('expand').textContent).toContain(`Hammasini ko'rish (${TOTAL})`)

    fireEvent.click(screen.getByTestId('expand'))
    await waitFor(() => expect(screen.getAllByTestId('word-row')).toHaveLength(30))
    expect(meCalls().at(-1)![1]).toMatchObject({ page_size: 30, page: 1 })
    fireEvent.click(screen.getByTestId('load-more'))
    await waitFor(() => expect(screen.getAllByTestId('word-row')).toHaveLength(60))
    expect(meCalls().at(-1)![1]).toMatchObject({ page: 2 })

    fireEvent.change(screen.getByLabelText("So'z yoki tarjima"), { target: { value: 'word7' } })
    await waitFor(() => expect(screen.getAllByTestId('word-row')).toHaveLength(1))
    expect(meCalls().at(-1)![1]).toMatchObject({ search: 'word7' })

    expect(screen.getByTestId('close-top')).toBeTruthy()
    fireEvent.click(screen.getByTestId('close-bottom'))
    await waitFor(() => expect(screen.queryByTestId('expanded')).toBeNull())
    expect(screen.getByTestId('collapsed')).toBeTruthy()
  })

  it('remembers the expanded state per tab', async () => {
    render(
      <MemoryRouter>
        <WordListsSection track="en" />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('expand')).toBeTruthy())
    fireEvent.click(screen.getByTestId('expand'))
    await waitFor(() => expect(screen.getByTestId('expanded')).toBeTruthy())
    fireEvent.click(screen.getByRole('tab', { name: /Yodlanadiganlar/ }))
    await waitFor(() => expect(screen.queryByTestId('expanded')).toBeNull()) // other tab: collapsed
    expect(screen.getByRole('link', { name: /Bu ro'yxatni o'rganish/ }).getAttribute('href')).toBe('/play/flashcards?source=want')
    fireEvent.click(screen.getByRole('tab', { name: /Yodlanganlar/ }))
    await waitFor(() => expect(screen.getByTestId('expanded')).toBeTruthy()) // remembered
  })
})
