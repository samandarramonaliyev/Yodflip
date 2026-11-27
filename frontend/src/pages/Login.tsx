import { motion } from 'framer-motion'
import { Send } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Segmented, Spinner } from '../components/ui'
import { LANG_NAMES, useT } from '../i18n'
import { api, ApiError } from '../lib/api'
import { duelCodeOf } from '../lib/duel'
import type { AuthResponse, UiLang } from '../lib/types'
import { refCode } from '../lib/storage'
import { useApp } from '../store/app'

function TelegramWidget({ bot, onAuth }: { bot: string; onAuth: (u: Record<string, unknown>) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    window.onTelegramAuth = onAuth
    const s = document.createElement('script')
    s.src = 'https://telegram.org/js/telegram-widget.js?22'
    s.async = true
    s.setAttribute('data-telegram-login', bot)
    s.setAttribute('data-size', 'large')
    s.setAttribute('data-radius', '14')
    s.setAttribute('data-onauth', 'onTelegramAuth(user)')
    s.setAttribute('data-request-access', 'write')
    ref.current.innerHTML = ''
    ref.current.appendChild(s)
  }, [bot, onAuth])
  return <div ref={ref} className="flex min-h-[48px] justify-center" />
}

export default function Login() {
  const t = useT()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') || '/'
  const duelCode = duelCodeOf(next)
  const { user, login, config, lang, setLang } = useApp()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (user) return <Navigate to={next} replace />

  const done = (r: AuthResponse) => {
    login(r)
    nav(next, { replace: true })
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r =
        mode === 'login'
          ? await api.publicPost<AuthResponse>('/auth/login/', { email, password })
          : await api.publicPost<AuthResponse>('/auth/register/', { email, password, display_name: name, ui_language: lang, duel_code: duelCode, ref_code: refCode() })
      done(r)
    } catch (err) {
      const data = err instanceof ApiError ? (err.data as Record<string, unknown>) : null
      if (data && Array.isArray(data.email) && String(data.email[0]).includes('email_taken')) setError(t('auth.email_taken'))
      else if (err instanceof ApiError && err.status === 401) setError(t('auth.invalid'))
      else if (data && Array.isArray(data.password)) setError(t('auth.weak_password'))
      else setError(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  const widgetAuth = async (u: Record<string, unknown>) => {
    try {
      done(await api.publicPost<AuthResponse>('/auth/telegram/widget/', { ...u, ...(duelCode ? { duel_code: duelCode } : {}), ...(refCode() ? { ref_code: refCode() } : {}) }))
    } catch {
      setError(t('auth.tg_failed'))
    }
  }

  const demoTelegram = async () => {
    setBusy(true)
    try {
      done(await api.publicPost<AuthResponse>('/auth/telegram/webapp/', { init_data: '', duel_code: duelCode, ref_code: refCode() }))
    } catch {
      setError(t('auth.tg_failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="card w-full max-w-md p-6 md:p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src="/favicon.svg" alt="" className="mb-2 h-16 w-16" />
          <h1 className="h1">Yodflip</h1>
          <p className="mt-1 text-muted">{t('auth.tagline')}</p>
        </div>

        <div className="mb-4 flex justify-center gap-1">
          {(Object.keys(LANG_NAMES) as UiLang[]).map((l) => (
            <button key={l} onClick={() => setLang(l)} className={`chip ${lang === l ? 'bg-primary text-white' : 'bg-line text-muted'}`}>
              {LANG_NAMES[l]}
            </button>
          ))}
        </div>

        <Segmented
          className="mb-4"
          value={mode}
          onChange={setMode}
          options={[
            { value: 'login', label: t('auth.login') },
            { value: 'register', label: t('auth.register') },
          ]}
        />

        <form onSubmit={submit} className="space-y-3">
          {mode === 'register' && (
            <input className="input" placeholder={t('auth.name')} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          )}
          <input className="input" type="email" required placeholder={t('auth.email')} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          <input
            className="input"
            type="password"
            required
            minLength={6}
            placeholder={t('auth.password')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
          {error && (
            <p className="rounded-xl bg-error/15 px-3 py-2 text-sm font-bold text-error" role="alert">
              {error}
            </p>
          )}
          <button className="btn-primary w-full" disabled={busy}>
            {busy && <Spinner className="h-5 w-5" />}
            {mode === 'login' ? t('auth.login') : t('auth.create_account')}
          </button>
        </form>

        <div className="my-5 flex items-center gap-3 text-sm text-muted">
          <span className="h-px flex-1 bg-line" /> {t('auth.or')} <span className="h-px flex-1 bg-line" />
        </div>

        {config?.bot_username ? (
          <TelegramWidget bot={config.bot_username} onAuth={widgetAuth} />
        ) : config?.telegram_mock ? (
          <button className="btn w-full bg-[#229ED9] text-white" onClick={demoTelegram} disabled={busy}>
            <Send className="h-5 w-5" /> {t('auth.tg_demo')}
          </button>
        ) : null}
        {config?.telegram_mock && <p className="mt-2 text-center text-xs text-muted">{t('auth.mock_note')}</p>}
      </motion.div>
    </div>
  )
}
