import { describe, expect, it } from 'vitest'
import { cameraConstraints, cameraErrorKind, cameraReducer, cameraSupported, fitSize, initialCamera, type CameraState } from './cameraMachine'

const live: CameraState = { ...initialCamera, status: 'live', torchSupported: true, canSwitch: true }

describe('camera state machine', () => {
  it('permission granted: idle → requesting → live → captured → live (retake)', () => {
    let s = cameraReducer(initialCamera, { type: 'REQUEST' })
    expect(s.status).toBe('requesting')
    s = cameraReducer(s, { type: 'READY', torchSupported: false, canSwitch: true })
    expect(s.status).toBe('live')
    expect(s.canSwitch).toBe(true)
    s = cameraReducer(s, { type: 'CAPTURED', url: 'blob:1' })
    expect(s).toMatchObject({ status: 'captured', photoUrl: 'blob:1' })
    s = cameraReducer(s, { type: 'RETAKE' })
    expect(s).toMatchObject({ status: 'live', photoUrl: null })
  })

  it('permission denied → fallback with the error kind, retry goes back to requesting', () => {
    let s = cameraReducer(initialCamera, { type: 'REQUEST' })
    s = cameraReducer(s, { type: 'FAIL', error: cameraErrorKind({ name: 'NotAllowedError' }) })
    expect(s).toMatchObject({ status: 'fallback', error: 'denied' })
    s = cameraReducer(s, { type: 'REQUEST' })
    expect(s).toMatchObject({ status: 'requesting', error: null })
  })

  it('maps getUserMedia errors to clear kinds', () => {
    expect(cameraErrorKind({ name: 'NotAllowedError' })).toBe('denied')
    expect(cameraErrorKind({ name: 'SecurityError' })).toBe('denied')
    expect(cameraErrorKind({ name: 'NotFoundError' })).toBe('notfound')
    expect(cameraErrorKind({ name: 'OverconstrainedError' })).toBe('notfound')
    expect(cameraErrorKind({ name: 'NotReadableError' })).toBe('busy')
    expect(cameraErrorKind({ name: 'TypeError' })).toBe('unsupported')
    expect(cameraErrorKind(new Error('x'))).toBe('unknown')
    expect(cameraErrorKind(null)).toBe('unknown')
  })

  it('switch flips the facing mode and restarts; torch only when supported', () => {
    const s = cameraReducer(live, { type: 'SWITCH' })
    expect(s).toMatchObject({ status: 'requesting', facing: 'user' })
    expect(cameraReducer({ ...live, canSwitch: false }, { type: 'SWITCH' }).status).toBe('live')
    expect(cameraReducer(live, { type: 'TORCH', on: true }).torchOn).toBe(true)
    expect(cameraReducer({ ...live, torchSupported: false }, { type: 'TORCH', on: true }).torchOn).toBe(false)
  })

  it('ignores events that do not fit the current state', () => {
    expect(cameraReducer(initialCamera, { type: 'CAPTURED', url: 'x' }).status).toBe('idle')
    expect(cameraReducer(initialCamera, { type: 'READY', torchSupported: true, canSwitch: true }).status).toBe('idle')
    expect(cameraReducer(live, { type: 'RETAKE' }).status).toBe('live')
  })

  it('asks for the back camera in Full HD', () => {
    expect(cameraConstraints('environment')).toEqual({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    })
  })

  it('compresses to a 1600px long side', () => {
    expect(fitSize(1920, 1080)).toEqual({ width: 1600, height: 900 })
    expect(fitSize(1080, 1920)).toEqual({ width: 900, height: 1600 })
    expect(fitSize(800, 600)).toEqual({ width: 800, height: 600 })
  })

  it('detects missing getUserMedia', () => {
    expect(cameraSupported({} as Navigator)).toBe(false)
    expect(cameraSupported({ mediaDevices: { getUserMedia: () => null } } as unknown as Navigator)).toBe(true)
  })
})
