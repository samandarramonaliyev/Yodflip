import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Loader2, RefreshCw, X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { create } from 'zustand'
import { errorKey } from '../lib/api'
import { useT } from '../i18n'

export function Spinner({ className = '' }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden />
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />
}

export function ListSkeleton({ rows = 4, height = 'h-16' }: { rows?: number; height?: string }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={`${height} w-full`} />
      ))}
    </div>
  )
}

export function EmptyState({
  emoji = '🗂️',
  title,
  text,
  action,
}: {
  emoji?: string
  title: string
  text?: string
  action?: ReactNode
}) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="text-5xl" aria-hidden>
        {emoji}
      </div>
      <h3 className="h2">{title}</h3>
      {text && <p className="max-w-sm text-muted">{text}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useT()
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-8 text-center" role="alert">
      <AlertTriangle className="h-10 w-10 text-error" />
      <h3 className="h2">{t('err.title')}</h3>
      <p className="text-muted">{t(errorKey(error))}</p>
      {onRetry && (
        <button className="btn-soft mt-2" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" /> {t('common.retry')}
        </button>
      )}
    </div>
  )
}

export function ProgressBar({ value, className = '', color = 'bg-primary' }: { value: number; className?: string; color?: string }) {
  return (
    <div className={`h-2.5 w-full overflow-hidden rounded-full bg-line ${className}`} role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <motion.div className={`h-full rounded-full ${color}`} initial={{ width: 0 }} animate={{ width: `${Math.min(100, Math.max(0, value))}%` }} transition={{ duration: 0.4 }} />
    </div>
  )
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 md:items-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div
            role="dialog"
            aria-modal="true"
            className="safe-bottom max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-[24px] bg-card p-5 shadow-lift md:rounded-[24px]"
            initial={{ y: 60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 60, opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="h2">{title}</h3>
              <button className="grid h-10 w-10 place-items-center rounded-full bg-line" onClick={onClose} aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* ---------------- toasts ---------------- */
interface Toast {
  id: number
  text: string
  kind: 'ok' | 'err' | 'info'
}
const useToasts = create<{ list: Toast[]; push: (t: Omit<Toast, 'id'>) => void; drop: (id: number) => void }>((set) => ({
  list: [],
  push: (t) => {
    const id = Date.now() + Math.random()
    set((s) => ({ list: [...s.list, { ...t, id }] }))
    setTimeout(() => set((s) => ({ list: s.list.filter((x) => x.id !== id) })), 2600)
  },
  drop: (id) => set((s) => ({ list: s.list.filter((x) => x.id !== id) })),
}))

export const toast = {
  ok: (text: string) => useToasts.getState().push({ text, kind: 'ok' }),
  err: (text: string) => useToasts.getState().push({ text, kind: 'err' }),
  info: (text: string) => useToasts.getState().push({ text, kind: 'info' }),
}

export function Toaster() {
  const list = useToasts((s) => s.list)
  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[60] flex flex-col items-center gap-2 px-4" aria-live="polite">
      <AnimatePresence>
        {list.map((t) => (
          <motion.div
            key={t.id}
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -20, opacity: 0 }}
            className={`pointer-events-auto rounded-2xl px-4 py-3 font-bold shadow-lift ${
              t.kind === 'ok' ? 'bg-success text-white' : t.kind === 'err' ? 'bg-error text-white' : 'bg-card text-ink'
            }`}
          >
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className = '',
}: {
  value: T
  options: { value: T; label: ReactNode }[]
  onChange: (v: T) => void
  className?: string
}) {
  return (
    <div className={`flex rounded-2xl bg-line p-1 ${className}`} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`min-h-[40px] min-w-0 flex-1 break-words rounded-xl px-1.5 text-xs font-extrabold leading-tight transition sm:px-3 sm:text-sm ${value === o.value ? 'bg-card text-ink shadow-soft' : 'text-muted'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Two-line tab label (emoji + count / name) that fits three tabs on a 360px screen. */
export function TabLabel({ emoji, label, count }: { emoji: string; label: string; count?: number }) {
  return (
    <span className="flex flex-col items-center leading-tight">
      <span>
        {emoji}
        {count !== undefined ? ` ${count}` : ''}
      </span>
      <span className="text-[11px] sm:text-xs">{label}</span>
    </span>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="flex min-h-[44px] cursor-pointer items-center justify-between gap-3">
      <span className="font-bold">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-7 w-12 shrink-0 rounded-full transition ${checked ? 'bg-primary' : 'bg-line'}`}
      >
        <span className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? 'left-6' : 'left-1'}`} />
      </button>
    </label>
  )
}

export function Avatar({ name, url, size = 40 }: { name: string; url?: string; size?: number }) {
  const initials = (name || '?')
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return url ? (
    <img src={url} alt="" width={size} height={size} className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />
  ) : (
    <div className="grid shrink-0 place-items-center rounded-full bg-primary-soft font-black text-primary" style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {initials}
    </div>
  )
}
