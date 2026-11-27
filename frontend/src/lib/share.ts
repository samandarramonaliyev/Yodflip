/** Shareable result cards: template data, exact-size PNG export on the client, share-method detection. */
import { api, request } from './api'
import type { TelegramWebApp } from './telegram'

export type Template = 'game' | 'level' | 'exam' | 'streak' | 'duel' | 'league' | 'weekly'
export type CardFormat = 'story' | 'square'
export type CardTheme = 'violet' | 'yellow' | 'dark'

export const CARD_SIZES: Record<CardFormat, { width: number; height: number }> = {
  story: { width: 1080, height: 1920 },
  square: { width: 1080, height: 1080 },
}

export interface ThemeColors {
  bg: string
  fg: string
  sub: string
  accent: string
  panel: string
  shapes: [string, string, string, string]
}

export const THEMES: Record<CardTheme, ThemeColors> = {
  violet: { bg: '#6C5CE7', fg: '#FFFFFF', sub: 'rgba(255,255,255,0.8)', accent: '#FDCB6E', panel: 'rgba(255,255,255,0.16)', shapes: ['#FDCB6E', '#55EFC4', '#FF7675', '#A29BFE'] },
  yellow: { bg: '#FDCB6E', fg: '#2D3436', sub: 'rgba(45,52,54,0.75)', accent: '#6C5CE7', panel: 'rgba(255,255,255,0.45)', shapes: ['#6C5CE7', '#55EFC4', '#FF7675', '#FFEAA7'] },
  dark: { bg: '#1E1B2E', fg: '#FFFFFF', sub: 'rgba(255,255,255,0.72)', accent: '#FDCB6E', panel: 'rgba(255,255,255,0.08)', shapes: ['#6C5CE7', '#FDCB6E', '#55EFC4', '#FF7675'] },
}

export type CardInput =
  | { template: 'game'; game: string; correct: number; total: number; accuracy: number; durationMs: number; xp: number }
  | { template: 'level'; level: string; track: 'en' | 'de'; words: number }
  | { template: 'exam'; pack: string; percent: number; found: number; total: number }
  | { template: 'streak'; days: number; best: number }
  | { template: 'duel'; score: number; total: number; opponent: string; timeMs: number }
  | { template: 'league'; tierEmoji: string; tierName: string; result: 'promoted' | 'trophy'; rank: number; xp: number }
  | { template: 'weekly'; xp: number; words: number; accuracy: number; streak: number; tier?: string }

export interface CardStat {
  label: string
  value: string
}

export interface CardContent {
  template: Template
  emoji: string
  kicker: string
  main: string
  stats: CardStat[]
}

type T = (key: string, vars?: Record<string, string | number>) => string

export function formatTime(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** What a card says, in the interface language (`t`). 2–3 stats, one big main number. */
export function buildCard(input: CardInput, t: T): CardContent {
  switch (input.template) {
    case 'game':
      return {
        template: 'game',
        emoji: input.accuracy === 100 ? '💯' : '🎯',
        kicker: input.game,
        main: `${input.correct}/${input.total}`,
        stats: [
          { label: t('share.accuracy'), value: `${input.accuracy}%` },
          { label: t('share.time'), value: formatTime(input.durationMs) },
          { label: 'XP', value: `+${input.xp}` },
        ],
      }
    case 'level':
      return {
        template: 'level',
        emoji: '🎓',
        kicker: t('share.k_level', { track: input.track.toUpperCase() }),
        main: t('share.level_done', { level: input.level }),
        stats: [
          { label: t('share.words'), value: String(input.words) },
          { label: t('share.track'), value: input.track.toUpperCase() },
        ],
      }
    case 'exam':
      return {
        template: 'exam',
        emoji: input.percent >= 100 ? '🎖️' : '📘',
        kicker: input.pack,
        main: `${input.percent}%`,
        stats: [
          { label: t('share.words'), value: `${input.found}/${input.total}` },
          { label: t('share.status'), value: input.percent >= 100 ? t('share.done') : t('share.halfway') },
        ],
      }
    case 'streak':
      return {
        template: 'streak',
        emoji: '🔥',
        kicker: t('share.k_streak'),
        main: t('share.streak_main', { n: input.days }),
        stats: [
          { label: t('share.best'), value: t('share.days_n', { n: Math.max(input.best, input.days) }) },
          { label: t('share.goal'), value: t('share.days_n', { n: nextMilestone(input.days) }) },
        ],
      }
    case 'duel':
      return {
        template: 'duel',
        emoji: '⚔️',
        kicker: t('share.k_duel', { name: input.opponent }),
        main: `${input.score}/${input.total}`,
        stats: [
          { label: t('share.result'), value: t('share.win') },
          { label: t('share.time'), value: formatTime(input.timeMs) },
        ],
      }
    case 'league':
      return {
        template: 'league',
        emoji: input.result === 'trophy' ? '🏆' : '🎉',
        kicker: input.result === 'trophy' ? t('share.k_trophy') : t('share.k_promoted'),
        main: `${input.tierEmoji} ${input.tierName}`,
        stats: [
          { label: t('share.rank'), value: `#${input.rank}` },
          { label: 'XP', value: String(input.xp) },
        ],
      }
    case 'weekly': {
      const stats: CardStat[] = [
        { label: t('share.words'), value: String(input.words) },
        { label: t('share.accuracy'), value: `${input.accuracy}%` },
        { label: t('share.streak'), value: `🔥 ${input.streak}` },
      ]
      return { template: 'weekly', emoji: '📊', kicker: input.tier ? `${t('share.k_weekly')} · ${input.tier}` : t('share.k_weekly'), main: `${input.xp} XP`, stats }
    }
  }
}

export const STREAK_MILESTONES = [7, 30, 100]

export function nextMilestone(days: number): number {
  return STREAK_MILESTONES.find((m) => m > days) ?? Math.ceil((days + 1) / 100) * 100
}

/** Offer "📸 Ulashish" for a streak only on the milestone days. */
export const isStreakMilestone = (days: number) => STREAK_MILESTONES.includes(days)

/** Big number font size (px) so long texts like "B1 yakunlandi" still fit. */
export function mainFontSize(main: string, format: CardFormat): number {
  const n = [...main].length
  const story = n <= 4 ? 260 : n <= 7 ? 200 : n <= 11 ? 150 : n <= 16 ? 112 : 92
  return format === 'story' ? story : Math.round(story * 0.78)
}

/* ------------------------------------------------------------------ referral links */
export interface RefConfig {
  bot_username?: string
  app_short_name?: string
}

/** The link in the card's QR code: opens the Mini App (or the site) with the user's referral code. */
export function referralLink(code: string | null | undefined, cfg: RefConfig | null | undefined, origin: string): string {
  const c = code ? encodeURIComponent(code) : ''
  if (cfg?.bot_username && cfg.app_short_name) return `https://t.me/${cfg.bot_username}/${cfg.app_short_name}${c ? `?startapp=ref_${c}` : ''}`
  if (cfg?.bot_username) return `https://t.me/${cfg.bot_username}${c ? `?start=ref_${c}` : ''}`
  return `${origin}/${c ? `?ref=${c}` : ''}`
}

/** Short text under the QR code ("t.me/yodflip_bot"). */
export const shortLink = (link: string) => link.replace(/^https?:\/\//, '').replace(/[?#].*$/, '').replace(/\/$/, '')

/* ------------------------------------------------------------------ feature detection */
/** Telegram stories need Bot API 7.8+. Old clients may lack the method or the version check: never throw. */
export function supportsStory(app: TelegramWebApp | undefined | null): boolean {
  try {
    if (!app || typeof app.shareToStory !== 'function') return false
    return typeof app.isVersionAtLeast === 'function' ? Boolean(app.isVersionAtLeast('7.8')) : false
  } catch {
    return false
  }
}

export function canShareFiles(nav: Partial<Navigator> | undefined, file: File): boolean {
  try {
    return Boolean(nav && typeof nav.share === 'function' && typeof nav.canShare === 'function' && nav.canShare({ files: [file] }))
  } catch {
    return false
  }
}

export type ShareMethod = 'story' | 'telegram_link' | 'webshare' | 'download' | 'copy'

export interface ShareEnv {
  telegram: boolean
  story: boolean
  webShareFiles: boolean
  mobile: boolean
}

/** Buttons to show, most useful first. */
export function shareMethods(env: ShareEnv): ShareMethod[] {
  if (env.telegram) return env.story ? ['story', 'telegram_link', 'download'] : ['telegram_link', 'download']
  if (env.webShareFiles) return ['webshare', 'download', 'copy']
  return env.mobile ? ['download', 'copy'] : ['download', 'copy']
}

export const isMobileUA = (ua: string) => /Android|iPhone|iPad|iPod|Mobile/i.test(ua)

/* ------------------------------------------------------------------ export */
/** Width and height from a PNG's IHDR chunk (null if it isn't a PNG). */
export function pngSize(bytes: Uint8Array): { width: number; height: number } | null {
  const sig = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]
  if (bytes.length < 24 || sig.some((b, i) => bytes[i] !== b)) return null
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  return { width: v.getUint32(16), height: v.getUint32(20) }
}

async function blobBytes(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === 'function') return new Uint8Array(await blob.arrayBuffer())
  // older WebViews (and jsdom): FileReader
  return new Promise((ok, fail) => {
    const r = new FileReader()
    r.onload = () => ok(new Uint8Array(r.result as ArrayBuffer))
    r.onerror = fail
    r.readAsArrayBuffer(blob)
  })
}

let fontCSS: Promise<string> | null = null

/** @font-face rules of the bundled (same-origin) Nunito with the files inlined as data URLs. Cross-origin
 * stylesheets are skipped: reading them would fail, and nothing on the card uses them. */
export function nunitoFontCSS(): Promise<string> {
  fontCSS ??= (async () => {
    const rules: string[] = []
    for (const sheet of Array.from(document.styleSheets)) {
      let list: CSSRuleList
      try {
        list = sheet.cssRules
      } catch {
        continue
      }
      for (const rule of Array.from(list)) {
        if (typeof CSSFontFaceRule === 'undefined' || !(rule instanceof CSSFontFaceRule) || !/nunito/i.test(rule.style.getPropertyValue('font-family'))) continue
        const weight = rule.style.getPropertyValue('font-weight')
        if (!/(700|800|900)/.test(weight)) continue
        let css = rule.cssText
        const urls = [...css.matchAll(/url\(["']?([^"')]+\.woff2)["']?\)/g)].map((m) => m[1])
        for (const u of urls) {
          try {
            const blob = await (await fetch(u)).blob()
            const data = await new Promise<string>((ok, fail) => {
              const r = new FileReader()
              r.onload = () => ok(String(r.result))
              r.onerror = fail
              r.readAsDataURL(blob)
            })
            css = css.split(u).join(data)
          } catch {
            /* the browser still has the font loaded; the export just won't embed this file */
          }
        }
        rules.push(css.replace(/,\s*url\(["']?[^)"']*\.woff["']?\)[^,;]*/g, '')) // the .woff fallback isn't needed
      }
    }
    return rules.join('\n')
  })().catch(() => '')
  return fontCSS
}

/** Fonts (all glyphs on the card) and images are ready before the canvas is drawn. */
export async function waitForAssets(node: HTMLElement): Promise<void> {
  const fonts = (document as Document & { fonts?: FontFaceSet }).fonts
  if (fonts) {
    const text = node.textContent || 'Yodflip'
    await Promise.all(['700', '800', '900'].map((w) => fonts.load(`${w} 64px Nunito`, text).catch(() => [])))
    await fonts.ready
  }
  await Promise.all(
    Array.from(node.querySelectorAll('img')).map((img) => (img.complete ? Promise.resolve() : img.decode().catch(() => undefined))),
  )
}

export interface ImageLib {
  toBlob: (node: HTMLElement, options: Record<string, unknown>) => Promise<Blob | null>
}

/** PNG of the card at exactly 1080×1920 (story) or 1080×1080 (square). Throws if the size is off. */
export async function exportCard(node: HTMLElement, format: CardFormat, lib?: ImageLib): Promise<Blob> {
  const { width, height } = CARD_SIZES[format]
  const engine = lib ?? ((await import('html-to-image')) as unknown as ImageLib)
  await waitForAssets(node)
  const blob = await engine.toBlob(node, {
    width,
    height,
    canvasWidth: width,
    canvasHeight: height,
    pixelRatio: 1,
    cacheBust: false,
    fontEmbedCSS: await nunitoFontCSS(),
    style: { transform: 'none', left: '0', top: '0', margin: '0' },
  })
  if (!blob) throw new Error('export_failed')
  const size = pngSize(await blobBytes(blob))
  if (!size || size.width !== width || size.height !== height) throw new Error('export_wrong_size')
  return blob
}

export interface ServerCard {
  format: CardFormat
  theme: CardTheme
  lang: string
  content: CardContent
  name: string
  footer: string
  link: string
}

/** Fallback: the server draws the card with Pillow (used only when the client export failed). */
export async function renderOnServer(card: ServerCard): Promise<Blob> {
  const res = await request<Response>('POST', '/share/render/', { body: card, raw: true })
  return res.blob()
}

export async function makeCardImage(node: HTMLElement, card: ServerCard, lib?: ImageLib): Promise<Blob> {
  try {
    return await exportCard(node, card.format, lib)
  } catch {
    return renderOnServer(card)
  }
}

/** Public HTTPS URL of the image (Telegram stories and downloads need one). */
export async function uploadCard(blob: Blob, template: Template): Promise<string> {
  const form = new FormData()
  form.append('image', blob, `yodflip-${template}.png`)
  return (await api.form<{ url: string }>('/share/upload/', form)).url
}

export function trackShare(template: Template, platform: ShareMethod | string): void {
  void api.post('/share/events/', { template, platform }).catch(() => undefined)
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** Web Share API with the PNG. false = not supported (caller falls back to download). */
export async function webShare(blob: Blob, filename: string, text: string, nav: Partial<Navigator> = navigator): Promise<boolean> {
  const file = new File([blob], filename, { type: 'image/png' })
  if (!canShareFiles(nav, file)) return false
  try {
    await nav.share!({ files: [file], text })
  } catch (e) {
    if ((e as DOMException)?.name !== 'AbortError') return false // a cancelled share sheet is fine
  }
  return true
}
