import { motion } from 'framer-motion'
import { Camera, Image as ImageIcon, Keyboard, ScanLine, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Spinner, toast } from '../components/ui'
import { useT } from '../i18n'
import { api, ApiError, errorKey } from '../lib/api'
import { useAsync, useMainButton } from '../lib/hooks'
import { compressImage } from '../lib/image'
import type { SetPair } from '../lib/types'
import { useApp } from '../store/app'
import type { Track } from '../games/types'

interface ScanResult {
  language: Track
  pairs: SetPair[]
  engine: string
  scans_left: number
  track_mismatch: boolean
  new_achievements: string[]
}

export default function Scan() {
  const t = useT()
  const nav = useNavigate()
  const track = useApp((s) => s.track)
  const cam = useRef<HTMLInputElement>(null)
  const gal = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<Blob | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const quota = useAsync(() => api.get<{ left: number; limit: number; mock: boolean }>('/ocr/quota/'), [])

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview])

  const pick = async (f: File | undefined) => {
    if (!f) return
    setError('')
    if (f.size > 25 * 1024 * 1024) {
      setError(t('err.too_large'))
      return
    }
    const blob = await compressImage(f, 1600)
    if (blob.size > 10 * 1024 * 1024) {
      setError(t('err.too_large'))
      return
    }
    setFile(blob)
    setPreview(URL.createObjectURL(blob))
  }

  const upload = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const fd = new FormData()
      fd.append('image', file, 'page.jpg')
      fd.append('track', track)
      const r = await api.form<ScanResult>('/ocr/scan/', fd)
      if (!r.pairs.length) {
        setError(t('scan.no_pairs'))
        return
      }
      r.new_achievements?.forEach((a) => toast.ok(`🏅 ${t(`ach.${a}`)}`))
      nav('/sets/new', { state: { pairs: r.pairs, language: r.language, mismatch: r.track_mismatch } })
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) setError(t('scan.failed'))
      else setError(t(errorKey(e)))
    } finally {
      setBusy(false)
    }
  }

  useMainButton(file && !busy ? t('scan.extract') : null, upload, !busy)

  return (
    <div className="page max-w-2xl space-y-5">
      <div>
        <h1 className="h1">{t('scan.title')}</h1>
        <p className="text-muted">{t('scan.subtitle')}</p>
      </div>

      <input ref={cam} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
      <input ref={gal} type="file" accept="image/*" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />

      {!preview ? (
        <div className="card flex flex-col items-center gap-4 p-6 text-center">
          <motion.div animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 2.4 }} className="grid h-24 w-24 place-items-center rounded-[28px] bg-primary-soft">
            <ScanLine className="h-12 w-12 text-primary" />
          </motion.div>
          <p className="max-w-sm text-muted">{t('scan.tip')}</p>
          <div className="grid w-full gap-2 sm:grid-cols-2">
            <button className="btn-primary" onClick={() => cam.current?.click()}>
              <Camera className="h-5 w-5" /> {t('scan.camera')}
            </button>
            <button className="btn-ghost" onClick={() => gal.current?.click()}>
              <ImageIcon className="h-5 w-5" /> {t('scan.gallery')}
            </button>
          </div>
        </div>
      ) : (
        <div className="card space-y-3 p-3">
          <div className="relative overflow-hidden rounded-2xl bg-line">
            <img src={preview} alt="" className="max-h-[55vh] w-full object-contain" />
            {busy && (
              <div className="absolute inset-0 grid place-items-center bg-black/40 text-white">
                <div className="flex flex-col items-center gap-2 font-bold">
                  <Spinner className="h-8 w-8" /> {t('scan.reading')}
                </div>
              </div>
            )}
            {!busy && (
              <button className="absolute right-2 top-2 grid h-10 w-10 place-items-center rounded-full bg-black/50 text-white" onClick={() => { setFile(null); setPreview(null) }} aria-label={t('common.cancel')}>
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
          <button className="btn-primary w-full" disabled={busy} onClick={upload}>
            {busy ? <Spinner className="h-5 w-5" /> : <ScanLine className="h-5 w-5" />} {t('scan.extract')}
          </button>
        </div>
      )}

      {error && (
        <p className="rounded-2xl bg-error/15 p-3 font-bold text-error" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
        <span>{quota.data ? t('scan.quota', { left: quota.data.left, limit: quota.data.limit }) : ''}</span>
        {quota.data?.mock && <span className="chip bg-accent/25 text-ink">{t('scan.mock')}</span>}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <Link to="/sets/new" state={{ pairs: [], language: track }} className="btn-ghost">
          <Keyboard className="h-5 w-5" /> {t('scan.manual')}
        </Link>
        <Link to="/sets" className="btn-ghost">
          {t('sets.title')}
        </Link>
      </div>
    </div>
  )
}
