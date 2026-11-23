import { Loader2, Volume2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Track } from '../games/types'
import { useT } from '../i18n'
import { hasVoice, speakIn } from '../lib/tts'

const LONG_PRESS = 500
const SECOND_TAP = 2000

/**
 * Speaks the foreign word (track voice) or, with `lang`, a translation in that language.
 * Tap = normal speed; long press or a second tap within 2 s = slow (🐢).
 */
export function SpeakButton({ text, track, lang, className = '' }: { text: string; track: Track; lang?: string; className?: string }) {
  const t = useT()
  const voiceLang = lang || track
  const [state, setState] = useState<'idle' | 'loading' | 'slow'>('idle')
  const lastTap = useRef(0)
  const timer = useRef<number | undefined>(undefined)
  const longPressed = useRef(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      window.clearTimeout(timer.current)
    }
  }, [])
  if (!hasVoice(voiceLang)) return null

  const run = async (slow: boolean) => {
    setState(slow ? 'slow' : 'loading')
    await speakIn(text, voiceLang, slow ? 'slow' : 'normal')
    if (!alive.current) return
    if (slow) setTimeout(() => alive.current && setState('idle'), 900)
    else setState('idle')
  }
  return (
    <button
      type="button"
      className={`grid h-10 w-10 shrink-0 select-none place-items-center rounded-full bg-primary-soft text-primary ${className}`}
      onPointerDown={(e) => {
        e.stopPropagation()
        longPressed.current = false
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => {
          longPressed.current = true
          void run(true)
        }, LONG_PRESS)
      }}
      onPointerUp={() => window.clearTimeout(timer.current)}
      onPointerLeave={() => window.clearTimeout(timer.current)}
      onPointerCancel={() => window.clearTimeout(timer.current)}
      onContextMenu={(e) => e.preventDefault()}
      onKeyDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation()
        e.preventDefault()
        if (longPressed.current) return
        const now = Date.now()
        const slow = now - lastTap.current < SECOND_TAP
        lastTap.current = slow ? 0 : now
        void run(slow)
      }}
      aria-label={t('common.listen')}
      title={t('tts.hint')}
    >
      {state === 'loading' ? <Loader2 className="h-5 w-5 animate-spin" /> : state === 'slow' ? <span className="text-lg leading-none">🐢</span> : <Volume2 className="h-5 w-5" />}
    </button>
  )
}
