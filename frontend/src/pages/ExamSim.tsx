import { Play, RotateCcw } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ProgressBar, Segmented, Spinner, toast } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useExamGuard, watermark, type ViolationKind } from '../lib/examGuard'
import { clock, examPlayUrl, type ExamPackDetail, type SimQuestion, type Simulation, type SimResult } from '../lib/exams'
import { feedbackWin } from '../lib/fx'
import { useAsync, useInterval, useTelegramBack } from '../lib/hooks'
import { allowedLangs, isValidPair, LANG_META, type TrLang } from '../lib/translation'
import { useApp } from '../store/app'

/** "Imtihon simulyatsiyasi": 30 questions, a timer, no hints, weak topics at the end. */
export default function ExamSim() {
  const { slug = '' } = useParams()
  const t = useT()
  useTelegramBack(`/exams/${slug}`)
  const lang = useApp((s) => s.lang)
  const setTrack = useApp((s) => s.setTrack)
  const bumpUser = useApp((s) => s.bumpUser)
  const user = useApp((s) => s.user)
  const pack = useAsync(() => api.get<ExamPackDetail>(`/exams/${slug}/`), [slug])
  const [tl, setTl] = useState<TrLang>('uz')
  const [sim, setSim] = useState<Simulation | null>(null)
  const [question, setQuestion] = useState<SimQuestion | null>(null)
  const [picked, setPicked] = useState<number | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [left, setLeft] = useState(0)
  const [result, setResult] = useState<SimResult | null>(null)
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  const endsAt = useRef(0)

  const start = async () => {
    if (!pack.data) return
    setBusy(true)
    try {
      setTrack(pack.data.track)
      const s = await api.post<Simulation>(`/exams/${slug}/simulation/`, { translation_lang: isValidPair(pack.data.track, tl) ? tl : 'uz' })
      setSim(s)
      setQuestion(s.question)
      setPicked(null)
      setWarning(null)
      setResult(null)
      sending.current = false
      endsAt.current = Date.now() + s.time_limit * 1000
      setLeft(s.time_limit)
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  const finishWith = useCallback(
    (r: SimResult) => {
      setResult(r)
      bumpUser({ xp: r.xp_total, streak: r.streak })
      if (r.percent >= 60 && !r.terminated) feedbackWin()
      window.scrollTo({ top: 0 })
    },
    [bumpUser],
  )
  const submit = useCallback(async () => {
    if (!sim || sending.current) return
    sending.current = true
    setBusy(true)
    try {
      finishWith(await api.post<SimResult>(`/exams/simulations/${sim.id}/submit/`))
    } catch {
      sending.current = false
      toast.err(t('err.network'))
    } finally {
      setBusy(false)
    }
  }, [sim, finishWith, t])

  const next = async () => {
    if (!sim || !question || busy) return
    setBusy(true)
    try {
      const r = await api.post<{ done: boolean; question: SimQuestion | null }>(`/exams/simulations/${sim.id}/answer/`, { index: question.index, choice: picked })
      setPicked(null)
      setQuestion(r.question)
      setBusy(false)
      if (r.done) void submit()
    } catch {
      setBusy(false)
      toast.err(t('err.network'))
    }
  }

  /* ---- protection: active only while questions are on screen ---- */
  const active = Boolean(sim && !result)
  const pending = useRef<ViolationKind[]>([])
  const flushing = useRef(false)
  const flush = useCallback(async () => {
    if (!sim || flushing.current) return
    flushing.current = true
    try {
      while (pending.current.length) {
        const r = await api.post<{ count: number; max: number; terminated: boolean; result: SimResult | null }>(`/exams/simulations/${sim.id}/violation/`, { kind: pending.current[0] })
        pending.current.shift()
        if (r.terminated && r.result) {
          sending.current = true
          pending.current = []
          finishWith(r.result)
        } else setWarning(t('exam.warn', { n: r.count, max: r.max }))
      }
    } catch {
      /* offline (e.g. app in the background): sent when the player is back */
    } finally {
      flushing.current = false
    }
  }, [sim, finishWith, t])
  const { hidden, show } = useExamGuard(active, (kind) => {
    pending.current.push(kind)
    void flush()
  })
  const mark = useMemo(
    () => watermark(`${user?.display_name || user?.email || ''} #${user?.id ?? ''} · ${new Date().toLocaleDateString()}`),
    [user?.display_name, user?.email, user?.id],
  )

  useInterval(
    () => {
      const s = Math.max(0, Math.round((endsAt.current - Date.now()) / 1000))
      setLeft(s)
      if (s === 0) void submit()
    },
    sim && !result && left > 0 ? 1000 : null,
  )

  if (result)
    return (
      <div className="page max-w-xl space-y-4" data-testid="sim-result">
        <div className="card p-6 text-center">
          {result.terminated && <p className="mb-3 rounded-2xl bg-error/15 p-3 font-black text-error" data-testid="terminated">⚠️ {t('exam.terminated')}</p>}
          <div className="text-6xl">{result.percent >= 80 ? '🏆' : result.percent >= 60 ? '🎉' : '💪'}</div>
          <h1 className="h1 mt-2">
            {result.score} / {result.total} · {result.percent}%
          </h1>
          <p className="mt-1 text-muted">
            ⏱ {clock(result.duration_ms / 1000)} · +{result.xp} XP
          </p>
          {Boolean(result.violations?.length) && (
            <p className="mt-2 text-sm font-bold text-error" data-testid="violations">
              {t('exam.violations', { n: result.violations!.length })}: {result.violations!.map((v) => t(`exam.v_${v.kind}`)).join(', ')}
            </p>
          )}
          {result.late && <p className="mt-2 font-bold text-error">{t('exam.late')}</p>}
        </div>
        <div className="card space-y-3 p-4">
          <h2 className="h2">{t('exam.by_topic')}</h2>
          {result.topics.map((x) => (
            <div key={x.slug} className="space-y-1">
              <div className="flex justify-between gap-2 text-sm font-bold">
                <span>
                  {x.emoji} {x.name[lang]} {x.weak && <span className="chip bg-error/15 text-xs text-error">{t('exam.weak')}</span>}
                </span>
                <span>
                  {x.correct}/{x.total}
                </span>
              </div>
              <ProgressBar value={x.percent} className="h-1.5" color={x.weak ? 'bg-error' : 'bg-success'} />
            </div>
          ))}
          {result.weak_topics.length > 0 ? (
            <Link className="btn-primary w-full" to={examPlayUrl('flashcards', slug, result.weak_topics.join(','), true)}>
              🎯 {t('exam.practice_weak')}
            </Link>
          ) : (
            <p className="font-bold text-success">{t('exam.no_weak')}</p>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            <button className="btn-soft" onClick={() => void start()} disabled={busy}>
              <RotateCcw className="h-5 w-5" /> {t('exam.sim_again')}
            </button>
            <Link className="btn-ghost" to={`/exams/${slug}`}>
              {t('exam.back_to_pack')}
            </Link>
          </div>
        </div>
        <ul className="card divide-y divide-line p-4 text-sm">
          {result.review.map((r, i) => (
            <li key={i} className="py-2">
              {r.correct ? '✅' : '❌'} <span className="font-extrabold">{r.prompt}</span> — {r.answer}
              {!r.correct && r.given && <span className="text-error"> ({r.given})</span>}
            </li>
          ))}
        </ul>
      </div>
    )

  if (!sim)
    return (
      <div className="page max-w-xl space-y-4">
        <div className="card space-y-4 p-6 text-center">
          <div className="text-6xl">⏱</div>
          <h1 className="h1">{t('exam.simulation')}</h1>
          <p className="font-bold">{pack.data?.name[lang]}</p>
          <p className="text-muted">{t('exam.sim_rules')}</p>
          <p className="rounded-2xl bg-accent/20 p-3 text-sm font-bold">🔒 {t('exam.protect_rules')}</p>
          {pack.data && (
            <Segmented
              value={isValidPair(pack.data.track, tl) ? tl : 'uz'}
              onChange={setTl}
              options={allowedLangs(pack.data.track).map((l) => ({ value: l, label: `${LANG_META[l].flag} ${LANG_META[l].short}` }))}
            />
          )}
          <button className="btn-primary w-full" disabled={!pack.data || busy} onClick={() => void start()}>
            {busy ? <Spinner className="h-5 w-5" /> : <Play className="h-5 w-5" />} {t('common.start')}
          </button>
          <p className="text-xs text-muted">{t('exam.disclaimer')}</p>
        </div>
      </div>
    )

  const q = question
  if (!q)
    return (
      <div className="grid min-h-[60vh] place-items-center">
        {busy ? (
          <Spinner className="h-8 w-8 text-primary" />
        ) : (
          <button className="btn-primary" onClick={() => void submit()}>
            {t('common.finish')}
          </button>
        )}
      </div>
    )
  const last = q.index === sim.total - 1
  return (
    <div className="page max-w-xl" data-testid="sim-question">
      {warning && (
        <div className="mb-3 flex items-center gap-3 rounded-2xl bg-error/15 p-3 font-bold text-error" role="alert">
          <span className="flex-1">⚠️ {warning}</span>
          <button className="btn-ghost min-h-[36px] px-3" onClick={() => setWarning(null)}>
            OK
          </button>
        </div>
      )}
      <div className="relative select-none">
        <div className={`space-y-4 transition ${hidden ? 'pointer-events-none blur-2xl' : ''}`} aria-hidden={hidden} data-testid="exam-area">
          <div className="flex items-center justify-between">
            <span className="chip bg-line">
              {q.index + 1}/{sim.total}
            </span>
            <span className={`chip text-base ${left <= 60 ? 'bg-error/15 text-error' : 'bg-line'}`}>⏱ {clock(left)}</span>
          </div>
          <ProgressBar value={(100 * q.index) / sim.total} className="h-2" />
          <div className="card flex min-h-[140px] flex-col items-center justify-center gap-2 p-6 text-center">
            <span className="text-xs font-bold uppercase text-muted">{t(`exam.q_${q.kind}`)}</span>
            <span className={q.kind === 'definition' ? 'font-read text-lg' : 'break-words text-3xl font-black'}>{hidden ? '' : q.prompt}</span>
          </div>
          <div className="grid gap-2">
            {q.options.map((o, i) => (
              <button key={i} aria-pressed={picked === i} onClick={() => setPicked(i)} className={`btn min-h-[56px] text-lg ${picked === i ? 'bg-primary text-white' : 'bg-card text-ink shadow-soft'}`}>
                {hidden ? '' : o}
              </button>
            ))}
          </div>
          <button className="btn-primary w-full" disabled={busy} onClick={() => void next()}>
            {busy && <Spinner className="h-5 w-5" />} {t(last ? 'common.finish' : picked === null ? 'exam.skip' : 'common.next')}
          </button>
        </div>
        <div className="pointer-events-none absolute inset-0 z-10" style={{ backgroundImage: mark }} aria-hidden data-testid="watermark" />
        {hidden && (
          <button
            className="absolute inset-0 z-20 grid place-items-center rounded-[24px] bg-bg/90 p-6 text-center text-lg font-black"
            data-testid="exam-overlay"
            onClick={() => {
              show()
              void flush()
            }}
          >
            {t('exam.overlay')}
          </button>
        )}
      </div>
    </div>
  )
}
