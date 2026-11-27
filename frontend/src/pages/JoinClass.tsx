import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Avatar, EmptyState, ErrorState, Skeleton, toast } from '../components/ui'
import { useT } from '../i18n'
import { api, ApiError } from '../lib/api'
import type { JoinPreview } from '../lib/classes'
import { useAsync } from '../lib/hooks'
import { useApp } from '../store/app'

/** /join/:code — "Sinfga qo'shilish" confirm screen (also opened from t.me/...?startapp=class_<code>). */
export default function JoinClass() {
  const t = useT()
  const { code = '' } = useParams()
  const nav = useNavigate()
  const setTrack = useApp((s) => s.setTrack)
  const { data, error } = useAsync(() => api.get<JoinPreview>(`/classes/join/${code}/`), [code])
  const [busy, setBusy] = useState(false)
  const join = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ id: number; membership: string }>(`/classes/join/${code}/`)
      if (data) setTrack(data.track)
      toast.ok(r.membership === 'pending' ? t('cls.join_pending') : t('cls.joined'))
      nav(`/classes/${r.id}`, { replace: true })
    } catch (err) {
      const detail = err instanceof ApiError ? (err.data as { detail?: string })?.detail : ''
      toast.err(detail === 'class_full' ? t('cls.full') : detail === 'removed_from_class' ? t('cls.removed') : t('err.generic'))
    } finally {
      setBusy(false)
    }
  }
  if (error)
    return (
      <div className="page">
        {error instanceof ApiError && error.status === 404 ? (
          <EmptyState emoji="🔍" title={t('cls.code_invalid')} action={<Link className="btn-primary" to="/">{t('nav.home')}</Link>} />
        ) : (
          <ErrorState error={error} />
        )}
      </div>
    )
  if (!data)
    return (
      <div className="page">
        <Skeleton className="h-64" />
      </div>
    )
  const member = data.membership === 'active' || data.membership === 'pending'
  return (
    <div className="page mx-auto max-w-md space-y-4">
      <div className="card overflow-hidden" data-testid="join-preview">
        <div className="h-20" style={{ background: data.color }} />
        <div className="-mt-8 space-y-3 p-5 text-center">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-2xl border-4 border-card text-2xl font-black text-white" style={{ background: data.color }}>
            {data.name.slice(0, 2).toUpperCase()}
          </span>
          <h1 className="h1">{data.name}</h1>
          <p className="text-muted">
            {data.track.toUpperCase()}
            {data.level && ` · ${data.level}`} · {t('cls.n_students', { n: data.students })}
          </p>
          {data.description && <p>{data.description}</p>}
          <div className="flex items-center justify-center gap-2 text-sm font-bold">
            <Avatar name={data.teacher.name} url={data.teacher.avatar_url} size={28} /> {data.teacher.name}
          </div>
          {data.is_teacher || member ? (
            <Link className="btn-primary w-full" to={`/classes/${data.id}`}>
              {data.membership === 'pending' ? `⏳ ${t('cls.pending')}` : t('cls.open')}
            </Link>
          ) : (
            <button className="btn-primary w-full" onClick={join} disabled={busy} data-testid="join-btn">
              {t('cls.join')}
            </button>
          )}
          {data.approval_required && !member && !data.is_teacher && <p className="text-xs text-muted">{t('cls.approval_hint')}</p>}
        </div>
      </div>
    </div>
  )
}

/** /teach/:code — co-teacher invitation. */
export function TeachInvite() {
  const t = useT()
  const { code = '' } = useParams()
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const accept = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ id: number }>(`/classes/teach/${code}/`)
      nav(`/classes/${r.id}`, { replace: true })
    } catch {
      toast.err(t('cls.code_invalid'))
      setBusy(false)
    }
  }
  return (
    <div className="page mx-auto max-w-md">
      <EmptyState
        emoji="🧑‍🏫"
        title={t('cls.coteacher_invite')}
        text={t('cls.coteacher_text')}
        action={
          <button className="btn-primary" onClick={accept} disabled={busy}>
            {t('cls.coteacher_accept')}
          </button>
        }
      />
    </div>
  )
}
