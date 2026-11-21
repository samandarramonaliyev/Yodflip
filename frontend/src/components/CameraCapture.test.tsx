import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { CameraCapture } from './CameraCapture'

function fakeStream() {
  const track = { stop: vi.fn(), kind: 'video', getCapabilities: () => ({ torch: true }), applyConstraints: vi.fn() }
  return { track, stream: { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream }
}

function mockMedia(getUserMedia: () => Promise<MediaStream>, cameras = 2) {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(getUserMedia),
      enumerateDevices: vi.fn(async () => Array.from({ length: cameras }, (_, i) => ({ kind: 'videoinput', deviceId: String(i) }))),
    },
  })
}

beforeAll(() => {
  // jsdom has no media playback
  Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: () => Promise.resolve() })
})

afterEach(() => {
  cleanup()
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined })
})

const flush = () => act(async () => void (await new Promise((r) => setTimeout(r, 0))))

describe('CameraCapture', () => {
  it('permission granted: live preview with frame, shutter, torch and switch; tracks stop on close', async () => {
    const { stream, track } = fakeStream()
    mockMedia(async () => stream)
    const { unmount } = render(<CameraCapture onCapture={vi.fn()} onClose={vi.fn()} />)
    await flush()
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    })
    expect(screen.getByTestId('page-frame')).toBeTruthy()
    expect(screen.getByTestId('shutter')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Chiroq' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Kamerani almashtirish' })).toBeTruthy()
    unmount()
    expect(track.stop).toHaveBeenCalled() // no camera left on
  })

  it('permission denied: falls back to <input capture> with the Uzbek hint', async () => {
    mockMedia(async () => {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' })
    })
    render(<CameraCapture onCapture={vi.fn()} onClose={vi.fn()} />)
    await flush()
    expect(screen.getByTestId('camera-fallback')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('Kameraga ruxsat berilmadi')
    expect(screen.getByText('Kameraga ruxsat bering yoki rasmni galereyadan tanlang')).toBeTruthy()
    const input = screen.getByTestId('camera-file-input') as HTMLInputElement
    expect(input.getAttribute('capture')).toBe('environment')
    expect(input.accept).toBe('image/*')
  })

  it('busy camera and missing camera get their own messages', async () => {
    mockMedia(async () => {
      throw Object.assign(new Error('busy'), { name: 'NotReadableError' })
    })
    render(<CameraCapture onCapture={vi.fn()} onClose={vi.fn()} />)
    await flush()
    expect(screen.getByRole('alert').textContent).toContain('band')
    cleanup()
    mockMedia(async () => {
      throw Object.assign(new Error('none'), { name: 'NotFoundError' })
    })
    render(<CameraCapture onCapture={vi.fn()} onClose={vi.fn()} />)
    await flush()
    expect(screen.getByRole('alert').textContent).toContain('Kamera topilmadi')
  })

  it('no getUserMedia at all: unsupported fallback without retry', async () => {
    render(<CameraCapture onCapture={vi.fn()} onClose={vi.fn()} />)
    await flush()
    expect(screen.getByTestId('camera-fallback')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Qayta urinish/ })).toBeNull()
  })

  it('a file picked in the fallback is passed on', async () => {
    const onCapture = vi.fn()
    render(<CameraCapture onCapture={onCapture} onClose={vi.fn()} />)
    await flush()
    const file = new File(['x'], 'p.jpg', { type: 'image/jpeg' })
    const input = screen.getByTestId('camera-file-input') as HTMLInputElement
    Object.defineProperty(input, 'files', { value: [file] })
    await act(async () => void input.dispatchEvent(new Event('change', { bubbles: true })))
    expect(onCapture).toHaveBeenCalledWith(file, true)
  })
})
