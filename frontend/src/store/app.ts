import { create } from 'zustand'
import type { Track } from '../games/types'
import { api, setTokens } from '../lib/api'
import { load, save } from '../lib/storage'
import type { AuthResponse, PublicConfig, UiLang, User } from '../lib/types'

export type ThemePref = 'system' | 'light' | 'dark'

interface AppState {
  user: User | null
  booting: boolean
  track: Track
  lang: UiLang
  theme: ThemePref
  muted: boolean
  config: PublicConfig | null
  setUser: (u: User | null) => void
  login: (r: AuthResponse) => void
  logout: () => void
  setTrack: (t: Track) => void
  setLang: (l: UiLang) => void
  setTheme: (t: ThemePref) => void
  toggleMute: () => void
  setConfig: (c: PublicConfig) => void
  setBooting: (b: boolean) => void
  bumpUser: (patch: Partial<User>) => void
}

export const useApp = create<AppState>((set, get) => ({
  user: null,
  booting: true,
  track: load<Track>('wf.track', 'en'),
  lang: load<UiLang>('wf.lang', 'uz'),
  theme: load<ThemePref>('wf.theme', 'system'),
  muted: load<boolean>('wf.muted', false),
  config: null,
  setUser: (user) => {
    set({ user })
    if (user) {
      set({ track: user.active_track, lang: user.ui_language })
      save('wf.track', user.active_track)
      save('wf.lang', user.ui_language)
    }
  },
  login: (r) => {
    setTokens({ access: r.access, refresh: r.refresh })
    get().setUser(r.user)
  },
  logout: () => {
    setTokens(null)
    set({ user: null })
  },
  setTrack: (track) => {
    set({ track })
    save('wf.track', track)
    if (get().user) {
      set({ user: { ...get().user!, active_track: track } })
      api.patch('/auth/me/', { active_track: track }).catch(() => undefined)
    }
  },
  setLang: (lang) => {
    set({ lang })
    save('wf.lang', lang)
    document.documentElement.lang = lang
    if (get().user) api.patch('/auth/me/', { ui_language: lang }).catch(() => undefined)
  },
  setTheme: (theme) => {
    set({ theme })
    save('wf.theme', theme)
  },
  toggleMute: () => {
    const muted = !get().muted
    set({ muted })
    save('wf.muted', muted)
  },
  setConfig: (config) => set({ config }),
  setBooting: (booting) => set({ booting }),
  bumpUser: (patch) => {
    const u = get().user
    if (u) set({ user: { ...u, ...patch } })
  },
}))
