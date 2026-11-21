/**
 * Built-in camera screen state machine (pure, unit-tested).
 *
 *   idle ──REQUEST──▶ requesting ──READY──▶ live ──CAPTURED──▶ captured ──RETAKE──▶ live
 *                          │                  └──SWITCH──▶ requesting
 *                          └──FAIL(name)──▶ fallback (denied | notfound | busy | unsupported | unknown)
 *   fallback ──REQUEST──▶ requesting  (retry after the user enabled the permission)
 *
 * In "fallback" the screen offers <input type=file capture> and the gallery instead.
 */

export type CameraStatus = 'idle' | 'requesting' | 'live' | 'captured' | 'fallback'
export type CameraError = 'denied' | 'notfound' | 'busy' | 'unsupported' | 'unknown'
export type Facing = 'environment' | 'user'

export interface CameraState {
  status: CameraStatus
  error: CameraError | null
  facing: Facing
  torchSupported: boolean
  torchOn: boolean
  canSwitch: boolean
  photoUrl: string | null
}

export type CameraAction =
  | { type: 'REQUEST' }
  | { type: 'READY'; torchSupported: boolean; canSwitch: boolean }
  | { type: 'FAIL'; error: CameraError }
  | { type: 'CAPTURED'; url: string }
  | { type: 'RETAKE' }
  | { type: 'SWITCH' }
  | { type: 'TORCH'; on: boolean }

export const initialCamera: CameraState = {
  status: 'idle',
  error: null,
  facing: 'environment',
  torchSupported: false,
  torchOn: false,
  canSwitch: false,
  photoUrl: null,
}

/** Map a getUserMedia DOMException name to a user-facing error kind. */
export function cameraErrorKind(e: unknown): CameraError {
  const name = e && typeof e === 'object' && 'name' in e ? String((e as { name: unknown }).name) : ''
  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
    case 'SecurityError':
      return 'denied'
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return 'notfound'
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return 'busy'
    case 'TypeError':
      return 'unsupported'
    default:
      return 'unknown'
  }
}

/** getUserMedia needs a secure context (HTTPS or localhost) and a modern WebView. */
export function cameraSupported(nav: Navigator | undefined = typeof navigator === 'undefined' ? undefined : navigator): boolean {
  const secure = typeof window === 'undefined' || window.isSecureContext !== false
  return Boolean(secure && nav?.mediaDevices && typeof nav.mediaDevices.getUserMedia === 'function')
}

export function cameraConstraints(facing: Facing): MediaStreamConstraints {
  return {
    audio: false,
    video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } },
  }
}

export function cameraReducer(state: CameraState, action: CameraAction): CameraState {
  switch (action.type) {
    case 'REQUEST':
      if (state.status === 'requesting') return state
      return { ...state, status: 'requesting', error: null, torchOn: false, photoUrl: null }
    case 'READY':
      if (state.status !== 'requesting') return state
      return { ...state, status: 'live', torchSupported: action.torchSupported, canSwitch: action.canSwitch }
    case 'FAIL':
      return { ...state, status: 'fallback', error: action.error, torchOn: false }
    case 'CAPTURED':
      if (state.status !== 'live') return state
      return { ...state, status: 'captured', photoUrl: action.url }
    case 'RETAKE':
      if (state.status !== 'captured') return state
      return { ...state, status: 'live', photoUrl: null }
    case 'SWITCH':
      if (state.status !== 'live' || !state.canSwitch) return state
      return { ...state, status: 'requesting', facing: state.facing === 'environment' ? 'user' : 'environment', torchOn: false }
    case 'TORCH':
      if (state.status !== 'live' || !state.torchSupported) return state
      return { ...state, torchOn: action.on }
    default:
      return state
  }
}

/** Longest side ≤ maxSide, keeping the aspect ratio. */
export function fitSize(w: number, h: number, maxSide = 1600): { width: number; height: number } {
  const scale = Math.min(1, maxSide / Math.max(w, h, 1))
  return { width: Math.round(w * scale), height: Math.round(h * scale) }
}
