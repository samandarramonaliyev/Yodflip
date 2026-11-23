import { motion } from 'framer-motion'
import { Copy, Play, RotateCcw, Send, UserPlus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Avatar, EmptyState, ErrorState, Spinner, toast } from '../components/ui'
import { ActionRow } from '../components/Results'
import DuelBoard from '../games/DuelBoard'
import { useT } from '../i18n'
import { ApiError } from '../lib/api'
import { duelApi, guestToken, seconds, setGuestToken, type Duel, type DuelSide } from '../lib/duel'
import { burst, feedbackWin } from '../lib/fx'
import { useTelegramBack } from '../lib/hooks'
import { shareToTelegram } from '../lib/telegram'
import { LANG_META } from '../lib/translation'
import { useApp } from '../store/app'

export default function DuelPage() {
  const { code = '' } = useParams()
  return <DuelView key={code} code={code} />
}

function DuelView({ code }: { code: string }) {
  const t = useT()
  const user = useApp((s) => s.user)
  const bumpUser = useApp((s) => s.bumpUser)
  useTelegramBack('/')
  const [duel, setDuel] = useState<Duel | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const playing = Boolean(duel?.questions && !duel.me?.finished)

  const load = async () => {
    setError(null)
    try {
      if (user && guestToken(code)) {
        // A guest signed in: save the guest result to the account.
        await duelApi.claim(code).catch(() => null)
        setGuestToken(code, null)
        toast.ok(t('duel.claimed'))
      }
      setDuel(await duelApi.get(code))
    } catch (e) {
      setError(e)
    }
  }
  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, user?.id])

  const start = async () => {
    setBusy(true)
    try {
      setDuel(await duelApi.start(code))
    } catch (e) {
      const st = e instanceof ApiError ? e.status : 0
      toast.err(t(st === 409 ? 'duel.taken' : st === 410 ? 'duel.expired' : 'err.generic'))
      if (st === 409 || st === 410) void load()
    } finally {
      setBusy(false)
    }
  }

  if (error)
    return (
      <div className="page">
        {error instanceof ApiError && error.status === 404 ? (
          <EmptyState emoji="⚔️" title={t('duel.not_found')} action={<Link className="btn-primary" to="/duel">{t('duel.new')}</Link>} />
        ) : (
          <ErrorState error={error} onRetry={() => void load()} />
        )}
      </div>
    )
  if (!duel)
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner className="h-8 w-8 text-primary" />
      </div>
    )

  if (playing)
    return (
      <div className="page">
        <DuelBoard
          code={code}
          mode={duel.mode}
          questions={duel.questions!}
          answered={duel.me?.answered ?? []}
          onDone={(d) => {
            setDuel(d)
            if (user && d.xp) bumpUser({ xp: user.xp + d.xp })
          }}
        />
      </div>
    )
  if (duel.me?.finished) return <div className="page max-w-xl">{duel.status === 'completed' ? <DuelResult duel={duel} /> : <ShareCard duel={duel} />}</div>

  const mine = Boolean(user && duel.status === 'pending')
  const closed = duel.status === 'completed' ? 'duel.taken' : duel.status === 'expired' ? 'duel.expired' : null
  return (
    <div className="page max-w-xl space-y-4">
      <div className="card space-y-4 p-6 text-center" data-testid="duel-intro">
        <div className="text-5xl">⚔️</div>
        <div className="flex justify-center">
          <Avatar name={duel.challenger.name} url={duel.challenger.avatar_url} size={72} />
        </div>
        <h1 className="h1">{mine ? t('duel.ready') : t('duel.challenges_you', { name: duel.challenger.name || t('duel.guest') })}</h1>
        <div className="flex flex-wrap justify-center gap-2">
          <span className="chip bg-line">{duel.track.toUpperCase()}</span>
          <span className="chip bg-line">{t(`game.${duel.mode}`)}</span>
          <span className="chip bg-line">{t('duel.words_n', { n: duel.total })}</span>
          {duel.mode === 'speed' && <span className="chip bg-line">{LANG_META[duel.translation_lang].flag}</span>}
        </div>
        {duel.creator?.score !== undefined && (
          <p className="text-lg font-black text-primary">{t('duel.to_beat', { score: duel.creator.score, total: duel.total, sec: seconds(duel.creator.time_ms ?? 0) })}</p>
        )}
        {closed ? (
          <p className="rounded-2xl bg-error/15 p-3 font-bold text-error">{t(closed)}</p>
        ) : (
          <>
            <button className="btn-primary w-full" disabled={busy} onClick={() => void start()}>
              {busy ? <Spinner className="h-5 w-5" /> : <Play className="h-5 w-5" />} {t('common.start')}
            </button>
            {!user && <p className="text-sm text-muted">{t('duel.guest_hint')}</p>}
          </>
        )}
        {closed && <Link className="btn-soft w-full" to="/duel">⚔️ {t('duel.new')}</Link>}
      </div>
    </div>
  )
}

/** The creator (or the first player of a rematch) has played: invite the opponent. */
function ShareCard({ duel }: { duel: Duel }) {
  const t = useT()
  const me = duel.me!
  const link = duel.telegram_link || duel.web_link
  const text = t('duel.share_text', { name: duel.challenger.name, score: me.score, total: duel.total, sec: seconds(me.time_ms) })
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${text}\n${duel.web_link}`)
      toast.ok(t('duel.copied'))
    } catch {
      toast.info(duel.web_link)
    }
  }
  return (
    <div className="space-y-4" data-testid="duel-share">
      <div className="card space-y-3 bg-tint p-6 text-center text-tint-ink">
        <div className="text-6xl">🃏</div>
        <div className="text-5xl font-black">
          {me.score}/{duel.total}
        </div>
        <div className="font-bold opacity-80">⏱ {seconds(me.time_ms)}s</div>
        <p className="font-bold">{text}</p>
      </div>
      {duel.status === 'expired' ? (
        <p className="rounded-2xl bg-error/15 p-3 text-center font-bold text-error">{t('duel.expired')}</p>
      ) : (
        <>
          <button className="btn w-full bg-[#229ED9] text-white" onClick={() => shareToTelegram(link, text)}>
            <Send className="h-5 w-5" /> {t('duel.share_tg')}
          </button>
          <button className="btn-ghost w-full" onClick={() => void copy()}>
            <Copy className="h-5 w-5" /> {t('duel.copy_link')}
          </button>
          <p className="text-center text-sm text-muted">{t('duel.wait_text')}</p>
        </>
      )}
      <ReviewList duel={duel} />
    </div>
  )
}

function SideCard({ side, winner, label }: { side: DuelSide | null; winner: boolean; label: string }) {
  const t = useT()
  const name = side?.name || t('duel.guest')
  return (
    <motion.div animate={winner ? { scale: [1, 1.06, 1] } : {}} transition={{ repeat: winner ? 2 : 0, duration: 0.6 }} className={`card flex flex-col items-center gap-1 p-4 text-center ${winner ? 'ring-4 ring-accent' : ''}`}>
      <div className="h-7 text-2xl">{winner ? '👑' : ''}</div>
      <Avatar name={name} url={side?.avatar_url} size={56} />
      <div className="w-full truncate font-black">{name}</div>
      <div className="text-xs text-muted">{label}</div>
      <div className="text-3xl font-black">{side?.score ?? '–'}</div>
      <div className="text-sm font-bold text-muted">⏱ {seconds(side?.time_ms ?? 0)}s</div>
      <div className="text-sm font-bold text-muted">🎯 {side?.accuracy ?? 0}%</div>
    </motion.div>
  )
}

function DuelResult({ duel }: { duel: Duel }) {
  const t = useT()
  const nav = useNavigate()
  const user = useApp((s) => s.user)
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const outcome = duel.outcome ?? 'draw'
  useEffect(() => {
    if (outcome === 'win') feedbackWin()
    else burst(ref.current)
  }, [outcome])
  const rematch = async () => {
    setBusy(true)
    try {
      const d = await duelApi.rematch(duel.code)
      nav(`/duel/${d.code}`)
    } catch {
      toast.err(t('err.generic'))
      setBusy(false)
    }
  }
  const iAmCreator = duel.me?.role === 'creator'
  const mySide = iAmCreator ? duel.creator : duel.opponent
  const other = iAmCreator ? duel.opponent : duel.creator
  return (
    <div ref={ref} className="space-y-4" data-testid="duel-result">
      <div className="text-center">
        <div className="text-6xl">{outcome === 'win' ? '🏆' : outcome === 'draw' ? '🤝' : '😅'}</div>
        <h1 className="h1 mt-1">{t(`duel.${outcome}`)}</h1>
        {!duel.me?.is_guest && duel.xp !== undefined && <span className="chip mt-2 bg-accent/30 font-black">+{duel.xp} XP</span>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <SideCard side={mySide} winner={outcome === 'win'} label={t('duel.you')} />
        <SideCard side={other} winner={outcome === 'loss'} label={t('duel.rival')} />
      </div>
      {duel.me?.is_guest && !user ? (
        <Link className="btn-primary w-full" to={`/login?next=/duel/${duel.code}`}>
          <UserPlus className="h-5 w-5" /> {t('duel.save_result')}
        </Link>
      ) : (
        <ActionRow>
          <button className="btn-primary" disabled={busy} onClick={() => void rematch()}>
            <RotateCcw className="h-5 w-5" /> {t('duel.rematch')}
          </button>
          <Link className="btn-soft" to="/duel">
            <UserPlus className="h-5 w-5" /> {t('duel.invite_other')}
          </Link>
        </ActionRow>
      )}
      <ReviewList duel={duel} />
    </div>
  )
}

function ReviewList({ duel }: { duel: Duel }) {
  if (!duel.review?.length) return null
  return (
    <ul className="card divide-y divide-line p-4 text-sm">
      {duel.review.map((r) => (
        <li key={r.term} className="flex gap-2 py-2">
          <span>{r.correct ? '✅' : '❌'}</span>
          <span className="font-extrabold">{r.term}</span>
          <span className="font-read text-muted">— {r.answer}</span>
        </li>
      ))}
    </ul>
  )
}
