import { ArrowLeft, Play as PlayIcon } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Results } from '../components/Results'
import { SourcePicker, type SourceChoice } from '../components/SourcePicker'
import { EmptyState, ErrorState, Segmented, Spinner, Toggle } from '../components/ui'
import { GAME_LIMITS, gameInfo } from '../games/catalog'
import { isAvailable, supportsReverse, usableItems } from '../games/direction'
import { BOARD_SIZES, splitRounds, type Difficulty } from '../games/matchMachine'
import type { GameId, GameItem, GameOutcome, GameProps, Source } from '../games/types'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useMainButton, useTelegramBack } from '../lib/hooks'
import type { ResultsResponse } from '../lib/types'
import { useApp } from '../store/app'

const COMPONENTS: Record<string, React.LazyExoticComponent<React.ComponentType<GameProps>>> = {
  match: lazy(() => import('../games/MatchGame')),
  speed: lazy(() => import('../games/SpeedMatch')),
  builder: lazy(() => import('../games/WordBuilder')),
  falling: lazy(() => import('../games/FallingWords')),
  memory: lazy(() => import('../games/MemoryPairs')),
  derdiedas: lazy(() => import('../games/DerDieDas')),
  review: lazy(() => import('../games/QuizGame')),
  daily: lazy(() => import('../games/QuizGame')),
}

const FIXED_SOURCE: Partial<Record<GameId, Source>> = { review: 'review', daily: 'daily' }

export default function Play() {
  const { game = 'match' } = useParams<{ game: GameId }>()
  const [params, setParams] = useSearchParams()
  const track = useApp((s) => s.track)
  const t = useT()
  useTelegramBack('/games')
  const info = gameInfo(game as GameId)

  if (!info || !COMPONENTS[game]) return <div className="page"><EmptyState emoji="🤔" title={t('err.not_found')} action={<Link className="btn-primary" to="/games">{t('nav.games')}</Link>} /></div>
  if (!isAvailable(game as GameId, track))
    return (
      <div className="page">
        <EmptyState emoji="🇩🇪" title={t('game.german_only')} text={t('game.german_only_text')} action={<Link className="btn-primary" to="/games">{t('nav.games')}</Link>} />
      </div>
    )

  const source = (params.get('source') as Source | null) ?? FIXED_SOURCE[game as GameId] ?? null
  if (!source) return <Setup game={game as GameId} onStart={(q) => setParams(q)} />
  return <Runner key={`${track}-${params.toString()}`} game={game as GameId} source={source} params={params} />
}

function Setup({ game, onStart }: { game: GameId; onStart: (q: Record<string, string>) => void }) {
  const t = useT()
  const nav = useNavigate()
  const [choice, setChoice] = useState<SourceChoice | null>(null)
  const [reverse, setReverse] = useState(false)
  const [difficulty, setDifficulty] = useState<Difficulty>('medium')
  const start = () => {
    if (!choice) return
    const q: Record<string, string> = { source: choice.source }
    if (choice.level) q.level = choice.level
    if (choice.pack) q.pack = choice.pack
    if (choice.id) q.id = String(choice.id)
    if (reverse) q.reverse = '1'
    if (game === 'match') q.difficulty = difficulty
    onStart(q)
  }
  useMainButton(choice ? t('common.start') : null, start, Boolean(choice))
  return (
    <div className="page max-w-2xl space-y-4">
      <div className="flex items-center gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => nav('/games')} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <h1 className="h1">
          {gameInfo(game)?.emoji} {t(`game.${game}`)}
        </h1>
      </div>
      <p className="text-muted">{t(`game.${game}_desc`)}</p>
      <div className="card space-y-4 p-4">
        <h2 className="h2">{t('src.choose')}</h2>
        <SourcePicker value={choice} onChange={setChoice} />
      </div>
      <div className="card space-y-2 p-4">
        {supportsReverse(game) && <Toggle checked={reverse} onChange={setReverse} label={t('play.reverse')} />}
        {game === 'match' && (
          <div className="space-y-2">
            <div className="font-bold">{t('play.difficulty')}</div>
            <Segmented
              value={difficulty}
              onChange={setDifficulty}
              options={(Object.keys(BOARD_SIZES) as Difficulty[]).map((d) => ({ value: d, label: `${t(`play.${d}`)} · ${BOARD_SIZES[d]}` }))}
            />
          </div>
        )}
      </div>
      <button className="btn-primary w-full" disabled={!choice} onClick={start}>
        <PlayIcon className="h-5 w-5" /> {t('common.start')}
      </button>
    </div>
  )
}

type Phase = 'loading' | 'error' | 'empty' | 'playing' | 'results'

function Runner({ game, source, params }: { game: GameId; source: Source; params: URLSearchParams }) {
  const t = useT()
  const track = useApp((s) => s.track)
  const bumpUser = useApp((s) => s.bumpUser)
  const reverse = params.get('reverse') === '1'
  const difficulty = (params.get('difficulty') as Difficulty) || 'medium'
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<unknown>(null)
  const [items, setItems] = useState<GameItem[]>([])
  const [round, setRound] = useState(0)
  const [playKey, setPlayKey] = useState(0)
  const [outcome, setOutcome] = useState<GameOutcome | null>(null)
  const [server, setServer] = useState<ResultsResponse | null>(null)
  const [saving, setSaving] = useState(false)
  const [daily, setDaily] = useState<{ already_played?: boolean; my_score?: number | null }>({})

  const load = useCallback(async () => {
    setPhase('loading')
    try {
      const r = await api.get<{ items: GameItem[]; already_played?: boolean; my_score?: number | null }>('/games/words/', {
        game,
        track,
        source,
        level: params.get('level'),
        pack: params.get('pack'),
        id: params.get('id'),
        limit: GAME_LIMITS[game],
      })
      const usable = usableItems(r.items, game)
      setItems(usable)
      setDaily({ already_played: r.already_played, my_score: r.my_score })
      setRound(0)
      setPhase(usable.length ? 'playing' : 'empty')
    } catch (e) {
      setError(e)
      setPhase('error')
    }
  }, [game, track, source, params])

  useEffect(() => {
    void load()
  }, [load])

  const rounds = useMemo(() => (game === 'match' ? splitRounds(items, BOARD_SIZES[difficulty]) : [items]), [items, game, difficulty])
  const roundItems = rounds[round] || []

  const onFinish = async (o: GameOutcome) => {
    setOutcome(o)
    setServer(null)
    setPhase('results')
    if (!o.results.length) return
    setSaving(true)
    try {
      const r = await api.post<ResultsResponse>('/games/results/', {
        game,
        track,
        source,
        results: o.results,
        duration_ms: Math.round(o.durationMs),
        combo_max: o.comboMax ?? 0,
      })
      setServer(r)
      bumpUser({ xp: r.xp_total, streak: r.streak, level: r.level })
    } catch {
      /* results screen still shows local stats */
    } finally {
      setSaving(false)
    }
  }

  if (phase === 'loading')
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner className="h-8 w-8 text-primary" />
      </div>
    )
  if (phase === 'error') return <div className="page"><ErrorState error={error} onRetry={load} /></div>
  if (phase === 'empty')
    return (
      <div className="page">
        <EmptyState
          emoji={source === 'review' ? '🎉' : '📭'}
          title={source === 'review' ? t('play.nothing_due') : t('play.no_words')}
          text={source === 'review' ? t('play.nothing_due_text') : game === 'match' ? t('play.no_words_def') : t('play.no_words_text')}
          action={<Link className="btn-primary" to={`/play/${game === 'review' ? 'speed' : game}`}>{t('play.pick_other')}</Link>}
        />
      </div>
    )

  const Game = COMPONENTS[game]
  const missed = (() => {
    if (!outcome) return []
    const wrong = new Set(outcome.results.filter((r) => !r.correct).map((r) => r.term))
    return roundItems.filter((i) => wrong.has(i.term))
  })()
  const accuracy = outcome && outcome.results.length ? Math.round((100 * outcome.results.filter((r) => r.correct).length) / outcome.results.length) : 0
  const hasNextRound = game === 'match' && round < rounds.length - 1

  return (
    <div className="mx-auto w-full max-w-5xl px-3 pb-10 pt-3 md:px-4">
      {game === 'daily' && daily.already_played && phase === 'playing' && (
        <div className="mb-3 rounded-2xl bg-accent/25 p-3 text-center text-sm font-bold">{t('daily.already', { score: daily.my_score ?? 0 })}</div>
      )}
      {phase === 'playing' && (
        <>
          {rounds.length > 1 && (
            <div className="mb-2 text-center text-sm font-extrabold text-muted">{t('play.round_of', { n: round + 1, total: rounds.length })}</div>
          )}
          <Suspense fallback={<Spinner className="mx-auto mt-20 h-8 w-8 text-primary" />}>
            <Game key={`${round}-${playKey}`} items={roundItems} track={track} reverse={reverse} onFinish={onFinish} />
          </Suspense>
        </>
      )}
      {phase === 'results' && outcome && (
        <Results
          track={track}
          durationMs={outcome.durationMs}
          flips={outcome.flips}
          accuracy={accuracy}
          missed={missed}
          server={server}
          saving={saving}
          onReplay={() => {
            setPlayKey((k) => k + 1)
            setPhase('playing')
          }}
          onNext={
            hasNextRound
              ? () => {
                  setRound((r) => r + 1)
                  setPhase('playing')
                }
              : game === 'daily'
                ? undefined
                : () => void load()
          }
          nextLabel={hasNextRound ? t('res.next_round') : t('res.new_game')}
          extra={
            game === 'daily' && server?.daily ? (
              <div className="mt-2 space-y-2">
                <div className="text-lg font-black text-primary">{t('daily.score', { score: server.daily.score })}</div>
                <Link to="/leaderboard?tab=daily" className="btn-soft">
                  🏆 {t('daily.leaderboard')}
                </Link>
              </div>
            ) : null
          }
        />
      )}
    </div>
  )
}
