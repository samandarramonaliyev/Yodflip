import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner, Toaster } from './components/ui'
import { api, getTokens, setLogoutHandler } from './lib/api'
import { isTelegram, tg } from './lib/telegram'
import type { AuthResponse, PublicConfig, User } from './lib/types'
import { useApp } from './store/app'
import { useMediaQuery } from './lib/hooks'

const Home = lazy(() => import('./pages/Home'))
const Login = lazy(() => import('./pages/Login'))
const Levels = lazy(() => import('./pages/Levels'))
const LevelPage = lazy(() => import('./pages/LevelPage'))
const Scan = lazy(() => import('./pages/Scan'))
const Sets = lazy(() => import('./pages/Sets'))
const SetEditor = lazy(() => import('./pages/SetEditor'))
const Decks = lazy(() => import('./pages/Decks'))
const DeckPage = lazy(() => import('./pages/DeckPage'))
const DeckStudy = lazy(() => import('./pages/DeckStudy'))
const SharedDeck = lazy(() => import('./pages/SharedDeck'))
const GamesHub = lazy(() => import('./pages/GamesHub'))
const Play = lazy(() => import('./pages/Play'))
const Leaderboard = lazy(() => import('./pages/Leaderboard'))
const Profile = lazy(() => import('./pages/Profile'))
const Lists = lazy(() => import('./pages/Lists'))

function useThemeAndTrack() {
  const theme = useApp((s) => s.theme)
  const track = useApp((s) => s.track)
  const lang = useApp((s) => s.lang)
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  useEffect(() => {
    const root = document.documentElement
    root.dataset.track = track
    root.lang = lang
    if (isTelegram && tg) return // Telegram theme handled by applyTelegramTheme()
    root.dataset.theme = theme === 'system' ? (prefersDark ? 'dark' : 'light') : theme
  }, [theme, track, lang, prefersDark])
}

function useBoot() {
  const { setUser, login, setBooting, setConfig, logout } = useApp.getState()
  useEffect(() => {
    setLogoutHandler(() => logout())
    api.publicGet<PublicConfig>('/auth/telegram/config/').then(setConfig).catch(() => undefined)
    ;(async () => {
      try {
        if (isTelegram && tg) {
          // Mini App: always sign in with verified initData (fresh identity).
          const r = await api.publicPost<AuthResponse>('/auth/telegram/webapp/', { init_data: tg.initData })
          login(r)
        } else if (getTokens()) {
          setUser(await api.get<User>('/auth/me/'))
        }
      } catch {
        if (!isTelegram) logout()
      } finally {
        setBooting(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

function FullSpinner() {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <Spinner className="h-8 w-8 text-primary" />
    </div>
  )
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const user = useApp((s) => s.user)
  const booting = useApp((s) => s.booting)
  const loc = useLocation()
  if (booting) return <FullSpinner />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  return children
}

export default function App() {
  useThemeAndTrack()
  useBoot()
  const booting = useApp((s) => s.booting)
  return (
    <>
      <Toaster />
      <Suspense fallback={<FullSpinner />}>
        {booting ? (
          <FullSpinner />
        ) : (
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Layout />}>
              <Route path="/d/:code" element={<SharedDeck />} />
              <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
              <Route path="/levels" element={<RequireAuth><Levels /></RequireAuth>} />
              <Route path="/levels/:level" element={<RequireAuth><LevelPage /></RequireAuth>} />
              <Route path="/scan" element={<RequireAuth><Scan /></RequireAuth>} />
              <Route path="/sets" element={<RequireAuth><Sets /></RequireAuth>} />
              <Route path="/sets/:id" element={<RequireAuth><SetEditor /></RequireAuth>} />
              <Route path="/decks" element={<RequireAuth><Decks /></RequireAuth>} />
              <Route path="/decks/:id" element={<RequireAuth><DeckPage /></RequireAuth>} />
              <Route path="/decks/:id/study/:mode" element={<RequireAuth><DeckStudy /></RequireAuth>} />
              <Route path="/games" element={<RequireAuth><GamesHub /></RequireAuth>} />
              <Route path="/play/:game" element={<RequireAuth><Play /></RequireAuth>} />
              <Route path="/leaderboard" element={<RequireAuth><Leaderboard /></RequireAuth>} />
              <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
              <Route path="/lists/:which" element={<RequireAuth><Lists /></RequireAuth>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </Suspense>
    </>
  )
}
