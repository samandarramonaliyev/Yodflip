import { ArrowLeft, BookOpen, Brain } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { LevelBar, unlockText } from '../components/LevelProgress'
import { SpeakButton, WordActions } from '../components/WordActions'
import { EmptyState, ErrorState, ListSkeleton, ProgressBar, Segmented, Sheet } from '../components/ui'
import { GAMES } from '../games/catalog'
import { isAvailable, modeFor } from '../games/direction'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync, useTelegramBack } from '../lib/hooks'
import type { LevelProgress, LevelRow, Word } from '../lib/types'
import { useApp } from '../store/app'

export default function LevelPage() {
  const { level = 'A1' } = useParams()
  const t = useT()
  const nav = useNavigate()
  useTelegramBack('/levels')
  const track = useApp((s) => s.track)
  const lang = useApp((s) => s.lang)
  const [pack, setPack] = useState<string>('')
  const [playPack, setPlayPack] = useState<string | null>(null)
  const [mode, setMode] = useState<'definition' | 'memorize'>('definition')
  const overview = useAsync(() => api.get<{ levels: LevelRow[] }>('/words/levels/', { track }), [track])
  const words = useAsync(() => api.get<Word[]>(`/words/levels/${level}/`, { track, pack }), [track, level, pack])
  const detail = useAsync(() => api.get<LevelProgress & { found_words: Word[] }>(`/levels/${track}/${level}/`), [track, level])
  const [showFound, setShowFound] = useState(false)
  const lv = overview.data?.levels.find((l) => l.level === level)

  if (overview.error) return <div className="page"><ErrorState error={overview.error} onRetry={overview.reload} /></div>
  if (lv && !lv.unlocked) return <div className="page"><EmptyState emoji="🔒" title={t('levels.locked')} text={t('levels.locked_hint')} action={<Link to="/levels" className="btn-primary">{t('levels.title')}</Link>} /></div>

  const games = GAMES.filter((g) => g.needsSource && isAvailable(g.id, track) && (mode === 'definition' ? modeFor(g.id) === 'definition' : modeFor(g.id) !== 'definition'))
  const startUrl = (game: string, p: string | null) => `/play/${game}?source=level&level=${level}${p ? `&pack=${p}` : ''}`

  return (
    <div className="page space-y-5">
      <div className="flex items-center gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => nav('/levels')} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <h1 className="h1">
          {level} · {t(`cefr.${level}`)}
        </h1>
      </div>
      {lv && (
        <div className="card space-y-3 p-4" data-testid="level-progress">
          <LevelBar progress={lv} />
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-2xl bg-line/60 p-2">
              <div className="text-lg font-black">{lv.found}</div>
              <div className="text-xs font-bold text-muted">{t('level.found')}</div>
            </div>
            <div className="rounded-2xl bg-line/60 p-2">
              <div className="text-lg font-black">{lv.remaining}</div>
              <div className="text-xs font-bold text-muted">{t('level.left')}</div>
            </div>
            <div className="rounded-2xl bg-line/60 p-2">
              <div className="text-lg font-black">{lv.unlock_target}</div>
              <div className="text-xs font-bold text-muted">{t('level.target')}</div>
            </div>
          </div>
          <p className="text-sm font-bold text-primary">{unlockText(t, lv)}</p>
          <p className="text-xs text-muted">{t('level.rule')}</p>
          <button className="btn-ghost w-full" onClick={() => setShowFound((v) => !v)} disabled={!detail.data?.found_words.length}>
            ✅ {t('level.found_list', { n: detail.data?.found_words.length ?? lv.found })}
          </button>
          {showFound && detail.data && (
            <ul className="flex flex-wrap gap-1.5" data-testid="found-words">
              {detail.data.found_words.map((w) => (
                <li key={w.id} className="chip bg-success/15 text-ink" title={w.translation_uz}>
                  {w.display}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <section>
        <h2 className="h2 mb-3">{t('levels.packs')}</h2>
        {!lv ? (
          <ListSkeleton rows={2} height="h-20" />
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {lv.packs.map((p) => (
              <button key={p.slug} onClick={() => setPlayPack(p.slug)} className="card flex flex-col items-start gap-1 p-4 text-left transition hover:shadow-lift">
                <span className="text-3xl">{p.emoji}</span>
                <span className="font-black">{p.name[lang]}</span>
                <span className="text-xs text-muted">{t('level.count', { n: p.found, total: p.total })}</span>
                <ProgressBar value={p.percent} className="mt-1 h-1.5" />
              </button>
            ))}
          </div>
        )}
        <button className="btn-tint mt-3 w-full" onClick={() => setPlayPack('')}>
          {t('levels.play_all')}
        </button>
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="h2">{t('levels.words')}</h2>
          <select className="input max-w-[220px]" value={pack} onChange={(e) => setPack(e.target.value)} aria-label={t('levels.packs')}>
            <option value="">{t('levels.all_packs')}</option>
            {lv?.packs.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.emoji} {p.name[lang]}
              </option>
            ))}
          </select>
        </div>
        {words.error ? (
          <ErrorState error={words.error} onRetry={words.reload} />
        ) : words.loading ? (
          <ListSkeleton rows={6} />
        ) : (
          <ul className="grid gap-2 md:grid-cols-2">
            {words.data?.map((w) => (
              <li key={w.id} className="card flex items-start gap-3 p-3">
                <SpeakButton text={w.display} track={track} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-black">{w.display}</span>
                    <span className="text-xs text-muted">{w.part_of_speech}</span>
                  </div>
                  <div className="font-bold text-primary">{w.translation_uz}</div>
                  <div className="font-read text-sm text-muted">{w.definition}</div>
                  {w.example && <div className="font-read mt-1 text-xs italic text-muted">“{w.example}” — {w.example_uz}</div>}
                </div>
                <WordActions word={{ term: w.display, translation: w.translation_uz, definition: w.definition, article: w.article, word_id: w.id }} track={track} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <Sheet open={playPack !== null} onClose={() => setPlayPack(null)} title={t('levels.how_to_play')}>
        <Segmented
          className="mb-3"
          value={mode}
          onChange={setMode}
          options={[
            { value: 'definition', label: <span className="flex items-center justify-center gap-1"><BookOpen className="h-4 w-4" /> {t('mode.definition')}</span> },
            { value: 'memorize', label: <span className="flex items-center justify-center gap-1"><Brain className="h-4 w-4" /> {t('mode.memorize')}</span> },
          ]}
        />
        <p className="mb-3 text-sm text-muted">{mode === 'definition' ? t('mode.definition_desc') : t('mode.memorize_desc')}</p>
        <div className="grid gap-2">
          {games.map((g) => (
            <Link key={g.id} to={startUrl(g.id, playPack || null)} className="flex min-h-[56px] items-center gap-3 rounded-2xl bg-line/60 px-4 font-extrabold hover:bg-line">
              <span className="text-2xl">{g.emoji}</span> {t(`game.${g.id}`)}
            </Link>
          ))}
        </div>
      </Sheet>
    </div>
  )
}
