import { motion } from 'framer-motion'
import { Camera, Flame, Gamepad2, Home, Layers, Library, Trophy, User, Volume2, VolumeX } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useT } from '../i18n'
import { useApp } from '../store/app'
import type { Track } from '../games/types'

export function TrackSwitch({ compact = false }: { compact?: boolean }) {
  const track = useApp((s) => s.track)
  const setTrack = useApp((s) => s.setTrack)
  const t = useT()
  const opts: { v: Track; flag: string; label: string }[] = [
    { v: 'en', flag: '🇬🇧', label: 'EN' },
    { v: 'de', flag: '🇩🇪', label: 'DE' },
  ]
  return (
    <div className="flex rounded-full bg-line p-1" role="radiogroup" aria-label={t('track.label')}>
      {opts.map((o) => (
        <button
          key={o.v}
          role="radio"
          aria-checked={track === o.v}
          onClick={() => setTrack(o.v)}
          className={`relative min-h-[36px] rounded-full px-3 text-sm font-black transition ${track === o.v ? 'text-tint-ink' : 'text-muted'}`}
        >
          {track === o.v && <motion.span layoutId="track-pill" className="absolute inset-0 rounded-full bg-tint shadow-soft" transition={{ duration: 0.25 }} />}
          <span className="relative">
            {o.flag} {!compact && o.label}
          </span>
        </button>
      ))}
    </div>
  )
}

const NAV = [
  { to: '/', icon: Home, key: 'nav.home', end: true },
  { to: '/levels', icon: Layers, key: 'nav.levels' },
  { to: '/scan', icon: Camera, key: 'nav.scan', center: true },
  { to: '/decks', icon: Library, key: 'nav.decks' },
  { to: '/profile', icon: User, key: 'nav.profile' },
]

const DESKTOP_NAV = [
  { to: '/', icon: Home, key: 'nav.home', end: true },
  { to: '/levels', icon: Layers, key: 'nav.levels' },
  { to: '/games', icon: Gamepad2, key: 'nav.games' },
  { to: '/scan', icon: Camera, key: 'nav.scan' },
  { to: '/decks', icon: Library, key: 'nav.decks' },
  { to: '/leaderboard', icon: Trophy, key: 'nav.leaderboard' },
]

export function Header() {
  const t = useT()
  const user = useApp((s) => s.user)
  const muted = useApp((s) => s.muted)
  const toggleMute = useApp((s) => s.toggleMute)
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-5xl items-center gap-3 px-4">
        <NavLink to="/" className="flex items-center gap-2 font-black" aria-label="WordFlip">
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <span className="hidden text-lg sm:inline">WordFlip</span>
        </NavLink>
        <nav className="ml-4 hidden items-center gap-1 lg:flex">
          {DESKTOP_NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) => `flex min-h-[40px] items-center gap-1.5 rounded-xl px-3 text-sm font-extrabold transition ${isActive ? 'bg-primary-soft text-primary' : 'text-muted hover:text-ink'}`}
            >
              <n.icon className="h-4 w-4" /> {t(n.key)}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <TrackSwitch compact />
          {user && (
            <NavLink to="/profile" className="chip bg-accent/25 text-ink" title={t('profile.streak')}>
              <Flame className={`h-4 w-4 ${user.streak ? 'fill-orange-400 text-orange-500' : 'text-muted'}`} />
              {user.streak}
            </NavLink>
          )}
          <button className="grid h-10 w-10 place-items-center rounded-full text-muted hover:bg-line" onClick={toggleMute} aria-label={muted ? t('common.unmute') : t('common.mute')}>
            {muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
          </button>
          <NavLink to="/profile" className="hidden lg:block" aria-label={t('nav.profile')}>
            <User className="h-6 w-6 text-muted" />
          </NavLink>
        </div>
      </div>
    </header>
  )
}

export function BottomNav() {
  const t = useT()
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card/95 backdrop-blur-md lg:hidden" aria-label="Main">
      <div className="mx-auto flex max-w-lg items-end justify-around px-2 pt-1.5">
        {NAV.map((n) =>
          n.center ? (
            <NavLink key={n.to} to={n.to} className="-mt-6 flex flex-col items-center gap-0.5 pb-1.5" aria-label={t(n.key)}>
              <span className="grid h-14 w-14 place-items-center rounded-full bg-primary text-white shadow-lift ring-4 ring-bg">
                <n.icon className="h-6 w-6" />
              </span>
              <span className="text-[11px] font-extrabold text-muted">{t(n.key)}</span>
            </NavLink>
          ) : (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) => `flex min-h-[52px] min-w-[56px] flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-extrabold ${isActive ? 'text-primary' : 'text-muted'}`}
            >
              <n.icon className="h-6 w-6" />
              {t(n.key)}
            </NavLink>
          ),
        )}
      </div>
    </nav>
  )
}

export default function Layout() {
  const loc = useLocation()
  const focus = loc.pathname.startsWith('/play/') || loc.pathname.includes('/study/')
  return (
    <div className="min-h-screen">
      <Header />
      <main>
        <Outlet />
      </main>
      {!focus && <BottomNav />}
    </div>
  )
}
