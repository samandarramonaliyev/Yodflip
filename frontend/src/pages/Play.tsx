import { ArrowLeft, ChevronDown, Play as PlayIcon } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ExamComplete, LevelComplete, LevelRoundSummary } from '../components/LevelProgress'
import { Results, RoundComplete } from '../components/Results'
import { SourcePicker, type SourceChoice } from '../components/SourcePicker'
import { TranslationPicker, type PickerChoice } from '../components/TranslationPicker'
import { EmptyState, ErrorState, Segmented, Spinner, Toggle } from '../components/ui'
import { GAME_LIMITS, gameInfo } from '../games/catalog'
import { isAvailable, supportsReverse, usableItems } from '../games/direction'
import { BOARD_SIZES, shuffle, splitRounds, type Difficulty } from '../games/matchMachine'
import { accuracyOf, createSession, duelPath, otherSetPath, sessionReducer, totals } from '../games/session'
import type { GameId, GameItem, GameOutcome, GameProps, Source } from '../games/types'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useMainButton, useTelegramBack } from '../lib/hooks'
import { autoStartChoice, chipLabel, DEFAULT_PREF, isValidPair, needsPicker, type Direction, type TrLang, type TranslationPref } from '../lib/translation'
import type { LevelProgress, LevelRoundOutcome, ResultsResponse } from '../lib/types'
import { useApp } from '../store/app'

const COMPONENTS: Record<string, React.LazyExoticComponent<React.ComponentType<GameProps>>> = {
  match: lazy(() => import('../games/MatchGame')),
  flashcards: lazy(() => import('../games/Flashcards')),
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
  // Memorization games ask "Qaysi tilga tarjima qilinsin?" first (definition games / Der·Die·Das / decks never do).
  const withLang = (choice: { tl: TrLang; dir: Direction }) => {
    const q = new URLSearchParams(params)
    q.set('tl', choice.tl)
    q.set('dir', choice.dir)
    q.delete('reverse')
    setParams(q, { replace: true })
  }
  if (needsPicker(game as GameId, source) && !isValidPair(track, params.get('tl')))
    return <PickerGate key={track} track={track} source={source} setId={params.get('id')} onDone={withLang} />
  return <Runner key={`${track}-${params.toString()}`} game={game as GameId} source={source} params={params} onChangeLang={withLang} />
}

/** Saved per user and track on the server, so the website and the Mini App share it. */
export function saveTranslationPref(track: string, c: PickerChoice) {
  void api
    .request('PUT', '/auth/translation-prefs/', {
      body: { track, preferred_translation_lang: c.lang, preferred_direction: c.direction, remember_choice: c.remember },
    })
    .catch(() => null)
}

function useSetLangs(setId: string | null, source: Source) {
  const [langs, setLangs] = useState<TrLang[] | undefined>(undefined)
  useEffect(() => {
    if (source !== 'set' || !setId) return
    api
      .get<{ available_langs?: TrLang[] }>(`/sets/${setId}/`)
      .then((s) => setLangs(s.available_langs))
      .catch(() => setLangs(undefined))
  }, [setId, source])
  return langs
}

export function PickerGate({ track, source, setId, onDone }: { track: 'en' | 'de'; source: Source; setId: string | null; onDone: (c: { tl: TrLang; dir: Direction }) => void }) {
  const nav = useNavigate()
  const [pref, setPref] = useState<TranslationPref | null>(null)
  const available = useSetLangs(setId, source)
  useEffect(() => {
    let alive = true
    api
      .get<Record<string, TranslationPref>>('/auth/translation-prefs/')
      .then((all) => alive && setPref(all[track] ?? DEFAULT_PREF(track)))
      .catch(() => alive && setPref(DEFAULT_PREF(track)))
    return () => {
      alive = false
    }
  }, [track])
  const auto = autoStartChoice(pref, track)
  const autoOk = auto && (!available || available.includes(auto.tl))
  useEffect(() => {
    if (autoOk && auto) onDone(auto) // "Tanlovimni eslab qol": start directly
  }, [autoOk]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!pref || autoOk)
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner className="h-8 w-8 text-primary" />
      </div>
    )
  return (
    <div className="page">
      <TranslationPicker
        open
        track={track}
        available={available}
        initial={{ lang: pref.preferred_translation_lang, direction: pref.preferred_direction, remember: pref.remember_choice }}
        onClose={() => nav(-1)}
        onStart={(c) => {
          saveTranslationPref(track, c)
          onDone({ tl: c.lang, dir: c.direction })
        }}
      />
    </div>
  )
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
        {supportsReverse(game) && !needsPicker(game, choice?.source ?? null) && <Toggle checked={reverse} onChange={setReverse} label={t('play.reverse')} />}
        {needsPicker(game, choice?.source ?? null) && <p className="text-sm text-muted">🌐 {t('tr.setup_hint')}</p>}
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

type LoadPhase = 'loading' | 'error' | 'empty' | 'ready' | 'completed' | 'pool_done'

/** Words per server-built level round (Match uses the board size of the difficulty). */
export const LEVEL_ROUND_SIZE: Partial<Record<GameId, number>> = { speed: 24, builder: 10, falling: 24, memory: 6, derdiedas: 20, flashcards: 20 }

interface LevelRoundResponse {
  session_id: string | null
  completed: boolean
  pool_done: boolean
  words: GameItem[]
  progress: LevelProgress
}

interface LevelState {
  sessionId: string | null
  before: LevelProgress | null
  outcome: LevelRoundOutcome | null
}

function buildRounds(items: GameItem[], game: GameId, difficulty: Difficulty): GameItem[][] {
  return game === 'match' ? splitRounds(items, BOARD_SIZES[difficulty]) : [items]
}

function Runner({ game, source, params, onChangeLang }: { game: GameId; source: Source; params: URLSearchParams; onChangeLang: (c: { tl: TrLang; dir: Direction }) => void }) {
  const t = useT()
  const track = useApp((s) => s.track)
  const bumpUser = useApp((s) => s.bumpUser)
  const picker = needsPicker(game, source)
  const tl = (isValidPair(track, params.get('tl')) ? params.get('tl') : 'uz') as TrLang
  const dir: Direction = params.get('dir') === 'reverse' ? 'reverse' : 'forward'
  const reverse = dir === 'reverse' || params.get('reverse') === '1'
  const [activeLang, setActiveLang] = useState<TrLang>(tl)
  const [chipOpen, setChipOpen] = useState(false)
  const difficulty = (params.get('difficulty') as Difficulty) || 'medium'
  const [load, setLoad] = useState<LoadPhase>('loading')
  const [error, setError] = useState<unknown>(null)
  const [items, setItems] = useState<GameItem[]>([])
  const [session, dispatch] = useReducer(sessionReducer, createSession([]))
  const [daily, setDaily] = useState<{ already_played?: boolean; my_score?: number | null; score?: number }>({})
  const submitted = useRef(new Set<string>())
  const isExam = source === 'exam'
  const isLevel = source === 'level' || isExam // server-built rounds: found = learned
  const [levelRound, setLevelRound] = useState<LevelState>({ sessionId: null, before: null, outcome: null })
  const sessionRef = useRef<string | null>(null)

  const fetchItems = useCallback(async () => {
    setLoad('loading')
    try {
      if (isLevel) {
        // FOUND = LEARNED: the server builds every level round (unfound words first, "takror" fillers last).
        const size = game === 'match' ? BOARD_SIZES[difficulty] : (LEVEL_ROUND_SIZE[game] ?? 10)
        const lr = await api.get<LevelRoundResponse>(isExam ? `/exams/${params.get('pack')}/round/` : `/levels/${track}/${params.get('level') || 'A1'}/round/`, {
          size,
          game,
          pack: isExam ? undefined : params.get('pack'),
          topic: params.get('topic'),
          translation_lang: tl,
          direction: dir,
        })
        sessionRef.current = lr.session_id
        setLevelRound({ sessionId: lr.session_id, before: lr.progress, outcome: null })
        if (lr.completed) return setLoad('completed')
        if (lr.pool_done) return setLoad('pool_done')
        const usable = usableItems(lr.words, game)
        setItems(usable)
        dispatch({ type: 'RESTART', rounds: [usable] })
        setLoad(usable.length ? 'ready' : 'empty')
        return
      }
      const r = await api.get<{ items: GameItem[]; translation_lang?: TrLang; already_played?: boolean; my_score?: number | null }>('/games/words/', {
        game,
        track,
        source,
        translation_lang: source === 'deck' ? undefined : tl,
        direction: dir,
        level: params.get('level'),
        pack: params.get('pack'),
        topic: params.get('topic'),
        id: params.get('id'),
        ids: params.get('ids'),
        limit: GAME_LIMITS[game],
      })
      const usable = usableItems(r.items, game)
      if (r.translation_lang) setActiveLang(r.translation_lang)
      setItems(usable)
      setDaily({ already_played: r.already_played, my_score: r.my_score })
      dispatch({ type: 'RESTART', rounds: buildRounds(usable, game, difficulty) })
      setLoad(usable.length ? 'ready' : 'empty')
    } catch (e) {
      setError(e)
      setLoad('error')
    }
  }, [game, track, source, isLevel, isExam, params, difficulty, tl, dir])

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
      const sessionId = sessionRef.current
      if (!stat.results.length) {
        dispatch({ type: 'SAVED', playId, round: stat.round, xp: 0 })
        if (isLevel) setLevelRound((l) => (l.before ? { ...l, outcome: { session_id: sessionId || '', new_found_count: 0, progress: l.before, completed_now: false, bonus_xp: 0 } } : l))
        continue
      }
      const save = async () => {
        if (isLevel && sessionId && game !== 'flashcards') {
          // Flashcards save each answer themselves (/words/flash/answer/). Others: report every answer (idempotent on the server), then close the round.
          const answers = stat.results.filter((r) => r.word_id).map((r) => ({ word_id: r.word_id, correct: r.correct }))
          if (answers.length) await api.post('/levels/answer/', { session_id: sessionId, answers }).catch(() => null)
        }
        return api.post<ResultsResponse>('/games/results/', {
          game,
          track,
          source,
          session_id: isLevel ? sessionId : undefined,
          translation_lang: picker || source === 'deck' ? activeLang : undefined,
          results: stat.results,
          duration_ms: Math.round(stat.durationMs),
          combo_max: stat.comboMax ?? 0,
        })
      }
      save()
        .then((r) => {
          if (r.level_round) setLevelRound((l) => ({ ...l, outcome: r.level_round! }))
          dispatch({ type: 'SAVED', playId, round: stat.round, xp: r.xp_earned, newAchievements: r.new_achievements, learnedNow: r.learned_now.length })
          bumpUser({ xp: r.xp_total, streak: r.streak, level: r.level })
          if (r.daily) setDaily((d) => ({ ...d, score: r.daily!.score }))
        })
        .catch(() => dispatch({ type: 'SAVED', playId, round: stat.round, xp: 0 }))
    }
  }, [session.stats, session.playId, game, track, source, isLevel, bumpUser, picker, activeLang])

  const onFinish = useCallback(
    (o: GameOutcome) => dispatch({ type: 'ROUND_DONE', results: o.results, durationMs: o.durationMs, flips: o.flips, comboMax: o.comboMax }),
    [],
  )
  // "Yangi o'yin": same word set, freshly shuffled, from round 1.
  const newGame = useCallback(() => {
    if (isLevel) {
      void fetchItems() // a fresh server round: found words are left out
      window.scrollTo({ top: 0 })
      return
    }
    const reshuffled = shuffle(items)
    setItems(reshuffled)
    dispatch({ type: 'RESTART', rounds: buildRounds(reshuffled, game, difficulty) })
    window.scrollTo({ top: 0 })
  }, [items, game, difficulty, isLevel, fetchItems])
  // "Topa olmaganlarni qayta o'rganish": restart with only the missed cards.
  const retryMissed = useCallback((missed: GameItem[]) => {
    if (!missed.length) return
    dispatch({ type: 'RESTART', rounds: [missed] })
    window.scrollTo({ top: 0 })
  }, [])
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
  if (load === 'completed')
    return (
      <div className="page max-w-xl">
        {isExam ? <ExamComplete slug={params.get('pack') || ''} /> : <LevelComplete level={params.get('level') || 'A1'} bonusXp={0} />}
      </div>
    )
  if (load === 'pool_done')
    return (
      <div className="page">
        <EmptyState
          emoji="✅"
          title={t('level.pool_done')}
          text={t(isExam ? 'exam.topic_done' : 'level.pool_done_text')}
          action={<Link className="btn-primary" to={otherSetPath(source, params)}>{t('res.other_set')}</Link>}
        />
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
      {picker && (
        <div className="mb-2 flex justify-end">
          <button className="chip gap-1 bg-primary-soft text-primary" onClick={() => setChipOpen(true)} data-testid="lang-chip" aria-label={chipLabel(track, tl, dir)}>
            {chipLabel(track, tl, dir)} <ChevronDown className="h-3.5 w-3.5" />
          </button>
          <TranslationPicker
            open={chipOpen}
            track={track}
            initial={{ lang: tl, direction: dir, remember: false }}
            onClose={() => setChipOpen(false)}
            onStart={(c) => {
              setChipOpen(false)
              saveTranslationPref(track, c)
              onChangeLang({ tl: c.lang, dir: c.direction }) // new URL params -> the round restarts
            }}
          />
        </div>
      )}
      {session.status === 'playing' && (
        <>
          {game === 'daily' && daily.already_played && <div className="mb-3 rounded-2xl bg-accent/25 p-3 text-center text-sm font-bold">{t('daily.already', { score: daily.my_score ?? 0 })}</div>}
          {total > 1 && <div className="mb-2 text-center text-sm font-extrabold text-muted">{t('play.round_of', { n: session.index + 1, total })}</div>}
          <Suspense fallback={<Spinner className="mx-auto mt-20 h-8 w-8 text-primary" />}>
            <Game key={`${session.playId}-${session.index}`} items={session.rounds[session.index]} track={track} reverse={reverse} translationLang={activeLang} onFinish={onFinish} {...(game === 'flashcards' ? { sessionId: sessionRef.current } : {})} />
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
          const lr = levelRound.outcome
          return (
            <>
            {isLevel && lr && (lr.completed_now || lr.progress.completed) && (
              <div className="mx-auto mb-4 w-full max-w-xl">
                {isExam ? <ExamComplete slug={params.get('pack') || ''} /> : <LevelComplete level={lr.progress.level} bonusXp={lr.bonus_xp} />}
              </div>
            )}
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
              duelTo={duelPath(source, params)}
              otherSetTo={game === 'daily' || game === 'review' ? undefined : otherSetPath(source, params)}
              extraActions={
                game === 'flashcards' && sum.missed.length > 0 ? (
                  <button className="btn-soft" onClick={() => retryMissed(sum.missed)} data-testid="retry-missed">
                    🔁 {t('flash.retry_missed')} ({sum.missed.length})
                  </button>
                ) : null
              }
              extra={
                isLevel && levelRound.before ? (
                  <>
                    {game === 'flashcards' && <FlashSummary results={session.stats.flatMap((s) => s.results)} />}
                    <LevelRoundSummary before={levelRound.before} after={lr?.progress ?? null} newFound={lr ? lr.new_found_count : null} />
                  </>
                ) : game === 'flashcards' ? (
                  <FlashSummary results={session.stats.flatMap((s) => s.results)} />
                ) : isLevel && levelRound.before ? (
                  <LevelRoundSummary before={levelRound.before} after={lr?.progress ?? null} newFound={lr ? lr.new_found_count : null} />
                ) : game === 'daily' && daily.score !== undefined ? (
                  <div className="mt-2 space-y-2">
                    <div className="text-lg font-black text-primary">{t('daily.score', { score: daily.score })}</div>
                    <Link to="/leaderboard?tab=daily" className="btn-soft">
                      🏆 {t('daily.leaderboard')}
                    </Link>
                  </div>
                ) : null
              }
            />
            </>
          )
        })()}
    </div>
  )
}

function FlashSummary({ results }: { results: { correct: boolean }[] }) {
  const t = useT()
  const known = results.filter((r) => r.correct).length
  return (
    <div className="mt-3 flex justify-center gap-3 text-sm font-black" data-testid="flash-summary">
      <span className="rounded-full bg-success/15 px-3 py-1 text-success">✅ {t('flash.known')}: {known}</span>
      <span className="rounded-full bg-[#FF7675]/15 px-3 py-1 text-[#d64545]">❌ {t('flash.missed')}: {results.length - known}</span>
    </div>
  )
}
