// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { countdown, resultKey, secondsLeft, type LeagueState } from '../lib/league'
import { useApp } from '../store/app'
import League from './League'

const silver = { code: 'silver', order: 1, emoji: '🥈', color: '#C0C0C0', name: { uz: 'Kumush', en: 'Silver', ru: 'Серебро' } }
const state = (over: Partial<LeagueState> = {}): LeagueState => ({
  tiers: [silver],
  tier: silver,
  trophies: 0,
  week: { start: '2026-03-02', ends_at: '2026-03-09T00:00:00+05:00', seconds_left: 3 * 86400 + 5 * 3600 + 120 },
  joined: true,
  group: [
    { rank: 1, user_id: 1, name: 'A', avatar_url: '', xp: 90, is_me: false, zone: 'promote' },
    { rank: 2, user_id: 2, name: 'B', avatar_url: '', xp: 50, is_me: false, zone: 'safe' },
    { rank: 3, user_id: 3, name: 'Men', avatar_url: '', xp: 10, is_me: true, zone: 'demote' },
  ],
  zones: { promote: 1, demote: 1, size: 3, top_tier: false },
  me: { rank: 3, xp: 10, zone: 'demote', need_xp: 41 },
  last_result: null,
  ...over,
})

let calls = 0
let next: LeagueState
beforeEach(() => {
  calls = 0
  next = state()
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.stubGlobal('fetch', async () => {
    calls++
    return new Response(JSON.stringify(next), { status: 200 })
  })
  useApp.setState({ lang: 'uz' })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('league helpers', () => {
  it('counts down and keeps ticking between refetches', () => {
    expect(countdown(3 * 86400 + 5 * 3600 + 61)).toEqual({ days: 3, hours: 5, minutes: 1 })
    expect(secondsLeft({ week: { start: '', ends_at: '', seconds_left: 100 } }, 1_000, 31_000)).toBe(70)
    expect(secondsLeft({ week: { start: '', ends_at: '', seconds_left: 10 } }, 0, 60_000)).toBe(0)
    expect(resultKey({ week: '', tier: silver, new_tier: null, rank: 1, xp: 1, result: 'trophy' })).toBe('league.result_trophy')
  })
})

describe('League page', () => {
  it('shows tier, countdown, my row highlighted, zones and the danger hint', async () => {
    render(
      <MemoryRouter>
        <League />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Kumush ligasi')).toBeTruthy()
    expect(screen.getByTestId('countdown').textContent).toBe('3 kun 5 soat qoldi')
    const rows = screen.getByTestId('league-group').querySelectorAll('[data-zone]')
    expect([...rows].map((r) => r.getAttribute('data-zone'))).toEqual(['promote', 'safe', 'demote'])
    expect(rows[2].className).toContain('ring-primary')
    expect(screen.getByTestId('danger').textContent).toContain('41 XP')
  })

  it('refetches every 30 s and on focus (live updates without websockets)', async () => {
    render(
      <MemoryRouter>
        <League />
      </MemoryRouter>,
    )
    await screen.findByText('Kumush ligasi')
    const first = calls
    next = state({ group: state().group.map((r) => (r.is_me ? { ...r, xp: 99 } : r)) })
    await act(async () => {
      vi.advanceTimersByTime(30_000)
    })
    expect(calls).toBeGreaterThan(first)
    const afterTimer = calls
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })
    expect(calls).toBeGreaterThan(afterTimer)
    expect(await screen.findByText('99 XP')).toBeTruthy()
  })

  it('explains how to enter when there is no XP this week', async () => {
    next = state({ joined: false, group: [], zones: null, me: null })
    render(
      <MemoryRouter>
        <League />
      </MemoryRouter>,
    )
    expect(await screen.findByText("Bu hafta ligaga hali kirmadingiz")).toBeTruthy()
  })
})
