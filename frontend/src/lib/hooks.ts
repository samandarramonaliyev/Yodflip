import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isTelegram, tg } from './telegram'

/** Load data with loading / error state and a reload function. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fnRef.current())
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, error, loading, reload, setData }
}

/** Show the Telegram BackButton while mounted (falls back to nothing on the web). */
export function useTelegramBack(to?: string | number) {
  const navigate = useNavigate()
  useEffect(() => {
    const app = tg
    if (!isTelegram || !app) return
    const handler = () => (typeof to === 'string' ? navigate(to) : navigate(-1))
    app.BackButton.show()
    app.BackButton.onClick(handler)
    return () => {
      app.BackButton.offClick(handler)
      app.BackButton.hide()
    }
  }, [navigate, to])
}

/** Use the Telegram MainButton for a primary action while mounted. */
export function useMainButton(text: string | null, onClick: () => void, enabled = true) {
  const cb = useRef(onClick)
  cb.current = onClick
  useEffect(() => {
    if (!isTelegram || !tg || !text) return
    const handler = () => cb.current()
    const mb = tg.MainButton
    mb.setText(text)
    if (enabled) mb.enable()
    else mb.disable()
    mb.show()
    mb.onClick(handler)
    return () => {
      mb.offClick(handler)
      mb.hide()
    }
  }, [text, enabled])
}

export function useInterval(fn: () => void, ms: number | null) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (ms == null) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

export function useMediaQuery(q: string) {
  const [match, setMatch] = useState(() => typeof window !== 'undefined' && window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const on = () => setMatch(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [q])
  return match
}
