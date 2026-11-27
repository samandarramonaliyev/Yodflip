import { ChevronRight, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { EmptyState, ErrorState, ListSkeleton, Sheet, Toggle, toast } from '../components/ui'
import { useT } from '../i18n'
import { api, ApiError } from '../lib/api'
import type { ClassInfo, ClassList } from '../lib/classes'
import { useAsync, useTelegramBack } from '../lib/hooks'
import type { Cefr } from '../lib/types'
import { useApp } from '../store/app'

const LEVELS: Cefr[] = ['A1', 'A2', 'B1', 'B2', 'C1']

export function CreateClassSheet({ open, onClose, data }: { open: boolean; onClose: () => void; data: ClassList | null }) {
  const t = useT()
  const nav = useNavigate()
  const track = useApp((s) => s.track)
  const [form, setForm] = useState({ name: '', track, level: '' as Cefr | '', description: '', color: '#6C5CE7', approval_required: false, org: '' })
  const [busy, setBusy] = useState(false)
  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }))
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const c = await api.post<ClassInfo>('/classes/', { ...form, org: form.org ? Number(form.org) : null })
      toast.ok(t('cls.created'))
      nav(`/classes/${c.id}`)
    } catch (err) {
      const detail = err instanceof ApiError ? (err.data as { detail?: string })?.detail : ''
      toast.err(detail === 'class_limit' ? t('cls.limit_classes', { n: data?.limits.classes ?? 2 }) : t('err.generic'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet open={open} onClose={onClose} title={`👩‍🏫 ${t('cls.create')}`}>
      <form onSubmit={submit} className="space-y-3" data-testid="create-class">
        <input className="input" required maxLength={80} value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder={t('cls.name')} />
        <div className="grid grid-cols-2 gap-2">
          <select className="input" value={form.track} onChange={(e) => set({ track: e.target.value as 'en' | 'de' })} aria-label={t('track.label')}>
            <option value="en">EN · English</option>
            <option value="de">DE · Deutsch</option>
          </select>
          <select className="input" value={form.level} onChange={(e) => set({ level: e.target.value as Cefr | '' })} aria-label={t('cls.level')}>
            <option value="">{t('cls.level_any')}</option>
            {LEVELS.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </div>
        <textarea className="input min-h-[72px]" maxLength={500} value={form.description} onChange={(e) => set({ description: e.target.value })} placeholder={t('cls.description')} />
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t('cls.color')}>
          {(data?.colors ?? ['#6C5CE7', '#FDCB6E', '#00B894', '#FF7675']).map((c) => (
            <button type="button" key={c} role="radio" aria-checked={form.color === c} onClick={() => set({ color: c })} className={`h-9 w-9 rounded-full ring-offset-2 ${form.color === c ? 'ring-2 ring-primary' : ''}`} style={{ background: c }} aria-label={c} />
          ))}
        </div>
        {data && data.orgs.length > 0 && (
          <select className="input" value={form.org} onChange={(e) => set({ org: e.target.value })} aria-label={t('cls.org')}>
            <option value="">{t('cls.org_none')}</option>
            {data.orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        )}
        <Toggle checked={form.approval_required} onChange={(v) => set({ approval_required: v })} label={t('cls.approval')} />
        <p className="text-xs text-muted">{t('cls.free_plan', { classes: data?.limits.classes ?? 2, students: data?.limits.students ?? 40 })}</p>
        <button className="btn-primary w-full" disabled={busy}>
          {t('cls.create')}
        </button>
      </form>
    </Sheet>
  )
}

export function ClassCard({ c }: { c: ClassInfo }) {
  const t = useT()
  return (
    <Link to={`/classes/${c.id}`} className="card flex items-center gap-3 p-4 transition hover:shadow-lift" data-testid="class-card">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl text-xl font-black text-white" style={{ background: c.color }}>
        {c.name.slice(0, 2).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-black">
          {c.name} {c.archived && <span className="chip bg-line text-xs">{t('cls.archived')}</span>}
        </span>
        <span className="block truncate text-sm text-muted">
          {c.track.toUpperCase()}
          {c.level && ` · ${c.level}`} · {t('cls.n_students', { n: c.students })}
          {c.role === 'student' && ` · ${c.teacher.name}`}
          {c.membership === 'pending' && ` · ⏳ ${t('cls.pending')}`}
        </span>
      </span>
      {c.role === 'student' && !!c.open_assignments && <span className="chip bg-accent/40">📝 {c.open_assignments}</span>}
      <ChevronRight className="text-muted" />
    </Link>
  )
}

export default function Classes() {
  const t = useT()
  useTelegramBack('/profile')
  const { data, error, loading, reload } = useAsync(() => api.get<ClassList>('/classes/'), [])
  const [open, setOpen] = useState(false)
  const teaching = data?.classes.filter((c) => c.role === 'teacher') ?? []
  const studying = data?.classes.filter((c) => c.role === 'student') ?? []
  return (
    <div className="page space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">👩‍🏫 {t('cls.my_classes')}</h1>
        <button className="btn-primary" onClick={() => setOpen(true)} data-testid="open-create">
          <Plus className="h-5 w-5" /> {t('cls.create')}
        </button>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading || !data ? (
        <ListSkeleton rows={3} />
      ) : data.classes.length === 0 ? (
        <EmptyState emoji="🏫" title={t('cls.empty')} text={t('cls.empty_text')} />
      ) : (
        <>
          {teaching.length > 0 && (
            <section className="space-y-2">
              <h2 className="h2">{t('cls.teaching')}</h2>
              {teaching.map((c) => (
                <ClassCard key={c.id} c={c} />
              ))}
            </section>
          )}
          {studying.length > 0 && (
            <section className="space-y-2">
              <h2 className="h2">{t('cls.studying')}</h2>
              {studying.map((c) => (
                <ClassCard key={c.id} c={c} />
              ))}
            </section>
          )}
        </>
      )}
      <CreateClassSheet open={open} onClose={() => setOpen(false)} data={data} />
    </div>
  )
}
