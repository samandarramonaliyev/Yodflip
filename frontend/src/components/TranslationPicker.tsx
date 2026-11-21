import { ArrowRightLeft, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Track } from '../games/types'
import { useT } from '../i18n'
import { useMainButton } from '../lib/hooks'
import { allowedLangs, LANG_META, type Direction, type TrLang } from '../lib/translation'
import { Sheet } from './ui'

export interface PickerChoice {
  lang: TrLang
  direction: Direction
  remember: boolean
}

export interface TranslationPickerProps {
  open: boolean
  track: Track
  initial: PickerChoice
  /** Languages that exist for this source (others are greyed out); all allowed ones when omitted. */
  available?: TrLang[]
  onStart: (choice: PickerChoice) => void
  onClose: () => void
}

/** "Qaysi tilga tarjima qilinsin?" — before every memorization game. */
export function TranslationPicker({ open, track, initial, available, onStart, onClose }: TranslationPickerProps) {
  const t = useT()
  const langs = allowedLangs(track)
  const has = (l: TrLang) => !available || available.includes(l)
  const firstAvailable = langs.find(has) ?? 'uz'
  const [lang, setLang] = useState<TrLang>(has(initial.lang) ? initial.lang : firstAvailable)
  const [direction, setDirection] = useState<Direction>(initial.direction)
  const [remember, setRemember] = useState(initial.remember)

  useEffect(() => {
    if (!open) return
    setLang(has(initial.lang) ? initial.lang : firstAvailable)
    setDirection(initial.direction)
    setRemember(initial.remember)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial.lang, initial.direction, initial.remember, available?.join(',')])

  const start = () => onStart({ lang, direction, remember })
  useMainButton(open ? t('common.start') : null, start, open)
  const word = t('tr.word')
  const tr = t('tr.translation')

  return (
    <Sheet open={open} onClose={onClose} title={t('tr.title')}>
      <div className="space-y-4" data-testid="translation-picker">
        <div className="grid gap-2">
          {langs.map((l) => {
            const ok = has(l)
            return (
              <button
                key={l}
                type="button"
                disabled={!ok}
                title={ok ? undefined : t('tr.unavailable')}
                aria-pressed={lang === l}
                onClick={() => setLang(l)}
                className={`flex min-h-[60px] items-center gap-3 rounded-2xl px-4 text-lg font-black transition ${
                  lang === l ? 'bg-primary text-white shadow-lift' : 'bg-line/60 hover:bg-line'
                } ${ok ? '' : 'cursor-not-allowed opacity-40'}`}
              >
                <span className="text-3xl">{LANG_META[l].flag}</span>
                <span className="flex-1 text-left">{LANG_META[l].name}</span>
                {!ok && <span className="text-xs font-bold">{t('tr.unavailable')}</span>}
              </button>
            )
          })}
        </div>

        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-line/50 p-1" role="radiogroup" aria-label={t('tr.direction')}>
          {(['forward', 'reverse'] as Direction[]).map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={direction === d}
              onClick={() => setDirection(d)}
              className={`flex min-h-[44px] items-center justify-center gap-1 rounded-xl text-sm font-extrabold ${direction === d ? 'bg-card shadow-soft' : 'text-muted'}`}
            >
              {d === 'forward' ? `${word} → ${tr}` : `${tr} → ${word}`}
            </button>
          ))}
        </div>

        <label className="flex cursor-pointer items-center gap-3 font-bold">
          <input type="checkbox" className="h-5 w-5 accent-[var(--color-primary,#6C5CE7)]" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          {t('tr.remember')}
        </label>

        <button className="btn-primary w-full" onClick={start}>
          <Play className="h-5 w-5" /> {t('common.start')}
        </button>
        <p className="flex items-center justify-center gap-1 text-xs text-muted">
          <ArrowRightLeft className="h-3.5 w-3.5" /> {t('tr.ui_note')}
        </p>
      </div>
    </Sheet>
  )
}
