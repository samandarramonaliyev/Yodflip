import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useReducer } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Results, RoundComplete } from '../components/Results'
import MatchGame, { ROUND_END_MS } from './MatchGame'
import { accuracyOf, createSession, sessionReducer, totals } from './session'
import type { GameItem, GameOutcome } from './types'

vi.mock('../lib/fx', () => ({ burst: vi.fn(), feedbackCorrect: vi.fn(), feedbackWrong: vi.fn(), feedbackWin: vi.fn() }))

const item = (k: string): GameItem => ({
  key: k,
  word_id: null,
  term: `word-${k}`,
  word: `word-${k}`,
  article: '',
  definition: `definition of ${k}`,
  translation: `uz-${k}`,
  pos: '',
  example: '',
  example_uz: '',
})

/** Solve a Match board. Math.random is pinned so both areas keep their input order. */
function solveBoard(n: number) {
  const words = screen.getAllByRole('button', { name: 'Yopiq karta' }).slice(0, n)
  const defs = screen.getAllByRole('button', { name: 'Yopiq karta' }).slice(n, 2 * n)
  for (let i = 0; i < n; i++) {
    fireEvent.click(words[i])
    fireEvent.click(defs[i])
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.999) // shuffle() keeps order
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Match Game end of round', () => {
  it('finishes ~600ms after the last match, exactly once, even if the parent re-renders', () => {
    const items = [item('a'), item('b'), item('c'), item('d')]
    const onFinish = vi.fn()
    const { rerender } = render(<MatchGame items={items} track="en" reverse={false} onFinish={onFinish} />)
    solveBoard(4)
    // Parent re-renders with a NEW onFinish function while the end timer is pending (the old bug).
    const onFinish2 = vi.fn()
    rerender(<MatchGame items={items} track="en" reverse={false} onFinish={onFinish2} />)
    expect(onFinish).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(ROUND_END_MS + 50))
    const calls = onFinish.mock.calls.length + onFinish2.mock.calls.length
    expect(calls).toBe(1)
    const outcome: GameOutcome = (onFinish2.mock.calls[0] || onFinish.mock.calls[0])[0]
    expect(outcome.results).toHaveLength(4)
    expect(outcome.results.every((r) => r.correct)).toBe(true)
    expect(outcome.flips).toBe(8)
    act(() => vi.advanceTimersByTime(5000))
    expect(onFinish.mock.calls.length + onFinish2.mock.calls.length).toBe(1)
  })

  it('never leaves dashed placeholders on the board', () => {
    const { container } = render(<MatchGame items={[item('a'), item('b'), item('c'), item('d')]} track="en" reverse={false} onFinish={vi.fn()} />)
    solveBoard(4)
    act(() => vi.advanceTimersByTime(1000))
    expect(container.querySelector('.border-dashed')).toBeNull()
  })
})

/** Minimal harness mirroring the Play runner: session machine + game + end screens. */
function Harness({ rounds }: { rounds: GameItem[][] }) {
  const [s, dispatch] = useReducer(sessionReducer, createSession(rounds))
  const last = s.stats[s.stats.length - 1]
  return (
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <div data-testid="status">{s.status}</div>
      {s.status === 'playing' && (
        <>
          <div>{`round ${s.index + 1} of ${s.rounds.length}`}</div>
          <MatchGame
            key={`${s.playId}-${s.index}`}
            items={s.rounds[s.index]}
            track="en"
            reverse={false}
            onFinish={(o) => dispatch({ type: 'ROUND_DONE', results: o.results, durationMs: o.durationMs, flips: o.flips })}
          />
        </>
      )}
      {s.status === 'round_complete' && (
        <RoundComplete round={last.round} total={s.rounds.length} durationMs={last.durationMs} flips={last.flips} accuracy={accuracyOf(last.results)} xp={0} saving={false} onNext={() => dispatch({ type: 'NEXT_ROUND' })} />
      )}
      {s.status === 'game_complete' &&
        (() => {
          const sum = totals(s)
          return (
            <Results track="en" durationMs={sum.durationMs} flips={sum.flips} accuracy={sum.accuracy} xp={0} saving={false} missed={sum.missed} onNewGame={() => dispatch({ type: 'RESTART', rounds })} otherSetTo="/levels" />
          )
        })()}
    </MemoryRouter>
  )
}

describe('Match Game round flow', () => {
  it('round_complete between rounds, game_complete after the last one, result screen with all buttons', () => {
    const rounds = [
      [item('a'), item('b'), item('c'), item('d')],
      [item('e'), item('f'), item('g'), item('h')],
    ]
    render(<Harness rounds={rounds} />)
    expect(screen.getByText('round 1 of 2')).toBeTruthy()

    // Round 1: one miss, then solve.
    const cards = screen.getAllByRole('button', { name: 'Yopiq karta' })
    fireEvent.click(cards[0])
    fireEvent.click(cards[5]) // definition of b → miss on word-a
    act(() => vi.advanceTimersByTime(1300))
    solveBoard(4)
    act(() => vi.advanceTimersByTime(ROUND_END_MS + 50))
    expect(screen.getByTestId('status').textContent).toBe('round_complete')
    expect(screen.getByTestId('round-complete')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Bosh sahifa/ })).toBeTruthy()

    // Next round loads new cards and the header updates.
    fireEvent.click(screen.getByRole('button', { name: /Keyingi raund/ }))
    expect(screen.getByText('round 2 of 2')).toBeTruthy()
    solveBoard(4)
    act(() => vi.advanceTimersByTime(ROUND_END_MS + 50))

    expect(screen.getByTestId('status').textContent).toBe('game_complete')
    expect(screen.getByTestId('game-results')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Yangi o'yin/ })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Boshqa to'plam/ }).getAttribute('href')).toBe('/levels')
    expect(screen.getByRole('link', { name: /Bosh sahifa/ }).getAttribute('href')).toBe('/')
    expect(screen.getByRole('button', { name: /Xatolarni yodlashga qo'shish/ })).toBeTruthy()
    expect(screen.getByText('word-a')).toBeTruthy() // missed words list
    expect(screen.getByTestId('stat-Ochishlar').textContent).toContain('18') // 2 + 8 + 8 flips

    // "Yangi o'yin" restarts from round 1.
    fireEvent.click(screen.getByRole('button', { name: /Yangi o'yin/ }))
    expect(screen.getByTestId('status').textContent).toBe('playing')
    expect(screen.getByText('round 1 of 2')).toBeTruthy()
  })

  it('a perfect game shows no "add missed" button', () => {
    render(<Harness rounds={[[item('a'), item('b'), item('c'), item('d')]]} />)
    solveBoard(4)
    act(() => vi.advanceTimersByTime(ROUND_END_MS + 50))
    expect(screen.getByTestId('status').textContent).toBe('game_complete')
    expect(screen.queryByRole('button', { name: /Xatolarni yodlashga/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Yangi o'yin/ })).toBeTruthy()
  })
})
