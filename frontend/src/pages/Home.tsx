import { motion } from 'framer-motion'
import { Camera, ChevronRight, Flame, Layers, Library, RotateCcw, Star, Trophy } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ErrorState, ProgressBar, Skeleton } from '../components/ui'
import { GAMES } from '../games/catalog'
import { isAvailable } from '../games/direction'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { ProfileStats } from '../lib/types'
import { useApp } from '../store/app'

export default function Home() {
  const t = useT()
  const track = useApp((s) => s.track)
  const user = useApp((s) => s.user)!
  const { data, error, loading, reload } = useAsync(() => api.get<ProfileStats>('/gamification/profile/', { track }), [track])
  const pct = data ? Math.round((100 * (data.xp - data.level_floor)) / Math.max(1, data.level_ceil - data.level_floor)) : 0

  return (
    <div className="page space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="font-bold text-muted">{t('home.hello', { name: user.display_name || '' })}</p>
          <h1 className="h1">{t(track === 'en' ? 'home.title_en' : 'home.title_de')}</h1>
        </div>
      </section>

      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading || !data ? (
        <div className="grid gap-3 md:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : (
        <section className="grid gap-3 md:grid-cols-3">
          <div className="card flex items-center gap-4 p-4">
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-accent/30">
              <Flame className={`h-8 w-8 ${data.streak ? 'fill-orange-400 text-orange-500' : 'text-muted'}`} />
            </div>
            <div>
              <div className="text-2xl font-black">{t('home.streak_days', { n: data.streak })}</div>
              <div className="text-sm text-muted">{data.played_today ? t('home.played_today') : t('home.play_today')}</div>
            </div>
          </div>
          <div className="card p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1 font-black">
                <Star className="h-5 w-5 fill-accent text-accent" /> {t('profile.level_n', { n: data.level })}
              </span>
              <span className="text-sm font-bold text-muted">{data.xp} XP</span>
            </div>
            <ProgressBar value={pct} color="bg-accent" />
            <div className="mt-2 text-xs text-muted">{t('home.to_next', { n: data.level_ceil - data.xp })}</div>
          </div>
          <Link to="/play/review" className={`card flex items-center gap-4 p-4 transition hover:shadow-lift ${data.due ? 'ring-2 ring-error/40' : ''}`}>
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-error/15">
              <RotateCcw className="h-7 w-7 text-error" />
            </div>
            <div className="flex-1">
              <div className="text-2xl font-black">{data.due}</div>
              <div className="text-sm text-muted">{t('home.due')}</div>
            </div>
            <ChevronRight className="text-muted" />
          </Link>
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2">
        <Link to="/play/daily" className="card relative overflow-hidden bg-tint p-5 text-tint-ink transition hover:shadow-lift">
          <div className="text-4xl">📅</div>
          <div className="mt-2 text-xl font-black">{t('game.daily')}</div>
          <div className="opacity-80">{t('home.daily_desc')}</div>
          <Trophy className="absolute -right-3 -top-3 h-24 w-24 opacity-15" />
        </Link>
        <Link to="/scan" className="card relative overflow-hidden p-5 transition hover:shadow-lift">
          <div className="text-4xl">📸</div>
          <div className="mt-2 text-xl font-black">{t('home.scan_title')}</div>
          <div className="text-muted">{t('home.scan_desc')}</div>
          <Camera className="absolute -right-3 -top-3 h-24 w-24 text-primary opacity-10" />
        </Link>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { to: '/levels', icon: Layers, label: t('nav.levels') },
          { to: '/decks', icon: Library, label: t('nav.decks') },
          { to: '/sets', icon: Camera, label: t('sets.title') },
          { to: '/leaderboard', icon: Trophy, label: t('nav.leaderboard') },
        ].map((q) => (
          <Link key={q.to} to={q.to} className="card flex min-h-[64px] items-center gap-3 p-4 font-extrabold transition hover:shadow-lift">
            <q.icon className="h-6 w-6 text-primary" /> {q.label}
          </Link>
        ))}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="h2">{t('nav.games')}</h2>
          <Link to="/games" className="text-sm font-extrabold text-primary">
            {t('common.see_all')}
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {GAMES.filter((g) => isAvailable(g.id, track)).map((g, i) => (
            <motion.div key={g.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Link to={`/play/${g.id}`} className="card flex h-full flex-col gap-1 p-4 transition hover:shadow-lift">
                <span className={`grid h-12 w-12 place-items-center rounded-2xl text-2xl ${g.color}`}>{g.emoji}</span>
                <span className="mt-1 font-black">{t(`game.${g.id}`)}</span>
                <span className="text-xs text-muted">{t(`game.${g.id}_desc`)}</span>
              </Link>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  )
}
