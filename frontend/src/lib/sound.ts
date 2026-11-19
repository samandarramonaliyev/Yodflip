/* Tiny synthesized sound effects (no audio files). Respect the mute toggle in the store. */
import { useApp } from '../store/app'

let ctx: AudioContext | null = null

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AC) return null
  ctx ??= new AC()
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

function tone(freq: number, start: number, dur: number, type: OscillatorType = 'sine', gain = 0.08) {
  const ac = audio()
  if (!ac) return
  const osc = ac.createOscillator()
  const g = ac.createGain()
  osc.type = type
  osc.frequency.value = freq
  const t0 = ac.currentTime + start
  g.gain.setValueAtTime(0, t0)
  g.gain.linearRampToValueAtTime(gain, t0 + 0.01)
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
  osc.connect(g).connect(ac.destination)
  osc.start(t0)
  osc.stop(t0 + dur + 0.02)
}

export type Sfx = 'flip' | 'success' | 'miss' | 'win' | 'tick'

export function play(sfx: Sfx) {
  if (useApp.getState().muted) return
  try {
    switch (sfx) {
      case 'flip':
        tone(520, 0, 0.06, 'triangle', 0.05)
        break
      case 'tick':
        tone(880, 0, 0.04, 'square', 0.02)
        break
      case 'success':
        tone(660, 0, 0.12)
        tone(990, 0.08, 0.18)
        break
      case 'miss':
        tone(220, 0, 0.18, 'sawtooth', 0.04)
        tone(180, 0.1, 0.2, 'sawtooth', 0.03)
        break
      case 'win':
        ;[523, 659, 784, 1046].forEach((f, i) => tone(f, i * 0.1, 0.22))
        break
    }
  } catch {
    /* audio unavailable */
  }
}
