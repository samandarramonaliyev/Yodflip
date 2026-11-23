import { ArrowLeft, Play, Timer } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { LevelBar } from '../components/LevelProgress'
import { SpeakButton, WordActions } from '../components/WordActions'
import { ErrorState, ListSkeleton, ProgressBar, Sheet, toast } from '../components/ui'
import { GAMES } from '../games/catalog'
import { isAvailable } from '../games/direction'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { examPlayUrl, type ExamGoal, type ExamPackDetail, type PackWord } from '../lib/exams'
import { useAsync, useTelegramBack } from '../lib/hooks'
import { useApp } from '../store/app'

const GOALS = [10, 15, 20, 30]

export default function ExamPage() {
  const { slug = '' } = useParams()
  const t = useT()
  const nav = useNavigate()
  useTelegramBack('/exams')
  const lang = useApp((s) => s.lang)
  const track = useApp((s) => s.track)
  const setTrack = useApp((s) => s.setTrack)
  const pack = useAsync(() => api.get<ExamPackDetail>(`/exams/${slug}/`), [slug])
  const [sheet, setSheet] = useState<{ topic: string | null; title: string; done: boolean } | null>(null)
  const [wordsTopic, setWordsTopic] = useState<string | null>(null)
  const words = useAsync(() => (wordsTopic ? api.get<PackWord[]>(`/exams/${slug}/words/`, { topic: wordsTopic }) : Promise.resolve([])), [slug, wordsTopic])
  const p = pack.data

  if (pack.error) return <div className="page"><ErrorState error={pack.error} onRetry={pack.reload} /></div>
  if (!p) return <div className="page"><ListSkeleton rows={6} /></div>

  const go = (url: string) => {
    if (track !== p.track) setTrack(p.track) // games run in the pack's track
    nav(url)
  }
  const open = (topic: string | null) => {
    const row = topic ? p.topics.find((x) => x.slug === topic) : null
    setSheet({ topic, title: row ? `${row.emoji} ${row.name[lang]}` : p.name[lang], done: row ? row.found >= row.total : p.completed })
  }
  const setGoal = async (n: number) => {
    try {
      const r = await api.post<{ goal: ExamGoal | null }>(`/exams/${slug}/goal/`, { per_day: n })
      pack.setData({ ...p, goal: r.goal })
      toast.ok(t('common.saved'))
    } catch {
      toast.err(t('err.generic'))
    }
  }
  const games = GAMES.filter((g) => g.needsSource && isAvailable(g.id, p.track))

  return (
    <div className="page max-w-3xl space-y-5">
      <div className="flex items-center gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => nav('/exams')} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <h1 className="h1">
          {p.emoji} {p.name[lang]}
        </h1>
      </div>
      <p className="rounded-2xl bg-accent/20 p-3 text-xs font-bold" data-testid="exam-disclaimer">ℹ️ {t('exam.disclaimer')}</p>

      <div className="card space-y-3 p-4">
        <LevelBar progress={p} />
        <button className="btn-primary w-full" onClick={() => open(p.next_topic)}>
          <Play className="h-5 w-5" /> {p.completed ? t('exam.review') : p.found ? t('exam.continue') : t('common.start')}
        </button>
        <div className="grid gap-2 sm:grid-cols-2">
          <Link to={`/exams/${slug}/simulation`} className="btn-soft">
            <Timer className="h-5 w-5" /> {t('exam.simulation')}
            {p.last_simulation && ` · ${p.last_simulation.score}/${p.last_simulation.total}`}
          </Link>
          <button className="btn-soft" onClick={() => go(`/duel?source=exam&ref=${slug}`)}>
            ⚔️ {t('exam.duel')}
          </button>
        </div>
      </div>

      <div className="card space-y-2 p-4">
        <div className="font-bold">🎯 {t('exam.goal_title')}</div>
        {p.goal && <p className="text-sm text-muted">{t('exam.goal_done', { done: p.goal.done, n: p.goal.per_day })}</p>}
        <div className="grid grid-cols-5 gap-1">
          {GOALS.map((n) => (
            <button key={n} aria-pressed={p.goal?.per_day === n} onClick={() => void setGoal(n)} className={`min-h-[44px] rounded-xl text-sm font-black ${p.goal?.per_day === n ? 'bg-tint text-tint-ink' : 'bg-line'}`}>
              {n}
            </button>
          ))}
          <button aria-pressed={!p.goal} onClick={() => void setGoal(0)} className={`min-h-[44px] rounded-xl text-sm font-black ${p.goal ? 'bg-line' : 'bg-tint text-tint-ink'}`}>
            {t('exam.goal_off')}
          </button>
        </div>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="h2">{t('exam.topics')}</h2>
          <button className="text-sm font-extrabold text-primary" onClick={() => open(null)}>
            {t('exam.all_words')}
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {p.topics.map((x) => (
            <div key={x.slug} className={`card space-y-2 p-4 ${p.next_topic === x.slug ? 'ring-2 ring-primary/40' : ''}`} data-testid="exam-topic">
              <button className="flex w-full items-center gap-3 text-left" onClick={() => open(x.slug)}>
                <span className="text-3xl">{x.emoji}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-black">{x.name[lang]}</span>
                  <span className="text-xs text-muted">
                    {x.found} / {x.total} · {x.percent}%
                  </span>
                </span>
                <Play className="h-5 w-5 text-primary" />
              </button>
              <ProgressBar value={x.percent} className="h-1.5" color={x.percent >= 100 ? 'bg-success' : 'bg-primary'} />
              <button className="text-xs font-extrabold text-primary" onClick={() => setWordsTopic(wordsTopic === x.slug ? null : x.slug)}>
                {wordsTopic === x.slug ? t('wl.close') : t('exam.show_words')}
              </button>
              {wordsTopic === x.slug &&
                (words.loading ? (
                  <ListSkeleton rows={3} height="h-12" />
                ) : (
                  <ul className="divide-y divide-line">
                    {words.data?.map((w) => (
                      <li key={w.id} className="flex items-start gap-2 py-2">
                        <SpeakButton text={w.display} track={p.track} />
                        <div className="min-w-0 flex-1 text-sm">
                          <div className="font-black">
                            {w.display} <span className="font-bold text-primary">— {w.translation}</span>
                          </div>
                          <div className="font-read text-muted">{w.definition}</div>
                          {w.example && <div className="font-read text-xs italic text-muted">“{w.example}” — {w.example_tr}</div>}
                          {w.collocations && <div className="text-xs font-bold">🔗 {w.collocations}</div>}
                          {w.word_family && <div className="text-xs text-muted">👪 {w.word_family}</div>}
                        </div>
                        <WordActions word={{ term: w.display, translation: w.translation, definition: w.definition, article: w.article, word_id: w.id }} track={p.track} />
                      </li>
                    ))}
                  </ul>
                ))}
            </div>
          ))}
        </div>
      </section>

      <Sheet open={sheet !== null} onClose={() => setSheet(null)} title={sheet?.title}>
        {sheet?.done && <p className="mb-3 text-sm text-muted">{t('exam.topic_done')}</p>}
        <div className="grid gap-2">
          {sheet &&
            games.map((g) => (
              <button key={g.id} onClick={() => go(examPlayUrl(g.id, slug, sheet.topic, sheet.done))} className="flex min-h-[56px] items-center gap-3 rounded-2xl bg-line/60 px-4 text-left font-extrabold hover:bg-line">
                <span className="text-2xl">{g.emoji}</span> {t(`game.${g.id}`)}
              </button>
            ))}
        </div>
      </Sheet>
    </div>
  )
}
