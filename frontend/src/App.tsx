import { lazy, Suspense, useEffect, useRef } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner, Toaster } from './components/ui'
import { api, getTokens, setLogoutHandler } from './lib/api'
import { classStartPath } from './lib/classes'
import { duelCodeOf, startParamPath } from './lib/duel'
import { isTelegram, startParam, tg } from './lib/telegram'
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
const WordStudy = lazy(() => import('./pages/WordStudy'))
const Exams = lazy(() => import('./pages/Exams'))
const ExamPage = lazy(() => import('./pages/ExamPage'))
const ExamSim = lazy(() => import('./pages/ExamSim'))
const DuelHub = lazy(() => import('./pages/DuelHub'))
const DuelPage = lazy(() => import('./pages/DuelPage'))
const Classes = lazy(() => import('./pages/Classes'))
const League = lazy(() => import('./pages/League'))
const ClassPage = lazy(() => import('./pages/ClassPage'))
const ClassStudent = lazy(() => import('./pages/ClassStudent'))
const JoinClass = lazy(() => import('./pages/JoinClass'))
const TeachInvite = lazy(() => import('./pages/JoinClass').then((m) => ({ default: m.TeachInvite })))

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
          const r = await api.publicPost<AuthResponse>('/auth/telegram/webapp/', {
            init_data: tg.initData,
            duel_code: duelCodeOf(window.location.pathname), // signed start_param wins; this covers bot buttons
          })
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

/** Opened via t.me/<bot>/<app>?startapp=duel_<code>: go straight to the duel (once). */
function useStartParam() {
  const nav = useNavigate()
  const done = useRef(false)
  useEffect(() => {
    if (done.current) return
    done.current = true
    const path = isTelegram ? startParamPath(startParam()) ?? classStartPath(startParam()) : null
    if (path) nav(path, { replace: true })
  }, [nav])
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
  useStartParam()
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
              <Route path="/duel/:code" element={<DuelPage />} />
              <Route path="/duel" element={<RequireAuth><DuelHub /></RequireAuth>} />
              <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
              <Route path="/exams" element={<RequireAuth><Exams /></RequireAuth>} />
              <Route path="/exams/:slug/words" element={<RequireAuth><WordStudy /></RequireAuth>} />
              <Route path="/levels/:level/words" element={<RequireAuth><WordStudy /></RequireAuth>} />
              <Route path="/exams/:slug" element={<RequireAuth><ExamPage /></RequireAuth>} />
              <Route path="/exams/:slug/simulation" element={<RequireAuth><ExamSim /></RequireAuth>} />
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
              <Route path="/league" element={<RequireAuth><League /></RequireAuth>} />
              <Route path="/classes" element={<RequireAuth><Classes /></RequireAuth>} />
              <Route path="/classes/:id" element={<RequireAuth><ClassPage /></RequireAuth>} />
              <Route path="/classes/:id/students/:uid" element={<RequireAuth><ClassStudent /></RequireAuth>} />
              <Route path="/join/:code" element={<RequireAuth><JoinClass /></RequireAuth>} />
              <Route path="/teach/:code" element={<RequireAuth><TeachInvite /></RequireAuth>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </Suspense>
    </>
  )
}
