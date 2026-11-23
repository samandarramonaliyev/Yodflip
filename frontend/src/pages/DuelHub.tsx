import { Play } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { DuelStatsCard } from '../components/DuelStatsCard'
import { ListSkeleton, Segmented, Spinner, toast } from '../components/ui'
import { useT } from '../i18n'
import { api, ApiError } from '../lib/api'
import type { Duel, DuelStats } from '../lib/duel'
import type { ExamPackRow } from '../lib/exams'
import { useAsync, useMainButton, useTelegramBack } from '../lib/hooks'
import { allowedLangs, isValidPair, LANG_META, type TrLang } from '../lib/translation'
import type { Deck, LevelRow } from '../lib/types'
import { useApp } from '../store/app'

type SourceTab = 'level' | 'exam' | 'deck'

/** Create a duel: track, source, mode, translation language. The creator plays first. */
export default function DuelHub() {
  const t = useT()
  const nav = useNavigate()
  useTelegramBack('/')
  const [params] = useSearchParams()
  const { track, setTrack, lang: uiLang } = useApp()
  const preset = params.get('source') as SourceTab | null
  const [tab, setTab] = useState<SourceTab>(preset === 'deck' || preset === 'exam' ? preset : 'level')
  const [ref, setRef] = useState<string>(params.get('ref') ?? 'A1')
  const [mode, setMode] = useState<'speed' | 'match'>('speed')
  const [lang, setLang] = useState<TrLang>('uz')
  const [busy, setBusy] = useState(false)
  const levels = useAsync(() => api.get<{ levels: LevelRow[] }>('/words/levels/', { track }), [track])
  const decks = useAsync(() => api.get<Deck[]>('/decks/', { track }), [track])
  const exams = useAsync(() => api.get<{ packs: ExamPackRow[] }>('/exams/', { track }), [track])
  const stats = useAsync(() => api.get<DuelStats>('/duels/'), [])
  const tl: TrLang = isValidPair(track, lang) ? lang : 'uz'

  const options =
    tab === 'level'
      ? (levels.data?.levels ?? []).map((l) => ({ ref: l.level as string, label: `${l.level} · ${t(`cefr.${l.level}`)}`, sub: `${l.total}`, ok: l.unlocked }))
      : tab === 'exam'
        ? (exams.data?.packs ?? []).map((p) => ({ ref: p.slug, label: `${p.emoji} ${p.name[uiLang]}`, sub: `${p.total}`, ok: true }))
        : (decks.data ?? []).map((d) => ({ ref: String(d.id), label: d.name, sub: t('decks.cards_n', { n: d.card_count }), ok: d.card_count >= 10 }))
  const chosen = options.find((o) => o.ref === ref && o.ok)
  const loading = { level: levels, exam: exams, deck: decks }[tab].loading

  const create = async () => {
    if (!chosen || busy) return
    setBusy(true)
    try {
      const d = await api.post<Duel>('/duels/', { track, source: tab, source_ref: ref, mode, translation_lang: tl })
      nav(`/duel/${d.code}`)
    } catch (e) {
      const detail = e instanceof ApiError ? e.message : ''
      toast.err(t(detail === 'not_enough_words' ? 'duel.not_enough' : 'err.generic'))
      setBusy(false)
    }
  }
  useMainButton(chosen ? t('duel.create') : null, () => void create(), Boolean(chosen) && !busy)

  return (
    <div className="page max-w-2xl space-y-4">
      <h1 className="h1">⚔️ {t('duel.title')}</h1>
      <p className="text-muted">{t('duel.intro')}</p>

      {stats.data && stats.data.open.length > 0 && (
        <div className="card space-y-2 p-4">
          <h2 className="h2">{t('duel.open')}</h2>
          {stats.data.open.map((d) => (
            <Link key={d.code} to={`/duel/${d.code}`} className="flex min-h-[48px] items-center justify-between rounded-2xl bg-line/60 px-4 font-bold">
              <span>
                {d.track.toUpperCase()} · {d.source_label} · {t(`game.${d.mode}`)}
              </span>
              <span className="text-xs text-muted">{d.status === 'open' ? t('duel.waiting') : t('duel.your_turn')}</span>
            </Link>
          ))}
        </div>
      )}

      <div className="card space-y-4 p-4">
        <Segmented value={track} onChange={setTrack} options={[{ value: 'en', label: 'EN · English' }, { value: 'de', label: 'DE · Deutsch' }]} />
        <div>
          <div className="mb-1 font-bold">{t('duel.source')}</div>
          <Segmented
            value={tab}
            onChange={(v: SourceTab) => {
              setTab(v)
              setRef(v === 'level' ? 'A1' : '')
            }}
            options={[
              { value: 'level', label: t('src.levels') },
              { value: 'exam', label: t('nav.exams') },
              { value: 'deck', label: t('src.decks') },
            ]}
          />
          <div className="mt-2 max-h-[34vh] space-y-2 overflow-y-auto">
            {loading ? (
              <ListSkeleton rows={3} height="h-12" />
            ) : options.length ? (
              options.map((o) => (
                <button
                  key={o.ref}
                  disabled={!o.ok}
                  aria-pressed={ref === o.ref}
                  onClick={() => setRef(o.ref)}
                  className={`flex min-h-[48px] w-full items-center justify-between gap-2 rounded-2xl px-4 text-left font-bold disabled:opacity-40 ${ref === o.ref ? 'bg-primary text-white' : 'bg-line/60'}`}
                >
                  <span className="truncate">{o.label}</span>
                  <span className="shrink-0 text-xs opacity-80">{o.sub}</span>
                </button>
              ))
            ) : (
              <p className="py-4 text-center text-muted">{t('decks.empty')}</p>
            )}
          </div>
          {tab === 'deck' && <p className="mt-1 text-xs text-muted">{t('duel.deck_hint')}</p>}
        </div>
        <div>
          <div className="mb-1 font-bold">{t('duel.mode')}</div>
          <Segmented
            value={mode}
            onChange={setMode}
            options={[
              { value: 'speed', label: `⚡ ${t('game.speed')}` },
              { value: 'match', label: `🃏 ${t('game.match')}` },
            ]}
          />
        </div>
        {mode === 'speed' && tab !== 'deck' && (
          <div>
            <div className="mb-1 font-bold">{t('tr.title')}</div>
            <Segmented value={tl} onChange={setLang} options={allowedLangs(track).map((l) => ({ value: l, label: `${LANG_META[l].flag} ${LANG_META[l].short}` }))} />
          </div>
        )}
      </div>
      <button className="btn-primary w-full" disabled={!chosen || busy} onClick={() => void create()}>
        {busy ? <Spinner className="h-5 w-5" /> : <Play className="h-5 w-5" />} {t('duel.create')}
      </button>
      {stats.data && <DuelStatsCard stats={stats.data} />}
    </div>
  )
}
