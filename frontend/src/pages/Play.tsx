import { ArrowLeft, Play as PlayIcon } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Results, RoundComplete } from '../components/Results'
import { SourcePicker, type SourceChoice } from '../components/SourcePicker'
import { EmptyState, ErrorState, Segmented, Spinner, Toggle } from '../components/ui'
import { GAME_LIMITS, gameInfo } from '../games/catalog'
import { isAvailable, supportsReverse, usableItems } from '../games/direction'
import { BOARD_SIZES, shuffle, splitRounds, type Difficulty } from '../games/matchMachine'
import { accuracyOf, createSession, otherSetPath, sessionReducer, totals } from '../games/session'
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
        <EmptyState emoji="🎩" title={t('game.german_only')} text={t('game.german_only_text')} action={<Link className="btn-primary" to="/games">{t('nav.games')}</Link>} />
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

type LoadPhase = 'loading' | 'error' | 'empty' | 'ready'

function buildRounds(items: GameItem[], game: GameId, difficulty: Difficulty): GameItem[][] {
  return game === 'match' ? splitRounds(items, BOARD_SIZES[difficulty]) : [items]
}

function Runner({ game, source, params }: { game: GameId; source: Source; params: URLSearchParams }) {
  const t = useT()
  const track = useApp((s) => s.track)
  const bumpUser = useApp((s) => s.bumpUser)
  const reverse = params.get('reverse') === '1'
  const difficulty = (params.get('difficulty') as Difficulty) || 'medium'
  const [load, setLoad] = useState<LoadPhase>('loading')
  const [error, setError] = useState<unknown>(null)
  const [items, setItems] = useState<GameItem[]>([])
  const [session, dispatch] = useReducer(sessionReducer, createSession([]))
  const [daily, setDaily] = useState<{ already_played?: boolean; my_score?: number | null; score?: number }>({})
  const submitted = useRef(new Set<string>())

  const fetchItems = useCallback(async () => {
    setLoad('loading')
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
      dispatch({ type: 'RESTART', rounds: buildRounds(usable, game, difficulty) })
      setLoad(usable.length ? 'ready' : 'empty')
    } catch (e) {
      setError(e)
      setLoad('error')
    }
  }, [game, track, source, params, difficulty])

  useEffect(() => {
    void fetchItems()
  }, [fetchItems])

  // Save every finished round to the backend exactly once (keyed by playId + round).
  useEffect(() => {
    for (const stat of session.stats) {
      const key = `${session.playId}-${stat.round}`
      if (stat.xp !== null || submitted.current.has(key)) continue
      submitted.current.add(key)
      const playId = session.playId
      if (!stat.results.length) {
        dispatch({ type: 'SAVED', playId, round: stat.round, xp: 0 })
        continue
      }
      api
        .post<ResultsResponse>('/games/results/', {
          game,
          track,
          source,
          results: stat.results,
          duration_ms: Math.round(stat.durationMs),
          combo_max: stat.comboMax ?? 0,
        })
        .then((r) => {
          dispatch({ type: 'SAVED', playId, round: stat.round, xp: r.xp_earned, newAchievements: r.new_achievements, learnedNow: r.learned_now.length })
          bumpUser({ xp: r.xp_total, streak: r.streak, level: r.level })
          if (r.daily) setDaily((d) => ({ ...d, score: r.daily!.score }))
        })
        .catch(() => dispatch({ type: 'SAVED', playId, round: stat.round, xp: 0 }))
    }
  }, [session.stats, session.playId, game, track, source, bumpUser])

  const onFinish = useCallback(
    (o: GameOutcome) => dispatch({ type: 'ROUND_DONE', results: o.results, durationMs: o.durationMs, flips: o.flips, comboMax: o.comboMax }),
    [],
  )
  // "Yangi o'yin": same word set, freshly shuffled, from round 1.
  const newGame = useCallback(() => {
    const reshuffled = shuffle(items)
    setItems(reshuffled)
    dispatch({ type: 'RESTART', rounds: buildRounds(reshuffled, game, difficulty) })
    window.scrollTo({ top: 0 })
  }, [items, game, difficulty])
  const nextRound = useCallback(() => {
    dispatch({ type: 'NEXT_ROUND' })
    window.scrollTo({ top: 0 })
  }, [])

  if (load === 'loading')
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner className="h-8 w-8 text-primary" />
      </div>
    )
  if (load === 'error') return <div className="page"><ErrorState error={error} onRetry={fetchItems} /></div>
  if (load === 'empty')
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
  const total = session.rounds.length
  const lastStat = session.stats[session.stats.length - 1]

  return (
    <div className="mx-auto w-full max-w-5xl px-3 pb-10 pt-3 md:px-4">
      {session.status === 'playing' && (
        <>
          {game === 'daily' && daily.already_played && <div className="mb-3 rounded-2xl bg-accent/25 p-3 text-center text-sm font-bold">{t('daily.already', { score: daily.my_score ?? 0 })}</div>}
          {total > 1 && <div className="mb-2 text-center text-sm font-extrabold text-muted">{t('play.round_of', { n: session.index + 1, total })}</div>}
          <Suspense fallback={<Spinner className="mx-auto mt-20 h-8 w-8 text-primary" />}>
            <Game key={`${session.playId}-${session.index}`} items={session.rounds[session.index]} track={track} reverse={reverse} onFinish={onFinish} />
          </Suspense>
        </>
      )}

      {session.status === 'round_complete' && lastStat && (
        <RoundComplete
          round={lastStat.round}
          total={total}
          durationMs={lastStat.durationMs}
          flips={lastStat.flips}
          accuracy={accuracyOf(lastStat.results)}
          xp={lastStat.xp}
          saving={lastStat.xp === null}
          onNext={nextRound}
        />
      )}

      {session.status === 'game_complete' &&
        (() => {
          const sum = totals(session)
          return (
            <Results
              track={track}
              durationMs={sum.durationMs}
              flips={sum.flips}
              accuracy={sum.accuracy}
              xp={sum.xp}
              saving={sum.saving}
              missed={sum.missed}
              newAchievements={sum.newAchievements}
              learnedNow={sum.learnedNow}
              onNewGame={newGame}
              otherSetTo={game === 'daily' || game === 'review' ? undefined : otherSetPath(source, params)}
              extra={
                game === 'daily' && daily.score !== undefined ? (
                  <div className="mt-2 space-y-2">
                    <div className="text-lg font-black text-primary">{t('daily.score', { score: daily.score })}</div>
                    <Link to="/leaderboard?tab=daily" className="btn-soft">
                      🏆 {t('daily.leaderboard')}
                    </Link>
                  </div>
                ) : null
              }
            />
          )
        })()}
    </div>
  )
}
