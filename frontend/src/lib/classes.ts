/** Classes (teacher mode): API types and pure helpers (play links, table sorting, statuses). */
import type { Track } from '../games/types'

export interface Person {
  id: number
  name: string
  avatar_url: string
}

export type AssignmentStatus = 'done' | 'pending' | 'overdue' | 'upcoming'

export interface AssignmentProgress {
  done: number
  total: number
  percent: number
  plays: number
  target_percent: number
  status: AssignmentStatus
}

export interface Assignment {
  id: number
  title: string
  kind: 'level' | 'exam' | 'deck'
  level: string
  lesson_from: number | null
  lesson_to: number | null
  exam_slug: string
  topics: string[]
  deck: number | null
  deck_name: string
  word_count: number
  target_kind: 'learn_pct' | 'plays'
  target_value: number
  starts_on: string
  due_at: string
  start: { source: 'assignment' | 'deck'; id: number; assignment: number }
  progress?: AssignmentProgress | null
}

export interface ClassInfo {
  id: number
  name: string
  track: Track
  level: string
  description: string
  color: string
  archived: boolean
  teacher: Person
  org: { id: number; name: string } | null
  role: 'teacher' | 'student'
  students: number
  membership?: 'active' | 'pending' | 'left' | 'removed' | null
  open_assignments?: number
  join_code?: string
  links: { web?: string; telegram?: string; teacher?: string }
  approval_required?: boolean
  plan?: string
  limits?: { classes: number; students: number }
  is_owner?: boolean
  co_teachers?: Person[]
}

export interface StudentRow extends Person {
  membership: 'active' | 'pending'
  joined_at: string
  last_active: string | null
  words_week: number
  words_total: number
  accuracy: number | null
  streak: number
  weekly_xp: number
  assignments: Record<string, AssignmentProgress>
}

export interface Overview {
  students: number
  pending: number
  active_week: number
  avg_progress: number
  completion: number
  assignments: number
}

export interface TeacherView {
  class: ClassInfo
  overview: Overview
  students: StudentRow[]
  assignments: Assignment[]
}

export interface BoardRow extends Person {
  rank: number
  xp: number
  is_me: boolean
}

export interface StudentView {
  class: ClassInfo
  assignments: Assignment[]
  leaderboard: BoardRow[]
}

export interface ClassList {
  classes: ClassInfo[]
  limits: { classes: number; students: number }
  owned: number
  orgs: { id: number; name: string }[]
  colors: string[]
}

export interface JoinPreview {
  id: number
  name: string
  track: Track
  level: string
  description: string
  color: string
  teacher: Person
  students: number
  approval_required: boolean
  membership: ClassInfo['membership']
  is_teacher: boolean
}

export interface HardWord {
  term: string
  translation: string
  students: number
  misses: number
}

export interface StudentDetail {
  student: StudentRow
  assignments: Assignment[]
  chart: { date: string; xp: number; correct: number }[]
  mistakes: { term: string; translation: string; misses: number; box: number }[]
  levels: { level: string; percent: number }[]
}

export const isTeacherView = (d: TeacherView | StudentView): d is TeacherView => d.class.role === 'teacher'

export const STATUS_ICON: Record<AssignmentStatus, string> = { done: '✅', pending: '⏳', overdue: '❌', upcoming: '🗓️' }

/** Games a student can open from an assignment ("Boshlash"). */
export const ASSIGNMENT_GAMES = ['flashcards', 'speed', 'builder', 'memory'] as const

/** In-app path that plays exactly the assignment's words; the game reports the assignment id. */
export function assignmentPlayPath(a: Assignment, classId: number, game: string = 'flashcards'): string {
  const q = new URLSearchParams({ source: a.start.source, id: String(a.start.id), assignment: String(a.id), class: String(classId) })
  return `/play/${game}?${q.toString()}`
}

/** The word list of a level assignment (study mode), when there is one. */
export function assignmentWordsPath(a: Assignment): string | null {
  if (a.kind === 'level' && a.level) return `/levels/${a.level}/words${a.lesson_from ? `?lesson=${a.lesson_from}` : ''}`
  if (a.kind === 'exam' && a.exam_slug) return `/exams/${a.exam_slug}/words`
  return null
}

export type SortKey = 'name' | 'last_active' | 'words_week' | 'words_total' | 'accuracy' | 'streak' | 'weekly_xp'

/** Sort + search for the teacher's student table. Pending requests always come first. */
export function sortStudents(rows: StudentRow[], key: SortKey, desc: boolean, search = ''): StudentRow[] {
  const q = search.trim().toLowerCase()
  const list = q ? rows.filter((r) => r.name.toLowerCase().includes(q)) : [...rows]
  const val = (r: StudentRow): string | number => {
    if (key === 'name') return r.name.toLowerCase()
    if (key === 'last_active') return r.last_active ?? ''
    const v = r[key]
    return v === null || v === undefined ? -1 : v
  }
  list.sort((a, b) => {
    if (a.membership !== b.membership) return a.membership === 'pending' ? -1 : 1
    const x = val(a)
    const y = val(b)
    const c = x < y ? -1 : x > y ? 1 : a.name.localeCompare(b.name)
    return desc ? -c : c
  })
  return list
}

/** "3 kun qoldi" style countdown parts until a moment (never negative). */
export function timeLeft(iso: string, now: number = Date.now()): { days: number; hours: number; minutes: number; past: boolean } {
  const ms = new Date(iso).getTime() - now
  const s = Math.max(0, Math.floor(ms / 1000))
  return { days: Math.floor(s / 86400), hours: Math.floor((s % 86400) / 3600), minutes: Math.floor((s % 3600) / 60), past: ms <= 0 }
}

/** Telegram `startapp=class_<code>` → in-app join path. */
export function classStartPath(param: string | null | undefined): string | null {
  const m = /^class_([A-Za-z0-9]{6})$/.exec(param ?? '')
  return m ? `/join/${m[1].toUpperCase()}` : null
}
