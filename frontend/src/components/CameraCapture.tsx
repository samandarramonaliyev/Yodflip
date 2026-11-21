import { Check, RefreshCcw, RotateCcw, SwitchCamera, X, Zap, ZapOff } from 'lucide-react'
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useT } from '../i18n'
import { cameraConstraints, cameraErrorKind, cameraReducer, cameraSupported, fitSize, initialCamera } from '../lib/cameraMachine'
import { Spinner } from './ui'

export interface CameraCaptureProps {
  /** The final photo: a JPEG (longest side ≤ 1600px, quality 0.85) or a file picked in the fallback. */
  onCapture: (photo: Blob, fromFile: boolean) => void
  onClose: () => void
}

/**
 * Full-screen in-app camera (getUserMedia). Works inside the Telegram Mini App WebView, where
 * <input capture> often opens the gallery instead. Falls back to the file input on any error.
 * Every media track is stopped when the screen closes, so the camera is never left on.
 */
export function CameraCapture({ onCapture, onClose }: CameraCaptureProps) {
  const t = useT()
  const [state, dispatch] = useReducer(cameraReducer, initialCamera)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const blobRef = useRef<Blob | null>(null)
  const fileCam = useRef<HTMLInputElement>(null)
  const gallery = useRef<HTMLInputElement>(null)

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((tr) => tr.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  // Start (or restart after switching / retrying) the stream whenever we enter "requesting".
  useEffect(() => {
    if (state.status !== 'requesting') return
    let cancelled = false
    stop()
    if (!cameraSupported()) {
      dispatch({ type: 'FAIL', error: 'unsupported' })
      return
    }
    ;(async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia(cameraConstraints(state.facing))
        if (cancelled) {
          stream.getTracks().forEach((tr) => tr.stop())
          return
        }
        streamRef.current = stream
        const track = stream.getVideoTracks()[0] as MediaStreamTrack | undefined
        const caps = (track?.getCapabilities?.() ?? {}) as { torch?: boolean }
        const torchSupported = Boolean(caps.torch)
        let canSwitch = false
        try {
          const devices = await navigator.mediaDevices.enumerateDevices?.()
          canSwitch = (devices || []).filter((d) => d.kind === 'videoinput').length > 1
        } catch {
          canSwitch = false
        }
        const v = videoRef.current
        if (v) {
          v.srcObject = stream
          try {
            await v.play()
          } catch {
            /* autoplay is muted+playsInline; some test DOMs have no play() */
          }
        }
        dispatch({ type: 'READY', torchSupported, canSwitch })
      } catch (e) {
        if (!cancelled) dispatch({ type: 'FAIL', error: cameraErrorKind(e) })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [state.status, state.facing, stop])

  useEffect(() => {
    dispatch({ type: 'REQUEST' })
    const onHide = () => stop()
    window.addEventListener('pagehide', onHide)
    return () => {
      window.removeEventListener('pagehide', onHide)
      stop()
    }
  }, [stop])

  useEffect(() => () => void (state.photoUrl && URL.revokeObjectURL(state.photoUrl)), [state.photoUrl])

  const setTorch = async (on: boolean) => {
    const track = streamRef.current?.getVideoTracks()[0]
    try {
      await track?.applyConstraints({ advanced: [{ torch: on } as MediaTrackConstraintSet] })
      dispatch({ type: 'TORCH', on })
    } catch {
      /* torch not available after all */
    }
  }

  const shoot = () => {
    const v = videoRef.current
    if (!v || !v.videoWidth) return
    const { width, height } = fitSize(v.videoWidth, v.videoHeight, 1600)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    canvas.getContext('2d')?.drawImage(v, 0, 0, width, height)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        blobRef.current = blob
        dispatch({ type: 'CAPTURED', url: URL.createObjectURL(blob) })
      },
      'image/jpeg',
      0.85,
    )
  }

  const use = () => {
    if (!blobRef.current) return
    stop()
    onCapture(blobRef.current, false)
  }

  const close = () => {
    stop()
    onClose()
  }

  const pickFile = (f: File | undefined) => {
    if (!f) return
    stop()
    onCapture(f, true)
  }

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-black text-white" role="dialog" aria-modal="true" aria-label={t('cam.title')} data-testid="camera-screen">
      <input ref={fileCam} type="file" accept="image/*" capture="environment" className="hidden" data-testid="camera-file-input" onChange={(e) => pickFile(e.target.files?.[0])} />
      <input ref={gallery} type="file" accept="image/*" className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />

      <div className="flex items-center justify-between p-3" style={{ paddingTop: 'max(12px, env(safe-area-inset-top))' }}>
        <button className="grid h-11 w-11 place-items-center rounded-full bg-white/15" onClick={close} aria-label={t('cam.close')}>
          <X />
        </button>
        <div className="flex gap-2">
          {state.status === 'live' && state.torchSupported && (
            <button className="grid h-11 w-11 place-items-center rounded-full bg-white/15" onClick={() => setTorch(!state.torchOn)} aria-label={t('cam.torch')} aria-pressed={state.torchOn}>
              {state.torchOn ? <Zap className="text-accent" /> : <ZapOff />}
            </button>
          )}
          {state.status === 'live' && state.canSwitch && (
            <button className="grid h-11 w-11 place-items-center rounded-full bg-white/15" onClick={() => dispatch({ type: 'SWITCH' })} aria-label={t('cam.switch')}>
              <SwitchCamera />
            </button>
          )}
        </div>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        <video
          ref={videoRef}
          className={`h-full w-full object-cover ${state.status === 'live' ? '' : 'invisible'} ${state.facing === 'user' ? '-scale-x-100' : ''}`}
          playsInline
          muted
          autoPlay
        />
        {state.status === 'live' && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center p-6">
            <div className="relative aspect-[3/4] w-full max-w-md rounded-3xl border-[3px] border-white/85 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" data-testid="page-frame" />
            <p className="absolute bottom-4 left-0 right-0 text-center text-sm font-bold drop-shadow">{t('cam.align')}</p>
          </div>
        )}
        {state.status === 'captured' && state.photoUrl && <img src={state.photoUrl} alt="" className="absolute inset-0 h-full w-full object-contain" />}
        {(state.status === 'requesting' || state.status === 'idle') && (
          <div className="absolute inset-0 grid place-items-center">
            <div className="flex flex-col items-center gap-2 font-bold">
              <Spinner className="h-8 w-8" /> {t('cam.starting')}
            </div>
          </div>
        )}
        {state.status === 'fallback' && (
          <div className="absolute inset-0 overflow-y-auto p-5" data-testid="camera-fallback">
            <div className="mx-auto max-w-md space-y-4 rounded-3xl bg-white p-5 text-ink">
              <div className="text-4xl">📷</div>
              <p className="font-black" role="alert">
                {t(`cam.err_${state.error ?? 'unknown'}`)}
              </p>
              <p className="font-bold text-primary">{t('cam.hint')}</p>
              {(state.error === 'denied' || state.error === 'unsupported' || state.error === 'unknown') && (
                <div className="rounded-2xl bg-line/60 p-3 text-sm">
                  <div className="mb-1 font-bold">{t('cam.steps_title')}</div>
                  <ol className="list-decimal space-y-1 pl-5">
                    <li>{t('cam.step_tg_android')}</li>
                    <li>{t('cam.step_tg_ios')}</li>
                    <li>{t('cam.step_browser')}</li>
                  </ol>
                </div>
              )}
              <div className="grid gap-2">
                <button className="btn-primary" onClick={() => fileCam.current?.click()}>
                  📷 {t('cam.file_camera')}
                </button>
                <button className="btn-ghost" onClick={() => gallery.current?.click()}>
                  🖼 {t('scan.gallery')}
                </button>
                {state.error !== 'unsupported' && (
                  <button className="btn-ghost" onClick={() => dispatch({ type: 'REQUEST' })}>
                    <RefreshCcw className="h-5 w-5" /> {t('cam.retry')}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-center gap-4 p-5" style={{ paddingBottom: 'max(20px, env(safe-area-inset-bottom))' }}>
        {state.status === 'live' && (
          <button
            className="grid h-20 w-20 place-items-center rounded-full border-4 border-white bg-white/20 transition active:scale-95"
            onClick={shoot}
            aria-label={t('cam.shutter')}
            data-testid="shutter"
          >
            <span className="h-14 w-14 rounded-full bg-white" />
          </button>
        )}
        {state.status === 'captured' && (
          <>
            <button className="btn-ghost min-w-[140px] bg-white/15 text-white" onClick={() => dispatch({ type: 'RETAKE' })}>
              <RotateCcw className="h-5 w-5" /> {t('cam.retake')}
            </button>
            <button className="btn-primary min-w-[140px]" onClick={use}>
              <Check className="h-5 w-5" /> {t('cam.use')}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
