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

const VOICE_TAG: Record<string, string> = { en: 'en-US', de: 'de-DE', ru: 'ru-RU', uz: 'uz-UZ' }

/** Whether a voice exists for a language. Uzbek voices are often missing: then the button is hidden. */
export function hasVoice(lang: string): boolean {
  if (!ttsSupported()) return false
  if (lang === 'en' || lang === 'de') return true // the browser falls back to a default voice
  return Boolean(pickVoice(lang))
}

/** Speak text in a language: the foreign word in its own voice, a translation in the chosen language. */
export function speakIn(text: string, lang: string) {
  if (!ttsSupported() || !text) return
  const u = new SpeechSynthesisUtterance(text)
  u.lang = VOICE_TAG[lang] || lang
  const v = pickVoice(lang)
  if (v) u.voice = v
  u.rate = 0.9
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(u)
}

export function speak(text: string, track: Track) {
  speakIn(text, track === 'de' ? 'de' : 'en')
}

if (ttsSupported()) {
  // Chrome loads voices asynchronously.
  window.speechSynthesis.getVoices()
}
