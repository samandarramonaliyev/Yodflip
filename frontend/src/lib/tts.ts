/**
 * Pronunciation: neural audio from the server (one shared player), browser voice only as fallback.
 * The language is always the language of the text; a voice of another language is never used.
 */
import { useEffect } from 'react'
import { create } from 'zustand'
import type { Track } from '../games/types'
import { useApp } from '../store/app'
import { api, getTokens } from './api'
import { load, save } from './storage'

export type SpeechRate = 'normal' | 'slow'

/* ------------------------------------------------------------------ settings */
export interface TtsPrefs {
  de: 'female' | 'male'
  en: 'us' | 'uk'
  speed: number
  auto: boolean
}
const DEFAULTS: TtsPrefs = { de: 'female', en: 'us', speed: 1, auto: false }

export const useTts = create<TtsPrefs & { set: (p: Partial<TtsPrefs>) => void }>((set, get) => ({
  ...DEFAULTS,
  ...load<Partial<TtsPrefs>>('wf.tts', {}),
  set: (p) => {
    set(p)
    const { de, en, speed, auto } = get()
    save('wf.tts', { de, en, speed, auto })
  },
}))

/* -------------------------------------------------------------- browser voice */
const TAG: Record<string, string> = { en: 'en-US', de: 'de-DE', ru: 'ru-RU' }

export function ttsSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function pickVoice(tag: string): SpeechSynthesisVoice | undefined {
  const norm = (v: SpeechSynthesisVoice) => (v.lang || '').toLowerCase().replace('_', '-')
  const voices = window.speechSynthesis.getVoices().filter((v) => norm(v).slice(0, 2) === tag.slice(0, 2))
  const exact = voices.filter((v) => norm(v) === tag.toLowerCase())
  const pool = exact.length ? exact : voices
  return pool.find((v) => /neural|natural|premium|enhanced|google/i.test(v.name)) || pool[0]
}

/** Browser voice with the forced language. Silent when the device only has voices of other languages. */
export function browserSpeak(text: string, lang: string, rate: SpeechRate = 'normal'): boolean {
  const tag = lang === 'en' && useTts.getState().en === 'uk' ? 'en-GB' : TAG[lang]
  if (!tag || !ttsSupported() || !text) return false
  const voice = pickVoice(tag)
  if (!voice && window.speechSynthesis.getVoices().length) return false
  const u = new SpeechSynthesisUtterance(text)
  u.lang = tag
  if (voice) u.voice = voice
  u.rate = (rate === 'slow' ? 0.7 : 0.95) * useTts.getState().speed
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(u)
  return true
}

/** Uzbek has no good voice: its speaker button is hidden. */
export function hasVoice(lang: string): boolean {
  if (lang === 'de' || lang === 'en') return true
  if (lang !== 'ru') return false
  return Boolean(useApp.getState().config?.tts) || (ttsSupported() && Boolean(pickVoice('ru-RU')))
}

/* --------------------------------------------------------------- neural audio */
const urls = new Map<string, Promise<string | null>>()
const ready = new Map<string, string | null>()

function voiceFor(lang: string): string | undefined {
  const s = useTts.getState()
  return lang === 'de' ? s.de : lang === 'en' ? s.en : undefined
}

/** URL of the audio (null → use the browser voice). One request per text, voice and rate. */
export function audioUrl(text: string, lang: string, rate: SpeechRate = 'normal'): Promise<string | null> {
  if (!TAG[lang] || !text || text.length > 200 || !getTokens()) return Promise.resolve(null)
  const voice = voiceFor(lang)
  const key = [lang, voice, rate, text].join('|')
  let p = urls.get(key)
  if (!p) {
    p = Promise.resolve()
      .then(() => api.get<{ url: string | null }>('/tts/', { text, lang, rate, voice }))
      .then((r) => r?.url ?? null)
      .catch(() => null)
      .then((url) => {
        if (url) ready.set(key, url)
        else setTimeout(() => urls.delete(key), 30_000) // try again later (limit, network, no key)
        return url
      })
    urls.set(key, p)
  }
  return p
}

const preloaded = new Set<string>()
/** Warm the HTTP cache for a card that is (or is about to be) on screen. */
export function preload(text: string | undefined, lang: string) {
  if (!text) return
  void audioUrl(text, lang).then((url) => {
    if (!url || preloaded.has(url)) return
    preloaded.add(url)
    void fetch(url).catch(() => preloaded.delete(url))
  })
}

const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='
let player: HTMLAudioElement | null = null
let token = 0

export function getPlayer(): HTMLAudioElement | null {
  if (typeof Audio === 'undefined') return null
  if (!player) {
    player = new Audio()
    player.preload = 'auto'
  }
  return player
}

/** iOS / Telegram WebView: an element that played inside a gesture may play later without one. */
let unlocked = false
function unlock() {
  const p = getPlayer()
  if (unlocked || !p) return
  unlocked = true
  if (p.src && !p.paused) return
  p.src = SILENCE
  try {
    void p.play()?.catch(() => {
      unlocked = false
    })
  } catch {
    unlocked = false
  }
}
if (typeof window !== 'undefined') {
  for (const e of ['touchend', 'click', 'keydown']) window.addEventListener(e, unlock, { capture: true, passive: true })
  if (ttsSupported()) window.speechSynthesis.getVoices() // Chrome loads voices asynchronously
}

export function stopSpeech() {
  token++
  player?.pause()
  if (ttsSupported()) window.speechSynthesis.cancel()
}

/** Speak `text` in its own language. Resolves when playback has started (or cannot start). */
export async function speakIn(text: string, lang: string, rate: SpeechRate = 'normal'): Promise<void> {
  stopSpeech()
  const mine = token
  const key = [lang, voiceFor(lang), rate, text].join('|')
  const url = ready.get(key) ?? (await audioUrl(text, lang, rate)) // ready: stays inside the tap gesture
  if (mine !== token) return
  const p = getPlayer()
  if (url && p) {
    try {
      p.src = url
      p.playbackRate = useTts.getState().speed
      await p.play()
      return
    } catch (e) {
      if (mine !== token || (e as Error)?.name === 'AbortError') return
    }
  }
  browserSpeak(text, lang, rate)
}

/** Resolves when the current speech is over (for "listen to all"). */
export async function speakToEnd(text: string, lang: string): Promise<void> {
  await speakIn(text, lang)
  const mine = token
  const p = getPlayer()
  const limit = Date.now() + 12_000
  const busy = () => (p && p.src && !p.paused && !p.ended) || (ttsSupported() && (window.speechSynthesis.speaking || window.speechSynthesis.pending))
  while (mine === token && busy() && Date.now() < limit) await new Promise((r) => setTimeout(r, 100))
}

export function speak(text: string, track: Track) {
  void speakIn(text, track)
}

/** "So'zni avtomatik o'qish": speak when the foreign side becomes visible. */
export function useAutoSpeak(text: string | undefined, lang: Track, visible: boolean) {
  const auto = useTts((s) => s.auto)
  useEffect(() => {
    if (auto && visible && text) void speakIn(text, lang)
  }, [auto, visible, text, lang])
}

/** Preload the current and the next card. */
export function usePreload(texts: (string | undefined)[], lang: Track) {
  const key = texts.join('|')
  useEffect(() => {
    texts.forEach((x) => preload(x, lang))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, lang])
}
