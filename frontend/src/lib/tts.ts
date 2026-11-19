/* Text-to-speech with the Web Speech API, picking an English or German voice. */
import type { Track } from '../games/types'

export function ttsSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function pickVoice(lang: string): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices()
  const exact = voices.filter((v) => v.lang?.toLowerCase().replace('_', '-').startsWith(lang))
  return exact.find((v) => /google|natural|premium|enhanced/i.test(v.name)) || exact[0]
}

export function speak(text: string, track: Track) {
  if (!ttsSupported() || !text) return
  const lang = track === 'de' ? 'de' : 'en'
  const u = new SpeechSynthesisUtterance(text)
  u.lang = track === 'de' ? 'de-DE' : 'en-US'
  const v = pickVoice(lang)
  if (v) u.voice = v
  u.rate = 0.9
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(u)
}

if (ttsSupported()) {
  // Chrome loads voices asynchronously.
  window.speechSynthesis.getVoices()
}
