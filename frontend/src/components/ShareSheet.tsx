import { Camera, Copy, Download, Send, Share2 } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { translate, useT } from '../i18n'
import {
  buildCard,
  CARD_SIZES,
  downloadBlob,
  isMobileUA,
  makeCardImage,
  referralLink,
  shareMethods,
  supportsStory,
  trackShare,
  uploadCard,
  webShare,
  type CardFormat,
  type CardInput,
  type CardTheme,
  type ShareMethod,
} from '../lib/share'
import { isTelegram, shareToTelegram, tg } from '../lib/telegram'
import { useApp } from '../store/app'
import { ShareCard } from './ShareCard'
import { Segmented, Sheet, Toggle, toast } from './ui'

const PREVIEW_WIDTH = 240

function canWebShareFiles(): boolean {
  try {
    const probe = new File([new Uint8Array([0])], 'x.png', { type: 'image/png' })
    return typeof navigator.canShare === 'function' && typeof navigator.share === 'function' && navigator.canShare({ files: [probe] })
  } catch {
    return false
  }
}

export function ShareSheet({ open, onClose, input }: { open: boolean; onClose: () => void; input: CardInput }) {
  const t = useT()
  const lang = useApp((s) => s.lang)
  const user = useApp((s) => s.user)
  const config = useApp((s) => s.config)
  const [theme, setTheme] = useState<CardTheme>('violet')
  const [format, setFormat] = useState<CardFormat>('story')
  const [hideName, setHideName] = useState(false)
  const [busy, setBusy] = useState<ShareMethod | null>(null)
  const [hint, setHint] = useState('')
  const exportRef = useRef<HTMLDivElement>(null)

  const cardT = useMemo(() => (k: string, v?: Record<string, string | number>) => translate(lang, k, v), [lang]) // card language = interface language
  const content = useMemo(() => buildCard(input, cardT), [input, cardT])
  const link = referralLink(user?.referral_code, config, window.location.origin)
  const footer = cardT('share.footer')
  const name = hideName ? null : user?.display_name || null
  const props = { content, format, theme, name, footer, link }
  const env = { telegram: isTelegram, story: supportsStory(tg), webShareFiles: canWebShareFiles(), mobile: isMobileUA(navigator.userAgent) }
  const methods = shareMethods(env)
  const filename = `yodflip-${input.template}.png`
  const text = cardT('share.text', { link })

  const image = () => makeCardImage(exportRef.current!, { format, theme, lang, content, name: name ?? '', footer, link })

  const run = async (m: ShareMethod) => {
    setBusy(m)
    setHint('')
    try {
      if (m === 'copy') {
        await navigator.clipboard?.writeText(link)
        toast.ok(t('share.copied'))
      } else if (m === 'telegram_link') {
        shareToTelegram(link, cardT('share.text_short'))
      } else {
        const blob = await image()
        if (m === 'story') {
          const url = await uploadCard(blob, input.template)
          tg!.shareToStory!(url, { text: cardT('share.story_text'), widget_link: { url: link, name: 'Yodflip' } })
        } else if (m === 'webshare') {
          if (!(await webShare(blob, filename, text))) {
            downloadBlob(blob, filename)
            setHint(t('share.ig_hint'))
          }
        } else if (m === 'download') {
          if (isTelegram && tg) {
            // Telegram's WebView ignores <a download>: give it a URL.
            const url = await uploadCard(blob, input.template)
            if (typeof tg.downloadFile === 'function') tg.downloadFile({ url, file_name: filename })
            else tg.openLink?.(url)
          } else downloadBlob(blob, filename)
          setHint(env.mobile ? t('share.ig_hint') : t('share.desktop_hint'))
        }
      }
      trackShare(input.template, m)
    } catch {
      toast.err(t('share.failed'))
    } finally {
      setBusy(null)
    }
  }

  const label: Record<ShareMethod, { icon: JSX.Element; text: string }> = {
    story: { icon: <Camera className="h-5 w-5" />, text: t('share.to_story') },
    telegram_link: { icon: <Send className="h-5 w-5" />, text: t('share.to_telegram') },
    webshare: { icon: <Share2 className="h-5 w-5" />, text: t('share.to_apps') },
    download: { icon: <Download className="h-5 w-5" />, text: t('share.download') },
    copy: { icon: <Copy className="h-5 w-5" />, text: t('share.copy_link') },
  }
  const { width, height } = CARD_SIZES[format]
  const scale = PREVIEW_WIDTH / width

  return (
    <Sheet open={open} onClose={onClose} title={`📸 ${t('share.title')}`}>
      <div className="space-y-3" data-testid="share-sheet">
        <div className="mx-auto overflow-hidden rounded-2xl shadow-lift" style={{ width: PREVIEW_WIDTH, height: height * scale }}>
          <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width, height }}>
            <ShareCard {...props} />
          </div>
        </div>
        <Segmented
          value={theme}
          onChange={(v: CardTheme) => setTheme(v)}
          options={[
            { value: 'violet', label: `🟣 ${t('share.theme_violet')}` },
            { value: 'yellow', label: `🟡 ${t('share.theme_yellow')}` },
            { value: 'dark', label: `⚫ ${t('share.theme_dark')}` },
          ]}
        />
        <Segmented
          value={format}
          onChange={(v: CardFormat) => setFormat(v)}
          options={[
            { value: 'story', label: t('share.story') },
            { value: 'square', label: t('share.square') },
          ]}
        />
        <Toggle checked={hideName} onChange={setHideName} label={t('share.hide_name')} />
        <div className="grid gap-2">
          {methods.map((m, i) => (
            <button key={m} className={i === 0 ? 'btn-primary' : 'btn-soft'} disabled={busy !== null} onClick={() => run(m)} data-testid={`share-${m}`}>
              {label[m].icon} {busy === m ? '…' : label[m].text}
            </button>
          ))}
        </div>
        {hint && (
          <p className="rounded-2xl bg-accent/25 p-3 text-sm font-bold" data-testid="share-hint">
            💡 {hint}
          </p>
        )}
      </div>
      {/* the real-size node that is exported (off screen, but laid out) */}
      <div aria-hidden style={{ position: 'fixed', left: -20000, top: 0, pointerEvents: 'none' }}>
        <ShareCard ref={exportRef} {...props} />
      </div>
    </Sheet>
  )
}

/** "📸 Ulashish" button + its sheet. */
export function ShareButton({ input, className = 'btn-soft' }: { input: CardInput; className?: string }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className={className} onClick={() => setOpen(true)} data-testid="share-btn">
        📸 {t('share.button')}
      </button>
      {open && <ShareSheet open={open} onClose={() => setOpen(false)} input={input} />}
    </>
  )
}
