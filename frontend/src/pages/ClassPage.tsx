import { Copy, Download, Search, Share2, Trash2, UserPlus } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { QrCode } from '../components/QrCode'
import { Avatar, EmptyState, ErrorState, ProgressBar, Segmented, Sheet, Skeleton, Toggle, toast } from '../components/ui'
import { useT } from '../i18n'
import { api, ApiError } from '../lib/api'
import {
  ASSIGNMENT_GAMES,
  assignmentPlayPath,
  assignmentWordsPath,
  isTeacherView,
  sortStudents,
  STATUS_ICON,
  timeLeft,
  type Assignment,
  type BoardRow,
  type ClassInfo,
  type HardWord,
  type SortKey,
  type StudentView,
  type TeacherView,
} from '../lib/classes'
import type { ExamPackDetail, ExamPackRow } from '../lib/exams'
import { useAsync, useTelegramBack } from '../lib/hooks'
import { shareToTelegram } from '../lib/telegram'
import type { Cefr, Deck } from '../lib/types'
import { useApp } from '../store/app'

const LEVELS: Cefr[] = ['A1', 'A2', 'B1', 'B2', 'C1']

function copy(text: string, done: string) {
  void navigator.clipboard?.writeText(text).then(
    () => toast.ok(done),
    () => toast.err(text),
  )
}

function Deadline({ iso }: { iso: string }) {
  const t = useT()
  const left = timeLeft(iso)
  if (left.past) return <span className="text-error">{t('cls.deadline_passed')}</span>
  return <span>{left.days > 0 ? t('cls.left_days', { d: left.days, h: left.hours }) : t('cls.left_hours', { h: left.hours, m: left.minutes })}</span>
}

function targetText(t: (k: string, v?: Record<string, string | number>) => string, a: Assignment) {
  return a.target_kind === 'plays' ? t('cls.target_plays', { n: a.target_value }) : t('cls.target_learn', { n: a.target_value })
}

/* ------------------------------------------------------------------ student */
function StartSheet({ a, classId, track, onClose }: { a: Assignment | null; classId: number; track: 'en' | 'de'; onClose: () => void }) {
  const t = useT()
  const nav = useNavigate()
  const setTrack = useApp((s) => s.setTrack)
  if (!a) return null
  const go = (path: string) => {
    setTrack(track)
    nav(path)
  }
  const words = assignmentWordsPath(a)
  return (
    <Sheet open={!!a} onClose={onClose} title={a.title}>
      <div className="grid gap-2" data-testid="start-sheet">
        {ASSIGNMENT_GAMES.map((g) => (
          <button key={g} className="btn-soft justify-start" onClick={() => go(assignmentPlayPath(a, classId, g))}>
            {t(`game.${g}`)}
          </button>
        ))}
        {words && (
          <button className="btn-ghost justify-start" onClick={() => go(words)}>
            📖 {t('cls.word_list')}
          </button>
        )}
      </div>
    </Sheet>
  )
}

function AssignmentCard({ a, onStart }: { a: Assignment; onStart?: () => void }) {
  const t = useT()
  const p = a.progress
  return (
    <div className="card space-y-2 p-4" data-testid="assignment">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-black">
            {p && STATUS_ICON[p.status]} {a.title}
          </div>
          <div className="text-xs text-muted">
            {targetText(t, a)} · {t('cls.n_words', { n: a.word_count })} · ⏰ <Deadline iso={a.due_at} />
          </div>
        </div>
        {onStart && p?.status !== 'upcoming' && (
          <button className="btn-primary min-h-[40px] px-4" onClick={onStart}>
            {t('common.start')}
          </button>
        )}
      </div>
      {p && (
        <>
          <ProgressBar value={p.target_percent} color={p.status === 'done' ? 'bg-success' : p.status === 'overdue' ? 'bg-error' : 'bg-primary'} />
          <div className="text-xs font-bold text-muted">
            {a.target_kind === 'plays' ? t('cls.plays_progress', { n: p.plays, of: a.target_value }) : t('cls.words_progress', { n: p.done, of: p.total, pct: p.percent })}
          </div>
        </>
      )}
    </div>
  )
}

function Board({ rows }: { rows: BoardRow[] }) {
  const t = useT()
  if (!rows.length) return <p className="text-sm text-muted">{t('cls.no_students')}</p>
  return (
    <ol className="space-y-1" data-testid="class-board">
      {rows.map((r) => (
        <li key={r.id} className={`flex items-center gap-3 rounded-2xl px-3 py-2 ${r.is_me ? 'bg-primary/10 font-black' : ''}`}>
          <span className="w-6 text-center font-black">{r.rank <= 3 ? ['🥇', '🥈', '🥉'][r.rank - 1] : r.rank}</span>
          <Avatar name={r.name} url={r.avatar_url} size={32} />
          <span className="flex-1 truncate">{r.name}</span>
          <span className="font-black">{r.xp} XP</span>
        </li>
      ))}
    </ol>
  )
}

function StudentClass({ d, reload }: { d: StudentView; reload: () => void }) {
  const t = useT()
  const nav = useNavigate()
  const [start, setStart] = useState<Assignment | null>(null)
  const c = d.class
  const leave = async () => {
    if (!window.confirm(t('cls.leave_confirm'))) return
    await api.post(`/classes/${c.id}/leave/`)
    toast.ok(t('cls.left'))
    nav('/classes')
  }
  return (
    <div className="page space-y-4">
      <ClassHeader c={c} />
      {c.membership === 'pending' ? (
        <EmptyState emoji="⏳" title={t('cls.pending')} text={t('cls.pending_text')} action={<button className="btn-soft" onClick={reload}>{t('common.retry')}</button>} />
      ) : (
        <>
          <section className="space-y-2">
            <h2 className="h2">📝 {t('cls.assignments')}</h2>
            {d.assignments.length === 0 ? <p className="text-muted">{t('cls.no_assignments')}</p> : d.assignments.map((a) => <AssignmentCard key={a.id} a={a} onStart={() => setStart(a)} />)}
          </section>
          <section className="card p-4">
            <h2 className="h2 mb-2">🏆 {t('cls.leaderboard')}</h2>
            <Board rows={d.leaderboard} />
          </section>
        </>
      )}
      <button className="btn-ghost w-full text-error" onClick={leave}>
        {t('cls.leave')}
      </button>
      <StartSheet a={start} classId={c.id} track={c.track} onClose={() => setStart(null)} />
    </div>
  )
}

/* ------------------------------------------------------------------ teacher */
function ClassHeader({ c, action }: { c: ClassInfo; action?: React.ReactNode }) {
  const t = useT()
  return (
    <section className="card flex flex-wrap items-center gap-3 p-4">
      <span className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-2xl font-black text-white" style={{ background: c.color }}>
        {c.name.slice(0, 2).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <h1 className="h1 truncate">{c.name}</h1>
        <div className="text-sm text-muted">
          {c.track.toUpperCase()}
          {c.level && ` · ${c.level}`} · {t('cls.n_students', { n: c.students })} · {c.teacher.name}
          {c.org && ` · ${c.org.name}`}
        </div>
      </div>
      {action}
    </section>
  )
}

function InviteSheet({ c, open, onClose, onChange }: { c: ClassInfo; open: boolean; onClose: () => void; onChange: () => void }) {
  const t = useT()
  const link = c.links.telegram || c.links.web || ''
  const regenerate = async (what: 'regenerate' | 'teacher_code') => {
    if (!window.confirm(t('cls.regen_confirm'))) return
    await api.post(`/classes/${c.id}/${what}/`)
    onChange()
  }
  return (
    <Sheet open={open} onClose={onClose} title={t('cls.invite')}>
      <div className="space-y-4 text-center" data-testid="invite-sheet">
        <div>
          <div className="text-sm font-bold text-muted">{t('cls.code')}</div>
          <div className="font-mono text-4xl font-black tracking-[0.3em]">{c.join_code}</div>
        </div>
        {link && <QrCode value={link} size={200} className="mx-auto rounded-xl" />}
        <p className="text-xs text-muted">{t('cls.qr_hint')}</p>
        <div className="grid gap-2">
          {c.links.telegram && (
            <button className="btn-soft" onClick={() => copy(c.links.telegram!, t('cls.copied'))}>
              <Copy className="h-4 w-4" /> {t('cls.copy_tg')}
            </button>
          )}
          {c.links.web && (
            <button className="btn-soft" onClick={() => copy(c.links.web!, t('cls.copied'))}>
              <Copy className="h-4 w-4" /> {t('cls.copy_web')}
            </button>
          )}
          {link && (
            <button className="btn-soft" onClick={() => shareToTelegram(link, t('cls.share_text', { name: c.name }))}>
              <Share2 className="h-4 w-4" /> {t('cls.share')}
            </button>
          )}
          {c.is_owner && (
            <button className="btn-ghost" onClick={() => regenerate('regenerate')}>
              🔄 {t('cls.regenerate')}
            </button>
          )}
        </div>
        {c.is_owner && c.links.teacher && (
          <div className="space-y-2 border-t border-line pt-3 text-left">
            <div className="font-bold">🧑‍🏫 {t('cls.coteachers')}</div>
            {(c.co_teachers ?? []).map((p) => (
              <div key={p.id} className="flex items-center gap-2 text-sm">
                <Avatar name={p.name} url={p.avatar_url} size={24} /> {p.name}
              </div>
            ))}
            <button className="btn-soft w-full" onClick={() => copy(c.links.teacher!, t('cls.copied'))}>
              <UserPlus className="h-4 w-4" /> {t('cls.copy_teacher_link')}
            </button>
            <button className="btn-ghost w-full text-sm" onClick={() => regenerate('teacher_code')}>
              🔄 {t('cls.regenerate_teacher')}
            </button>
          </div>
        )}
      </div>
    </Sheet>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card p-3">
      <div className="text-2xl font-black">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  )
}

const SORTS: SortKey[] = ['name', 'last_active', 'words_week', 'words_total', 'accuracy', 'streak', 'weekly_xp']

function StudentsTab({ d, reload }: { d: TeacherView; reload: () => void }) {
  const t = useT()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortKey>('weekly_xp')
  const [desc, setDesc] = useState(true)
  const rows = useMemo(() => sortStudents(d.students, sort, desc, q), [d.students, sort, desc, q])
  const act = async (uid: number, action: 'approve' | 'remove') => {
    if (action === 'remove' && !window.confirm(t('cls.remove_confirm'))) return
    try {
      await api.post(`/classes/${d.class.id}/members/${uid}/${action}/`)
      reload()
    } catch (err) {
      const detail = err instanceof ApiError ? (err.data as { detail?: string })?.detail : ''
      toast.err(detail === 'class_full' ? t('cls.full') : t('err.generic'))
    }
  }
  const header = (k: SortKey, label: string) => (
    <th className="cursor-pointer select-none whitespace-nowrap px-2 py-2 text-left" onClick={() => (sort === k ? setDesc(!desc) : (setSort(k), setDesc(k !== 'name')))}>
      {label} {sort === k ? (desc ? '↓' : '↑') : ''}
    </th>
  )
  const status = (r: (typeof rows)[number], a: Assignment) => {
    const p = r.assignments[String(a.id)]
    return p ? <span title={`${p.percent}% · ${p.plays}`}>{STATUS_ICON[p.status]}</span> : '—'
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <label className="relative min-w-[180px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input className="input pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('common.search')} />
        </label>
        <select className="input w-auto md:hidden" value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label={t('cls.sort')}>
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {t(`cls.col_${s}`)}
            </option>
          ))}
        </select>
        <button className="btn-soft" onClick={() => api.download(`/classes/${d.class.id}/export.csv`, `${d.class.name}.csv`)}>
          <Download className="h-4 w-4" /> CSV
        </button>
      </div>
      {rows.length === 0 && <p className="text-muted">{t('cls.no_students')}</p>}
      {/* mobile: cards */}
      <div className="space-y-2 md:hidden">
        {rows.map((r) => (
          <div key={r.id} className="card flex items-center gap-3 p-3" onClick={() => r.membership === 'active' && nav(`/classes/${d.class.id}/students/${r.id}`)}>
            <Avatar name={r.name} url={r.avatar_url} size={40} />
            <div className="min-w-0 flex-1">
              <div className="truncate font-black">{r.name}</div>
              {r.membership === 'pending' ? (
                <div className="text-xs text-muted">⏳ {t('cls.pending')}</div>
              ) : (
                <div className="text-xs text-muted">
                  📚 {r.words_week}/{r.words_total} · 🎯 {r.accuracy ?? '—'}% · 🔥 {r.streak} · {r.weekly_xp} XP
                  <div className="mt-0.5">{d.assignments.map((a) => <span key={a.id} className="mr-1">{status(r, a)}</span>)}</div>
                </div>
              )}
            </div>
            {r.membership === 'pending' && (
              <button className="btn-primary min-h-[36px] px-3 text-sm" onClick={(e) => (e.stopPropagation(), act(r.id, 'approve'))}>
                ✓
              </button>
            )}
          </div>
        ))}
      </div>
      {/* desktop: wide table */}
      <div className="card hidden overflow-x-auto md:block">
        <table className="w-full text-sm" data-testid="students-table">
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              {header('name', t('cls.col_name'))}
              {header('last_active', t('cls.col_last_active'))}
              {header('words_week', t('cls.col_words_week'))}
              {header('words_total', t('cls.col_words_total'))}
              {header('accuracy', t('cls.col_accuracy'))}
              {header('streak', t('cls.col_streak'))}
              {header('weekly_xp', t('cls.col_weekly_xp'))}
              {d.assignments.map((a) => (
                <th key={a.id} className="max-w-[90px] truncate px-2 py-2 text-left" title={a.title}>
                  {a.title}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="cursor-pointer border-b border-line/50 hover:bg-line/30" onClick={() => r.membership === 'active' && nav(`/classes/${d.class.id}/students/${r.id}`)}>
                <td className="px-2 py-2">
                  <span className="flex items-center gap-2 font-bold">
                    <Avatar name={r.name} url={r.avatar_url} size={28} /> {r.name}
                  </span>
                </td>
                {r.membership === 'pending' ? (
                  <td colSpan={6 + d.assignments.length} className="px-2 text-muted">
                    ⏳ {t('cls.pending')}
                    <button className="btn-primary ml-3 min-h-[32px] px-3 text-xs" onClick={(e) => (e.stopPropagation(), act(r.id, 'approve'))}>
                      {t('cls.approve')}
                    </button>
                  </td>
                ) : (
                  <>
                    <td className="px-2">{r.last_active ?? '—'}</td>
                    <td className="px-2">{r.words_week}</td>
                    <td className="px-2">{r.words_total}</td>
                    <td className="px-2">{r.accuracy === null ? '—' : `${r.accuracy}%`}</td>
                    <td className="px-2">🔥 {r.streak}</td>
                    <td className="px-2 font-bold">{r.weekly_xp}</td>
                    {d.assignments.map((a) => (
                      <td key={a.id} className="px-2 text-center">
                        {status(r, a)}
                      </td>
                    ))}
                  </>
                )}
                <td className="px-2">
                  <button className="p-2 text-muted hover:text-error" onClick={(e) => (e.stopPropagation(), act(r.id, 'remove'))} aria-label={t('cls.remove')}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function inDays(n: number) {
  const d = new Date(Date.now() + n * 86400000)
  d.setHours(23, 59, 0, 0)
  const pad = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function NewAssignmentSheet({ c, open, onClose, onDone }: { c: ClassInfo; open: boolean; onClose: () => void; onDone: () => void }) {
  const t = useT()
  const lang = useApp((s) => s.lang)
  const [f, setF] = useState({ kind: 'level' as Assignment['kind'], title: '', level: (c.level || 'A1') as Cefr, lesson_from: '', lesson_to: '', exam_slug: '', topics: [] as string[], deck: '', target_kind: 'learn_pct' as Assignment['target_kind'], target_value: 80, starts_on: new Date().toISOString().slice(0, 10), due: inDays(7) })
  const set = (p: Partial<typeof f>) => setF((x) => ({ ...x, ...p }))
  const packs = useAsync(() => (open ? api.get<{ packs: ExamPackRow[] }>('/exams/', { track: c.track }) : Promise.resolve({ packs: [] })), [open, c.track])
  const pack = useAsync(() => (f.exam_slug ? api.get<ExamPackDetail>(`/exams/${f.exam_slug}/`) : Promise.resolve(null)), [f.exam_slug])
  const decks = useAsync(() => (open ? api.get<Deck[]>('/decks/', { track: c.track }) : Promise.resolve([] as Deck[])), [open, c.track])
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post(`/classes/${c.id}/assignments/`, {
        kind: f.kind,
        title: f.title,
        level: f.kind === 'level' ? f.level : '',
        lesson_from: f.kind === 'level' && f.lesson_from ? Number(f.lesson_from) : null,
        lesson_to: f.kind === 'level' && (f.lesson_to || f.lesson_from) ? Number(f.lesson_to || f.lesson_from) : null,
        exam_slug: f.kind === 'exam' ? f.exam_slug : '',
        topics: f.kind === 'exam' ? f.topics : [],
        deck: f.kind === 'deck' ? Number(f.deck) : null,
        target_kind: f.target_kind,
        target_value: f.target_value,
        starts_on: f.starts_on,
        due_at: new Date(f.due).toISOString(),
      })
      toast.ok(t('cls.assigned'))
      onDone()
    } catch (err) {
      const data = err instanceof ApiError ? (err.data as Record<string, unknown>) : {}
      toast.err(data?.detail === 'no_words' ? t('cls.no_words') : t('err.generic'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet open={open} onClose={onClose} title={`📝 ${t('cls.new_assignment')}`}>
      <form className="space-y-3" onSubmit={submit} data-testid="assignment-form">
        <Segmented
          value={f.kind}
          onChange={(v: Assignment['kind']) => set({ kind: v })}
          options={[
            { value: 'level', label: t('cls.kind_level') },
            { value: 'exam', label: t('cls.kind_exam') },
            { value: 'deck', label: t('cls.kind_deck') },
          ]}
        />
        {f.kind === 'level' && (
          <div className="grid grid-cols-3 gap-2">
            <select className="input" value={f.level} onChange={(e) => set({ level: e.target.value as Cefr })} aria-label={t('cls.level')}>
              {LEVELS.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
            <input className="input" type="number" min={1} value={f.lesson_from} onChange={(e) => set({ lesson_from: e.target.value })} placeholder={t('cls.lesson_from')} />
            <input className="input" type="number" min={1} value={f.lesson_to} onChange={(e) => set({ lesson_to: e.target.value })} placeholder={t('cls.lesson_to')} />
          </div>
        )}
        {f.kind === 'exam' && (
          <>
            <select className="input" required value={f.exam_slug} onChange={(e) => set({ exam_slug: e.target.value, topics: [] })} aria-label={t('cls.kind_exam')}>
              <option value="">—</option>
              {(packs.data?.packs ?? []).map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.emoji} {p.name[lang]} ({p.total})
                </option>
              ))}
            </select>
            {pack.data && (
              <div className="flex max-h-40 flex-wrap gap-1 overflow-y-auto">
                {pack.data.topics.map((tp) => {
                  const on = f.topics.includes(tp.slug)
                  return (
                    <button type="button" key={tp.slug} className={`chip ${on ? 'bg-primary text-white' : 'bg-line'}`} onClick={() => set({ topics: on ? f.topics.filter((x) => x !== tp.slug) : [...f.topics, tp.slug] })}>
                      {tp.emoji} {tp.name[lang]}
                    </button>
                  )
                })}
                <p className="w-full text-xs text-muted">{t('cls.topics_hint')}</p>
              </div>
            )}
          </>
        )}
        {f.kind === 'deck' && (
          <select className="input" required value={f.deck} onChange={(e) => set({ deck: e.target.value })} aria-label={t('cls.kind_deck')}>
            <option value="">—</option>
            {(decks.data ?? []).map((dk) => (
              <option key={dk.id} value={dk.id}>
                {dk.name} ({dk.card_count})
              </option>
            ))}
          </select>
        )}
        <div className="grid grid-cols-[1fr_96px] gap-2">
          <select className="input" value={f.target_kind} onChange={(e) => set({ target_kind: e.target.value as Assignment['target_kind'], target_value: e.target.value === 'plays' ? 3 : 80 })} aria-label={t('cls.target')}>
            <option value="learn_pct">{t('cls.target_learn_opt')}</option>
            <option value="plays">{t('cls.target_plays_opt')}</option>
          </select>
          <input className="input" type="number" min={1} max={100} value={f.target_value} onChange={(e) => set({ target_value: Number(e.target.value) })} aria-label={t('cls.target')} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs font-bold text-muted">
            {t('cls.starts')}
            <input className="input mt-1" type="date" value={f.starts_on} onChange={(e) => set({ starts_on: e.target.value })} />
          </label>
          <label className="text-xs font-bold text-muted">
            {t('cls.deadline')}
            <input className="input mt-1" type="datetime-local" required value={f.due} onChange={(e) => set({ due: e.target.value })} />
          </label>
        </div>
        <input className="input" maxLength={120} value={f.title} onChange={(e) => set({ title: e.target.value })} placeholder={t('cls.title_optional')} />
        <button className="btn-primary w-full" disabled={busy}>
          {t('cls.assign')}
        </button>
      </form>
    </Sheet>
  )
}

function AssignmentsTab({ d, reload }: { d: TeacherView; reload: () => void }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const del = async (a: Assignment) => {
    if (!window.confirm(t('common.confirm_delete'))) return
    await api.del(`/classes/${d.class.id}/assignments/${a.id}/`)
    reload()
  }
  const active = d.students.filter((s) => s.membership === 'active')
  return (
    <div className="space-y-2">
      <button className="btn-primary w-full" onClick={() => setOpen(true)} data-testid="new-assignment">
        ➕ {t('cls.new_assignment')}
      </button>
      {d.assignments.length === 0 && <p className="text-muted">{t('cls.no_assignments')}</p>}
      {d.assignments.map((a) => {
        const done = active.filter((s) => s.assignments[String(a.id)]?.status === 'done').length
        return (
          <div key={a.id} className="card space-y-2 p-4">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="font-black">{a.title}</div>
                <div className="text-xs text-muted">
                  {targetText(t, a)} · {t('cls.n_words', { n: a.word_count })} · ⏰ <Deadline iso={a.due_at} />
                </div>
              </div>
              <button className="p-2 text-muted hover:text-error" onClick={() => del(a)} aria-label={t('common.delete')}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <ProgressBar value={active.length ? (100 * done) / active.length : 0} color="bg-success" />
            <div className="text-xs font-bold text-muted">{t('cls.done_of', { n: done, of: active.length })}</div>
          </div>
        )
      })}
      <NewAssignmentSheet c={d.class} open={open} onClose={() => setOpen(false)} onDone={() => (setOpen(false), reload())} />
    </div>
  )
}

function HardestTab({ c, reload }: { c: ClassInfo; reload: () => void }) {
  const t = useT()
  const { data, error } = useAsync(() => api.get<{ words: HardWord[] }>(`/classes/${c.id}/hardest/`), [c.id])
  const [busy, setBusy] = useState(false)
  const make = async () => {
    setBusy(true)
    try {
      await api.post(`/classes/${c.id}/hardest/`, {})
      toast.ok(t('cls.deck_assigned'))
      reload()
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }
  if (error) return <ErrorState error={error} />
  if (!data) return <Skeleton className="h-40" />
  if (!data.words.length) return <p className="text-muted">{t('cls.no_hard_words')}</p>
  return (
    <div className="space-y-3">
      <button className="btn-primary w-full" onClick={make} disabled={busy} data-testid="hard-deck">
        🗂️ {t('cls.hard_deck')}
      </button>
      <div className="card divide-y divide-line">
        {data.words.map((w) => (
          <div key={w.term} className="flex items-center gap-3 px-4 py-2">
            <span className="flex-1">
              <span className="font-black">{w.term}</span> <span className="text-muted">— {w.translation || '…'}</span>
            </span>
            <span className="chip bg-error/15 text-error">❌ {w.students}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function AnnounceTab({ c }: { c: ClassInfo }) {
  const t = useT()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const send = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await api.post<{ recipients: number }>(`/classes/${c.id}/announce/`, { text })
      toast.ok(t('cls.announced', { n: r.recipients }))
      setText('')
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="card space-y-3 p-4" onSubmit={send}>
      <p className="text-sm text-muted">{t('cls.announce_hint')}</p>
      <textarea className="input min-h-[120px]" required maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder={t('cls.announce_placeholder')} />
      <button className="btn-primary w-full" disabled={busy || !text.trim()}>
        📣 {t('cls.announce_send')}
      </button>
    </form>
  )
}

function SettingsTab({ c, reload }: { c: ClassInfo; reload: () => void }) {
  const t = useT()
  const [name, setName] = useState(c.name)
  const [description, setDescription] = useState(c.description)
  const patch = async (p: Record<string, unknown>) => {
    try {
      await api.patch(`/classes/${c.id}/`, p)
      toast.ok(t('common.saved'))
      reload()
    } catch (err) {
      const detail = err instanceof ApiError ? (err.data as { detail?: string })?.detail : ''
      toast.err(detail === 'class_limit' ? t('cls.limit_classes', { n: c.limits?.classes ?? 2 }) : t('err.generic'))
    }
  }
  if (!c.is_owner) return <p className="text-muted">{t('cls.owner_only')}</p>
  return (
    <div className="card space-y-3 p-4">
      <input className="input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      <textarea className="input" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} placeholder={t('cls.description')} />
      <button className="btn-soft w-full" onClick={() => patch({ name, description })}>
        {t('common.save')}
      </button>
      <Toggle checked={!!c.approval_required} onChange={(v) => patch({ approval_required: v })} label={t('cls.approval')} />
      <p className="text-xs text-muted">{t('cls.plan_info', { plan: c.plan ?? 'free', students: c.limits?.students ?? 40 })}</p>
      <button className="btn-ghost w-full" onClick={() => patch({ archived: !c.archived })}>
        {c.archived ? `♻️ ${t('cls.unarchive')}` : `🗄️ ${t('cls.archive')}`}
      </button>
    </div>
  )
}

type Tab = 'students' | 'assignments' | 'hardest' | 'board' | 'announce' | 'settings'

function TeacherDashboard({ d, reload }: { d: TeacherView; reload: () => void }) {
  const t = useT()
  const [tab, setTab] = useState<Tab>('students')
  const [invite, setInvite] = useState(false)
  const o = d.overview
  const board = useAsync(() => (tab === 'board' ? api.get<{ entries: BoardRow[] }>(`/classes/${d.class.id}/leaderboard/`) : Promise.resolve(null)), [tab, d.class.id])
  const tabs: { v: Tab; label: string }[] = [
    { v: 'students', label: `👥 ${t('cls.tab_students')}` },
    { v: 'assignments', label: `📝 ${t('cls.assignments')}` },
    { v: 'hardest', label: `🧩 ${t('cls.tab_hardest')}` },
    { v: 'board', label: `🏆 ${t('cls.leaderboard')}` },
    { v: 'announce', label: `📣 ${t('cls.tab_announce')}` },
    { v: 'settings', label: `⚙️ ${t('profile.settings')}` },
  ]
  return (
    <div className="page max-w-6xl space-y-4">
      <ClassHeader
        c={d.class}
        action={
          <button className="btn-primary" onClick={() => setInvite(true)} data-testid="invite-btn">
            <UserPlus className="h-5 w-5" /> {t('cls.invite')}
          </button>
        }
      />
      <section className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid="overview">
        <Stat label={t('cls.ov_students')} value={o.pending ? `${o.students} (+${o.pending}⏳)` : o.students} />
        <Stat label={t('cls.ov_active')} value={o.active_week} />
        <Stat label={t('cls.ov_progress')} value={`${o.avg_progress}%`} />
        <Stat label={t('cls.ov_completion')} value={`${o.completion}%`} />
      </section>
      <div className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1">
        {tabs.map((x) => (
          <button key={x.v} onClick={() => setTab(x.v)} className={`chip shrink-0 ${tab === x.v ? 'bg-primary text-white' : 'bg-line'}`}>
            {x.label}
          </button>
        ))}
      </div>
      {tab === 'students' && <StudentsTab d={d} reload={reload} />}
      {tab === 'assignments' && <AssignmentsTab d={d} reload={reload} />}
      {tab === 'hardest' && <HardestTab c={d.class} reload={reload} />}
      {tab === 'board' && <div className="card p-4">{board.data ? <Board rows={board.data.entries} /> : <Skeleton className="h-32" />}</div>}
      {tab === 'announce' && <AnnounceTab c={d.class} />}
      {tab === 'settings' && <SettingsTab c={d.class} reload={reload} />}
      <InviteSheet c={d.class} open={invite} onClose={() => setInvite(false)} onChange={reload} />
    </div>
  )
}

export default function ClassPage() {
  const t = useT()
  const { id = '' } = useParams()
  useTelegramBack('/classes')
  const { data, error, reload } = useAsync(() => api.get<TeacherView | StudentView>(`/classes/${id}/`), [id])
  if (error)
    return (
      <div className="page">
        {error instanceof ApiError && error.status === 404 ? <EmptyState emoji="🔍" title={t('cls.not_found')} action={<Link className="btn-primary" to="/classes">{t('cls.my_classes')}</Link>} /> : <ErrorState error={error} onRetry={reload} />}
      </div>
    )
  if (!data)
    return (
      <div className="page space-y-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    )
  return isTeacherView(data) ? <TeacherDashboard d={data} reload={reload} /> : <StudentClass d={data} reload={reload} />
}
