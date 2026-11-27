// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { otherSetPath } from '../games/session'
import { assignmentPlayPath, classStartPath, sortStudents, timeLeft, type Assignment, type StudentRow } from '../lib/classes'
import { useApp } from '../store/app'
import ClassPage from './ClassPage'
import JoinClass from './JoinClass'

type Handler = (method: string, path: string, body: Record<string, unknown>) => unknown
let handler: Handler
const calls: { method: string; path: string; body: Record<string, unknown> }[] = []

beforeEach(() => {
  calls.length = 0
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const path = String(url).replace('/api', '').split('?')[0]
    const body = init.body ? JSON.parse(String(init.body)) : {}
    calls.push({ method: init.method!, path, body })
    return new Response(JSON.stringify(handler(init.method!, path, body)), { status: 200 })
  })
  useApp.setState({ user: null, lang: 'uz', track: 'en' })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function page(path: string, route: string, el: JSX.Element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={el} />
        <Route path="*" element={<div data-testid="elsewhere">elsewhere</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const assignment: Assignment = {
  id: 9,
  title: 'A1 · 1',
  kind: 'level',
  level: 'A1',
  lesson_from: 1,
  lesson_to: 1,
  exam_slug: '',
  topics: [],
  deck: null,
  deck_name: '',
  word_count: 20,
  target_kind: 'learn_pct',
  target_value: 80,
  starts_on: '2026-01-01',
  due_at: '2099-01-01T00:00:00Z',
  start: { source: 'assignment', id: 9, assignment: 9 },
  progress: { done: 4, total: 20, percent: 20, plays: 1, target_percent: 25, status: 'pending' },
}

const row = (p: Partial<StudentRow>): StudentRow => ({
  id: 1,
  name: 'A',
  avatar_url: '',
  membership: 'active',
  joined_at: '',
  last_active: null,
  words_week: 0,
  words_total: 0,
  accuracy: null,
  streak: 0,
  weekly_xp: 0,
  assignments: {},
  ...p,
})

describe('class helpers', () => {
  it('builds play links with exactly the assignment words and a way back to the class', () => {
    const path = assignmentPlayPath(assignment, 3, 'speed')
    expect(path).toBe('/play/speed?source=assignment&id=9&assignment=9&class=3')
    const deck = { ...assignment, kind: 'deck' as const, start: { source: 'deck' as const, id: 44, assignment: 9 } }
    expect(assignmentPlayPath(deck, 3)).toBe('/play/flashcards?source=deck&id=44&assignment=9&class=3')
    expect(otherSetPath('deck', new URLSearchParams('id=44&class=3'))).toBe('/classes/3')
  })

  it('maps the Telegram start param of a class link', () => {
    expect(classStartPath('class_abc234')).toBe('/join/ABC234')
    expect(classStartPath('class_../x')).toBeNull()
    expect(classStartPath('duel_abc')).toBeNull()
    expect(classStartPath(undefined)).toBeNull()
  })

  it('sorts and searches the student table, pending requests first', () => {
    const rows = [row({ id: 1, name: 'Bek', weekly_xp: 10 }), row({ id: 2, name: 'Ali', weekly_xp: 50 }), row({ id: 3, name: 'Zuhra', membership: 'pending' }), row({ id: 4, name: 'Olim', accuracy: 90 })]
    expect(sortStudents(rows, 'weekly_xp', true).map((r) => r.id)).toEqual([3, 2, 1, 4])
    expect(sortStudents(rows, 'name', false).map((r) => r.name)).toEqual(['Zuhra', 'Ali', 'Bek', 'Olim'])
    expect(sortStudents(rows, 'accuracy', true)[1].name).toBe('Olim') // null accuracy sorts last
    expect(sortStudents(rows, 'name', false, 'be').map((r) => r.name)).toEqual(['Bek'])
  })

  it('counts down to a deadline', () => {
    const now = Date.parse('2026-01-01T00:00:00Z')
    expect(timeLeft('2026-01-04T05:30:00Z', now)).toEqual({ days: 3, hours: 5, minutes: 30, past: false })
    expect(timeLeft('2025-12-31T00:00:00Z', now).past).toBe(true)
  })
})

describe('class pages', () => {
  it('student: joins through the code page after confirming', async () => {
    handler = (method, path) =>
      method === 'GET'
        ? { id: 3, name: '7-A', track: 'en', level: 'A2', description: '', color: '#6C5CE7', teacher: { id: 1, name: 'Ustoz', avatar_url: '' }, students: 12, approval_required: false, membership: null, is_teacher: false }
        : path.includes('join')
          ? { id: 3, membership: 'active' }
          : {}
    page('/join/ABC234', '/join/:code', <JoinClass />)
    expect(await screen.findByText('7-A')).toBeTruthy()
    expect(calls.some((c) => c.method === 'POST')).toBe(false) // nothing happens before the confirm tap
    fireEvent.click(screen.getByTestId('join-btn'))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/classes/join/ABC234/')).toBe(true))
    expect(await screen.findByTestId('elsewhere')).toBeTruthy()
  })

  it('student: sees assignments with progress and opens the game picker', async () => {
    handler = () => ({
      class: { id: 3, name: '7-A', track: 'en', level: '', description: '', color: '#6C5CE7', archived: false, teacher: { id: 1, name: 'Ustoz', avatar_url: '' }, org: null, role: 'student', students: 2, membership: 'active', links: {} },
      assignments: [assignment],
      leaderboard: [{ rank: 1, id: 5, name: 'Men', avatar_url: '', xp: 40, is_me: true }],
    })
    page('/classes/3', '/classes/:id', <ClassPage />)
    expect(await screen.findByText(/4 \/ 20/)).toBeTruthy()
    expect(screen.getByTestId('class-board').textContent).toContain('40 XP')
    fireEvent.click(screen.getByText('Boshlash'))
    expect(await screen.findByTestId('start-sheet')).toBeTruthy()
  })

  it('teacher: dashboard with overview, student table and invite QR', async () => {
    handler = () => ({
      class: { id: 3, name: '7-A', track: 'en', level: '', description: '', color: '#6C5CE7', archived: false, teacher: { id: 1, name: 'Ustoz', avatar_url: '' }, org: null, role: 'teacher', students: 2, join_code: 'ABC234', links: { web: 'https://x/join/ABC234', telegram: 'https://t.me/b/a?startapp=class_ABC234', teacher: 'https://x/teach/T' }, approval_required: false, plan: 'free', limits: { classes: 2, students: 40 }, is_owner: true, co_teachers: [] },
      overview: { students: 2, pending: 1, active_week: 1, avg_progress: 30, completion: 50, assignments: 1 },
      students: [row({ id: 5, name: 'Ali', weekly_xp: 70, assignments: { '9': assignment.progress! } }), row({ id: 6, name: 'Vali', membership: 'pending' })],
      assignments: [assignment],
    })
    page('/classes/3', '/classes/:id', <ClassPage />)
    expect(await screen.findByTestId('overview')).toBeTruthy()
    expect(screen.getByTestId('overview').textContent).toContain('30%')
    const table = screen.getByTestId('students-table')
    expect(table.textContent).toContain('Ali')
    expect(table.textContent).toContain('⏳')
    expect(table.textContent).not.toContain('@')
    fireEvent.click(screen.getByTestId('invite-btn'))
    const sheet = await screen.findByTestId('invite-sheet')
    expect(sheet.textContent).toContain('ABC234')
    expect(sheet.querySelector('svg[aria-label="QR"]')).toBeTruthy()
  })
})
