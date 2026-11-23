// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
vi.mock('./api', () => ({ api: { get: (...a: unknown[]) => get(...a) }, getTokens: () => ({}), setTokens: () => undefined }))

class Utterance {
  lang = ''
  voice: unknown = null
  rate = 1
  constructor(public text: string) {}
}
let voices: { lang: string; name: string }[] = []
const spoken: Utterance[] = []

async function fresh() {
  vi.resetModules()
  return import('./tts')
}

beforeEach(() => {
  get.mockReset()
  spoken.length = 0
  voices = [
    { lang: 'en-US', name: 'Google US English' },
    { lang: 'de_DE', name: 'Anna' },
    { lang: 'de-DE', name: 'Google Deutsch' },
  ]
  vi.stubGlobal('SpeechSynthesisUtterance', Utterance)
  Object.defineProperty(window, 'speechSynthesis', {
    configurable: true,
    value: { getVoices: () => voices, cancel: () => undefined, speak: (u: Utterance) => spoken.push(u) },
  })
  HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve())
  HTMLMediaElement.prototype.pause = vi.fn()
  vi.stubGlobal('fetch', () => Promise.resolve(new Response('')))
  localStorage.clear()
})

describe('tts', () => {
  it('plays server audio with the right language on one shared player', async () => {
    get.mockImplementation((_: string, q: { text: string }) => Promise.resolve({ url: `/static/tts/${q.text}.mp3` }))
    const t = await fresh()
    await t.speakIn('der', 'de')
    expect(get).toHaveBeenCalledWith('/tts/', { text: 'der', lang: 'de', rate: 'normal', voice: 'female' })
    const p = t.getPlayer()!
    expect(p.src).toContain('/static/tts/der.mp3')
    await t.speakIn('house', 'en', 'slow')
    expect(get).toHaveBeenLastCalledWith('/tts/', { text: 'house', lang: 'en', rate: 'slow', voice: 'us' })
    expect(t.getPlayer()).toBe(p)
    await t.speakIn('der', 'de')
    expect(get).toHaveBeenCalledTimes(2) // url is remembered
    expect(spoken).toEqual([])
  })

  it('falls back to a browser voice of the same language', async () => {
    get.mockResolvedValue({ url: null, fallback: true })
    const t = await fresh()
    await t.speakIn('der Bahnhof', 'de')
    expect(spoken[0].lang).toBe('de-DE')
    expect((spoken[0].voice as { name: string }).name).toBe('Google Deutsch')
    await t.speakIn('house', 'en')
    expect(spoken[1].lang).toBe('en-US')
  })

  it('never reads German with an English voice', async () => {
    voices = [{ lang: 'en-US', name: 'Google US English' }]
    get.mockRejectedValue(new Error('429'))
    const t = await fresh()
    await t.speakIn('der Bahnhof', 'de')
    expect(spoken).toEqual([])
    voices = [] // Android WebView: list unknown → only the forced language
    await t.speakIn('die Straße', 'de')
    expect(spoken[0].lang).toBe('de-DE')
    expect(spoken[0].voice).toBeNull()
  })

  it('uses the chosen voices and has no Uzbek speaker', async () => {
    get.mockResolvedValue({ url: '/x.mp3' })
    const t = await fresh()
    t.useTts.getState().set({ de: 'male', en: 'uk' })
    await t.speakIn('Tag', 'de')
    await t.speakIn('day', 'en')
    expect(get.mock.calls.map((c) => c[1].voice)).toEqual(['male', 'uk'])
    expect(t.hasVoice('uz')).toBe(false)
    await t.speakIn('olma', 'uz')
    expect(get).toHaveBeenCalledTimes(2)
  })
})
