import { ArrowLeft, ChevronLeft, ChevronRight, Pause, Play, Search, Star } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { SpeakButton } from '../components/SpeakButton'
import { EmptyState, ErrorState, ListSkeleton, Segmented, Toggle, toast } from '../components/ui'
import type { Track } from '../games/types'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync, useTelegramBack } from '../lib/hooks'
import { load, save } from '../lib/storage'
import { allowedLangs, isValidPair, LANG_META, type TranslationPref, type TrLang } from '../lib/translation'
import { speakToEnd, stopSpeech, useTts } from '../lib/tts'
import { useApp } from '../store/app'

interface StudyWord {
  id: number
  term: string
  word: string
  article: string
  pos: string
  definition: string
  translation: string
  translation_uz: string
  example: string
  example_tr: string
  topic: string
  learned: boolean
  want: boolean
  userword_id: number | null
}

interface StudyPage {
  track: Track
  lang: TrLang
  lesson: number
  lessons: number
  lesson_size: number
  total: number
  topics: { slug: string; emoji: string; name: Record<'uz' | 'en' | 'ru', string> }[]
  words: StudyWord[]
}

type Hide = 'none' | 'translation' | 'word'
const ARTICLE: Record<string, string> = { der: 'text-sky-600', die: 'text-rose-500', das: 'text-emerald-600' }
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** "So'zlar ro'yxati": read the words of a level or an exam pack. No game, no progress. */
export default function WordStudy() {
  const { level, slug } = useParams()
  const appTrack = useApp((s) => s.track)
  const id = slug ?? level ?? 'A1'
  const back = slug ? `/exams/${slug}` : `/levels/${id}`
  return <Study key={`${appTrack}-${id}`} id={id} isExam={Boolean(slug)} back={back} appTrack={appTrack} />
}

function Study({ id, isExam, back, appTrack }: { id: string; isExam: boolean; back: string; appTrack: Track }) {
  const t = useT()
  const nav = useNavigate()
  useTelegramBack(back)
  const ui = useApp((s) => s.lang)
  const setTrack = useApp((s) => s.setTrack)
  const storeKey = `wf.study.${isExam ? 'exam' : appTrack}.${id}`
  const [lesson, setLesson] = useState<number>(() => load<number>(storeKey, 1))
  const [lang, setLang] = useState<TrLang | null>(null)
  const [pref, setPref] = useState<TranslationPref | null>(null)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [topic, setTopic] = useState('')
  const [unlearned, setUnlearned] = useState(false)
  const [hide, setHide] = useState<Hide>('none')
  const [revealed, setRevealed] = useState<Set<number>>(new Set())
  const filtered = Boolean(search || topic || unlearned)
  const [filterLesson, setFilterLesson] = useState(1)
  const current = filtered ? filterLesson : lesson
  const url = isExam ? `/exams/${id}/study/` : `/levels/${appTrack}/${id}/words/`
  const { data, error, loading, reload, setData } = useAsync(
    () => (lang ? api.get<StudyPage>(url, { lesson: current, lang, search, topic, only_unlearned: unlearned || undefined }) : Promise.resolve(null)),
    [url, current, lang, search, topic, unlearned],
  )
  const track: Track = data?.track ?? appTrack

  useEffect(() => {
    api
      .get<Record<string, TranslationPref>>('/auth/translation-prefs/')
      .then((all) => {
        const p = all[appTrack]
        setPref(p ?? null)
        setLang(p && isValidPair(appTrack, p.preferred_translation_lang) ? p.preferred_translation_lang : 'uz')
      })
      .catch(() => setLang('uz'))
  }, [appTrack])
  useEffect(() => {
    const h = setTimeout(() => setSearch(query.trim()), 300)
    return () => clearTimeout(h)
  }, [query])
  useEffect(() => setFilterLesson(1), [search, topic, unlearned])
  useEffect(() => setRevealed(new Set()), [hide, current, search, topic, unlearned])
  useEffect(() => {
    if (!data) return
    if (data.track !== appTrack) setTrack(data.track) // opened by link: games must use the pack's track
    if (!filtered) save(storeKey, data.lesson)
  }, [data, appTrack, setTrack, filtered, storeKey])

  const goLesson = (n: number) => {
    stopAll()
    if (filtered) setFilterLesson(n)
    else {
      setLesson(n)
      save(storeKey, n)
    }
    window.scrollTo({ top: 0 })
  }
  const chooseLang = (l: TrLang) => {
    setLang(l)
    void api
      .request('PUT', '/auth/translation-prefs/', {
        body: { track, preferred_translation_lang: l, preferred_direction: pref?.preferred_direction ?? 'forward', remember_choice: pref?.remember_choice ?? false },
      })
      .catch(() => null)
  }
  const star = async (w: StudyWord) => {
    const put = (p: Partial<StudyWord>) => setData((d) => (d ? { ...d, words: d.words.map((x) => (x.id === w.id ? { ...x, ...p } : x)) } : d))
    try {
      if (w.want && w.userword_id) {
        await api.del(`/words/mine/${w.userword_id}/`, { list: 'want' })
        put({ want: false })
      } else {
        const r = await api.post<{ id: number }>('/words/lists/want/add/', { track, term: w.term, word_id: w.id, translation_uz: w.translation_uz, definition: w.definition, article: w.article })
        put({ want: true, userword_id: r.id })
        toast.ok(t('lists.saved_want'))
      }
    } catch {
      toast.err(t('err.generic'))
    }
  }
  const reveal = (wid: number) =>
    setRevealed((s) => {
      const n = new Set(s)
      if (n.has(wid)) n.delete(wid)
      else n.add(wid)
      return n
    })

  /* ---- listen to all ---- */
  const [playing, setPlaying] = useState<number | null>(null)
  const [playTr, setPlayTr] = useState(false)
  const run = useRef(0)
  const speed = useTts((s) => s.speed)
  const setTts = useTts((s) => s.set)
  const stopAll = useCallback(() => {
    run.current++
    setPlaying(null)
    stopSpeech()
  }, [])
  useEffect(
    () => () => {
      run.current++
      stopSpeech()
    },
    [],
  )
  const listen = async () => {
    if (playing !== null) return stopAll()
    const mine = ++run.current
    for (const w of data?.words ?? []) {
      if (mine !== run.current) return
      setPlaying(w.id)
      setPlayTr(false)
      document.getElementById(`sw-${w.id}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
      const started = Date.now()
      await speakToEnd(w.term, track)
      const pause = 1200 / useTts.getState().speed
      await wait(Math.max(pause, 1400 - (Date.now() - started)))
      if (mine !== run.current) return
      setPlayTr(true) // the translation is shown after the pause
      await wait(1.4 * pause)
    }
    if (mine === run.current) setPlaying(null)
  }

  const range = (n: number) => `${(n - 1) * (data?.lesson_size ?? 20) + 1}–${Math.min(n * (data?.lesson_size ?? 20), data?.total ?? 0)}`
  const flashUrl = data ? `/play/flashcards?source=lesson&${isExam ? 'pack' : 'level'}=${id}&ids=${data.words.map((w) => w.id).join(',')}&tl=${data.lang}` : ''

  const pager = data && data.lessons > 1 && (
    <div className="flex items-center gap-2">
      <button className="btn-ghost min-w-[48px] px-3" disabled={data.lesson <= 1} onClick={() => goLesson(data.lesson - 1)} aria-label={t('study2.prev')}>
        <ChevronLeft />
      </button>
      <select className="input flex-1 text-center font-bold" value={data.lesson} onChange={(e) => goLesson(Number(e.target.value))} aria-label={t('study2.lesson')}>
        {Array.from({ length: data.lessons }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>
            {t('study2.lesson_n', { n })}: {range(n)}
          </option>
        ))}
      </select>
      <button className="btn-ghost min-w-[48px] px-3" disabled={data.lesson >= data.lessons} onClick={() => goLesson(data.lesson + 1)} aria-label={t('common.next')}>
        <ChevronRight />
      </button>
    </div>
  )

  return (
    <div className="page max-w-5xl space-y-4">
      <div className="flex items-center gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => nav(back)} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <h1 className="h1">📖 {t('study2.title')}{isExam ? '' : ` · ${id}`}</h1>
      </div>
      <p className="rounded-2xl bg-line/60 p-3 text-sm text-muted" data-testid="study-note">ℹ️ {t('study2.note')}</p>

      <div className="card space-y-3 p-4">
        <Segmented value={lang ?? 'uz'} onChange={chooseLang} options={allowedLangs(track).map((l) => ({ value: l, label: `${LANG_META[l].flag} ${LANG_META[l].short}` }))} />
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="relative block">
            <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
            <input className="input pl-10" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('common.search')} />
          </label>
          <select className="input" value={topic} onChange={(e) => setTopic(e.target.value)} aria-label={t('exam.topics')}>
            <option value="">{t('study2.all_topics')}</option>
            {data?.topics.map((x) => (
              <option key={x.slug} value={x.slug}>
                {x.emoji} {x.name[ui]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid sm:grid-cols-3 sm:gap-6">
          <Toggle checked={hide === 'translation'} onChange={(v) => setHide(v ? 'translation' : 'none')} label={t('study2.hide_tr')} />
          <Toggle checked={hide === 'word'} onChange={(v) => setHide(v ? 'word' : 'none')} label={t('study2.hide_word')} />
          <Toggle checked={unlearned} onChange={setUnlearned} label={t('study2.only_unlearned')} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-soft flex-1" onClick={() => void listen()} disabled={!data?.words.length}>
            {playing !== null ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />} {t(playing !== null ? 'study2.stop' : 'study2.listen_all')}
          </button>
          <Segmented className="w-40" value={String(speed)} onChange={(v) => setTts({ speed: Number(v) })} options={['0.8', '1', '1.2'].map((v) => ({ value: v, label: `${v}×` }))} />
        </div>
      </div>

      {pager}
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data || (loading && !data.words.length) ? (
        <ListSkeleton rows={6} height="h-24" />
      ) : !data.words.length ? (
        <EmptyState emoji="📭" title={t('wl.nothing')} />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {data.words.map((w) => {
            const shown = revealed.has(w.id)
            const hideTr = (hide === 'translation' && !shown) || (playing === w.id && !playTr)
            const hideWord = hide === 'word' && !shown && playing !== w.id
            const mask = <span className="rounded-lg bg-line px-6 text-transparent" aria-hidden>•••</span>
            return (
              <li key={w.id} id={`sw-${w.id}`} className={`card p-4 ${playing === w.id ? 'ring-4 ring-primary/40' : ''}`} data-testid="study-row" onClick={() => hide !== 'none' && reveal(w.id)}>
                <div className="flex items-start gap-3">
                  <SpeakButton text={w.term} track={track} />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      {hideWord ? (
                        mask
                      ) : (
                        <span className="break-words text-xl font-black">
                          {w.article && <span className={ARTICLE[w.article] ?? ''}>{w.article} </span>}
                          {w.word}
                        </span>
                      )}
                      <span className="chip bg-line px-2 py-0 text-[11px] text-muted">{w.pos}</span>
                      {w.learned && <span title={t('study2.learned')} data-testid="learned-badge">✅</span>}
                    </div>
                    <div className="text-lg font-bold text-primary">{hideTr ? mask : w.translation}</div>
                  </div>
                  <button
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-full hover:bg-line"
                    aria-pressed={w.want}
                    aria-label={t('study2.star')}
                    onClick={(e) => {
                      e.stopPropagation()
                      void star(w)
                    }}
                  >
                    <Star className={`h-5 w-5 ${w.want ? 'fill-accent text-accent' : 'text-muted'}`} />
                  </button>
                </div>
                {w.example && (
                  <div className="mt-2 flex items-start gap-2 border-t border-line pt-2">
                    <SpeakButton text={w.example} track={track} className="h-8 w-8" />
                    <div className="min-w-0">
                      <div className="font-read">{hideWord ? mask : w.example}</div>
                      <div className="font-read text-sm text-muted">{hideTr ? mask : w.example_tr}</div>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {data && data.words.length > 0 && (
        <>
          <Link className="btn-primary w-full" to={flashUrl} data-testid="lesson-flashcards">
            🎴 {t('study2.check')}
          </Link>
          {pager}
        </>
      )}
    </div>
  )
}
