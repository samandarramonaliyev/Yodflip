/**
 * Exam mode only: copy / print / screenshot deterrents (best effort, a web page can't fully block
 * screenshots). Everything is added while `active` is true and removed afterwards.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { tg } from './telegram'

export type ViolationKind = 'tab_switch' | 'focus_loss' | 'printscreen' | 'copy' | 'devtools'

/** One real event (e.g. switching the app) fires blur + visibilitychange: count it once. */
export const VIOLATION_GAP = 1000

/** Possible names of a capture protection in the Telegram WebApp API; used only if the client has it. */
const CAPTURE: [on: string, off: string][] = [
  ['enableScreenCaptureProtection', 'disableScreenCaptureProtection'],
  ['disableScreenCapture', 'enableScreenCapture'],
]

export function setTelegramProtection(on: boolean, app: unknown = tg): boolean {
  const a = app as Record<string, unknown> | undefined
  for (const [start, stop] of CAPTURE) {
    try {
      if (typeof a?.[start] !== 'function' || typeof a?.[stop] !== 'function') continue
      ;(a[on ? start : stop] as () => void).call(a)
      return true
    } catch {
      /* unsupported client version */
    }
  }
  return false
}

export function classifyKey(e: { key: string; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean; altKey?: boolean }): { block: boolean; violation?: ViolationKind } {
  const k = e.key.toLowerCase()
  const mod = Boolean(e.ctrlKey || e.metaKey)
  if (k === 'printscreen') return { block: true, violation: 'printscreen' }
  if (k === 'f12' || (mod && (e.shiftKey || e.altKey) && ['i', 'j', 'c', 'k'].includes(k))) return { block: true, violation: 'devtools' }
  if (mod && ['c', 'x'].includes(k)) return { block: true, violation: 'copy' }
  if (mod && k === 'u') return { block: true, violation: 'devtools' }
  if (mod && ['a', 's', 'p'].includes(k)) return { block: true }
  return { block: false }
}

export function useExamGuard(active: boolean, onViolation: (kind: ViolationKind) => void) {
  const [hidden, setHidden] = useState(false)
  const cb = useRef(onViolation)
  cb.current = onViolation
  const last = useRef(0)

  useEffect(() => {
    if (!active) return
    const violate = (kind: ViolationKind) => {
      const now = Date.now()
      if (now - last.current < VIOLATION_GAP) return
      last.current = now
      cb.current(kind)
    }
    const stop = (e: Event) => e.preventDefault()
    const onCopy = (e: Event) => {
      e.preventDefault()
      violate('copy')
    }
    const onKey = (e: KeyboardEvent) => {
      const r = classifyKey(e)
      if (!r.block) return
      e.preventDefault()
      e.stopPropagation()
      if (r.violation === 'printscreen') {
        setHidden(true)
        try {
          void navigator.clipboard?.writeText('')?.catch(() => undefined)
        } catch {
          /* clipboard unavailable */
        }
      }
      if (r.violation) violate(r.violation)
    }
    const onVisibility = () => {
      if (!document.hidden) return
      setHidden(true)
      violate('tab_switch')
    }
    const onBlur = () => {
      setHidden(true)
      violate('focus_loss')
    }
    const blocked = ['contextmenu', 'dragstart', 'selectstart', 'paste']
    document.body.classList.add('exam-mode')
    setTelegramProtection(true)
    blocked.forEach((e) => document.addEventListener(e, stop))
    document.addEventListener('copy', onCopy)
    document.addEventListener('cut', onCopy)
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('keyup', onKey, true) // Windows reports PrintScreen on keyup only
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('blur', onBlur)
    return () => {
      document.body.classList.remove('exam-mode')
      setTelegramProtection(false)
      blocked.forEach((e) => document.removeEventListener(e, stop))
      document.removeEventListener('copy', onCopy)
      document.removeEventListener('cut', onCopy)
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('keyup', onKey, true)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('blur', onBlur)
      setHidden(false)
    }
  }, [active])

  const show = useCallback(() => setHidden(false), [])
  return { hidden, show }
}

/** Diagonal watermark (name / ID + date) as a CSS background. */
export function watermark(text: string): string {
  const safe = text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="280" height="160"><text x="10" y="110" transform="rotate(-25 140 80)" font-family="sans-serif" font-size="14" fill="gray" fill-opacity=".22">${safe}</text></svg>`
  return `url("data:image/svg+xml,${encodeURIComponent(svg).replace(/[()']/g, (c) => `%${c.charCodeAt(0).toString(16)}`)}")`
}
