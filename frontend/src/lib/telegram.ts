/* Thin wrapper around the Telegram WebApp JS SDK (https://core.telegram.org/bots/webapps). */

interface ThemeParams {
  bg_color?: string
  secondary_bg_color?: string
  text_color?: string
  hint_color?: string
  button_color?: string
  section_bg_color?: string
}

interface TgButton {
  setText: (t: string) => TgButton
  show: () => TgButton
  hide: () => TgButton
  enable: () => TgButton
  disable: () => TgButton
  onClick: (cb: () => void) => TgButton
  offClick: (cb: () => void) => TgButton
  setParams?: (p: Record<string, unknown>) => TgButton
}

export interface TelegramWebApp {
  initData: string
  initDataUnsafe: { user?: { id: number; first_name: string; username?: string; photo_url?: string } }
  colorScheme: 'light' | 'dark'
  themeParams: ThemeParams
  platform: string
  ready: () => void
  expand: () => void
  close: () => void
  onEvent: (e: string, cb: () => void) => void
  MainButton: TgButton
  BackButton: { show: () => void; hide: () => void; onClick: (cb: () => void) => void; offClick: (cb: () => void) => void }
  HapticFeedback?: {
    impactOccurred: (s: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
    notificationOccurred: (s: 'error' | 'success' | 'warning') => void
    selectionChanged: () => void
  }
  openTelegramLink?: (url: string) => void
  setHeaderColor?: (c: string) => void
  setBackgroundColor?: (c: string) => void
  disableVerticalSwipes?: () => void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
    onTelegramAuth?: (user: Record<string, unknown>) => void
  }
}

export const tg: TelegramWebApp | undefined = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined

/** True only when actually running inside Telegram (initData present). */
export const isTelegram = Boolean(tg?.initData)

export function initTelegram() {
  if (!isTelegram || !tg) return
  tg.ready()
  tg.expand()
  try {
    tg.disableVerticalSwipes?.()
  } catch {
    /* older clients */
  }
  applyTelegramTheme()
  tg.onEvent('themeChanged', applyTelegramTheme)
}

/** Read Telegram.WebApp.themeParams into our CSS variables. */
export function applyTelegramTheme() {
  if (!isTelegram || !tg) return
  const p = tg.themeParams || {}
  const root = document.documentElement
  root.dataset.theme = tg.colorScheme === 'dark' ? 'dark' : 'light'
  const set = (name: string, v?: string) => v && root.style.setProperty(name, v)
  set('--bg', p.secondary_bg_color || p.bg_color)
  set('--card', p.section_bg_color || p.bg_color)
  set('--text', p.text_color)
  set('--muted', p.hint_color)
  try {
    tg.setHeaderColor?.(p.secondary_bg_color || p.bg_color || '#F7F7FB')
  } catch {
    /* ignore */
  }
}

export function haptic(kind: 'success' | 'error' | 'light' | 'select') {
  const h = tg?.HapticFeedback
  if (!isTelegram || !h) {
    if (kind === 'error' && 'vibrate' in navigator) navigator.vibrate?.(60)
    return
  }
  if (kind === 'success') h.notificationOccurred('success')
  else if (kind === 'error') h.notificationOccurred('error')
  else if (kind === 'select') h.selectionChanged()
  else h.impactOccurred('light')
}

export function shareToTelegram(url: string, text: string) {
  const link = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`
  if (isTelegram && tg?.openTelegramLink) tg.openTelegramLink(link)
  else window.open(link, '_blank', 'noopener')
}
