import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SpeedMatch from '../games/SpeedMatch'
import type { GameItem } from '../games/types'
import type { LevelProgress } from '../lib/types'
import { LevelComplete, LevelRoundSummary } from './LevelProgress'

vi.mock('../lib/fx', () => ({ burst: vi.fn(), feedbackCorrect: vi.fn(), feedbackWrong: vi.fn(), feedbackWin: vi.fn() }))

const prog = (found: number, total = 100, level: LevelProgress['level'] = 'A1'): LevelProgress => {
  const target = Math.ceil(total * 0.7)
  return {
    level,
    total,
    found,
    learned: found,
    remaining: total - found,
    percent: Math.floor((100 * found) / total),
    unlock_target: target,
    to_unlock: Math.max(0, target - found),
    unlocked: true,
    completed: found >= total,
  }
}

const wrap = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>)

afterEach(cleanup)

describe('level round results', () => {
  it('shows new words, the updated count and what is left to unlock', () => {
    wrap(<LevelRoundSummary before={prog(34)} after={prog(37)} newFound={3} />)
    expect(screen.getByTestId('new-found').textContent).toBe("+3 yangi so'z")
    expect(screen.getByTestId('level-count').textContent).toBe("37 / 100 so'z")
    expect(screen.getByTestId('unlock-text').textContent).toBe("Keyingi daraja uchun yana 33 ta so'z")
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('37')
  })

  it('while saving shows the old progress and a placeholder', () => {
    wrap(<LevelRoundSummary before={prog(10, 150, 'A2')} after={null} newFound={null} />)
    expect(screen.getByTestId('new-found').textContent).toBe('…')
    expect(screen.getByTestId('level-count').textContent).toBe("10 / 150 so'z")
    expect(screen.getByTestId('unlock-text').textContent).toBe("Keyingi daraja uchun yana 95 ta so'z")
  })

  it('announces the unlock when the round crosses 70%', () => {
    wrap(<LevelRoundSummary before={prog(138, 200, 'B1')} after={prog(141, 200, 'B1')} newFound={3} />)
    expect(screen.getByText(/B2 darajasi ochildi!/)).toBeTruthy()
  })

  it('no new words: says so without a bonus', () => {
    wrap(<LevelRoundSummary before={prog(50)} after={prog(50)} newFound={0} />)
    expect(screen.getByTestId('new-found').textContent).toBe("Yangi so'z yo'q")
  })

  it('completion screen: badge, one-time bonus, next level and review', () => {
    wrap(<LevelComplete level="A1" bonusXp={200} />)
    expect(screen.getByText('Daraja yakunlandi 🎉')).toBeTruthy()
    expect(screen.getByText(/\+200 XP/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /A2/ }).getAttribute('href')).toBe('/levels/A2')
    expect(screen.getByRole('link', { name: /takrorlash/i }).getAttribute('href')).toBe('/play/speed?source=levelreview&level=A1')
    cleanup()
    wrap(<LevelComplete level="C1" bonusXp={0} />)
    expect(screen.queryByText(/XP/)).toBeNull()
    expect(screen.queryByRole('link', { name: /o'tish/ })).toBeNull()
  })

  it('filler cards show the "takror" badge', () => {
    const item = (k: string, filler: boolean): GameItem => ({
      key: k,
      word_id: 1,
      term: k,
      word: k,
      article: '',
      definition: '',
      translation: `uz-${k}`,
      pos: '',
      example: '',
      example_uz: '',
      is_filler: filler,
    })
    vi.spyOn(Math, 'random').mockReturnValue(0.999)
    wrap(<SpeedMatch items={[item('a', true), item('b', false), item('c', false)]} track="en" reverse={false} onFinish={vi.fn()} />)
    expect(screen.getByTestId('filler-badge').textContent).toContain('takror')
    vi.restoreAllMocks()
  })
})
