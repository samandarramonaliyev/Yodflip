// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ShareCard } from '../components/ShareCard'
import { ShareButton } from '../components/ShareSheet'
import { translate } from '../i18n'
import { useApp } from '../store/app'
import {
  buildCard,
  CARD_SIZES,
  exportCard,
  isStreakMilestone,
  mainFontSize,
  pngSize,
  referralLink,
  shareMethods,
  shortLink,
  supportsStory,
  webShare,
  type CardFormat,
} from './share'
import type { TelegramWebApp } from './telegram'

/** A minimal PNG header (signature + IHDR) with the given size. */
function fakePng(width: number, height: number): Blob {
  const b = new Uint8Array(33)
  b.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52])
  const v = new DataView(b.buffer)
  v.setUint32(16, width)
  v.setUint32(20, height)
  return new Blob([b], { type: 'image/png' })
}

const htmlToImage = vi.hoisted(() => ({ toBlob: vi.fn() }))
vi.mock('html-to-image', () => htmlToImage)

const uz = (k: string, v?: Record<string, string | number>) => translate('uz', k, v)
const ru = (k: string, v?: Record<string, string | number>) => translate('ru', k, v)

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  htmlToImage.toBlob.mockReset()
})

describe('card templates', () => {
  it('game result: big score, accuracy, time, XP', () => {
    const c = buildCard({ template: 'game', game: 'Tezkor juftlash', correct: 9, total: 10, accuracy: 90, durationMs: 83_000, xp: 45 }, uz)
    expect(c.main).toBe('9/10')
    expect(c.kicker).toBe('Tezkor juftlash')
    expect(c.stats).toEqual([
      { label: 'Aniqlik', value: '90%' },
      { label: 'Vaqt', value: '1:23' },
      { label: 'XP', value: '+45' },
    ])
  })

  it('streak, level, exam, duel, league and weekly in the interface language', () => {
    expect(buildCard({ template: 'streak', days: 30, best: 30 }, uz).main).toBe('🔥 30 kun')
    expect(buildCard({ template: 'streak', days: 30, best: 30 }, ru).main).toBe('🔥 30 дней')
    expect(buildCard({ template: 'streak', days: 7, best: 12 }, uz).stats.map((s) => s.value)).toEqual(['12 kun', '30 kun'])
    expect(buildCard({ template: 'level', level: 'B1', track: 'de', words: 200 }, uz).main).toBe('B1 yakunlandi')
    const exam = buildCard({ template: 'exam', pack: 'Goethe A1', percent: 50, found: 150, total: 300 }, uz)
    expect([exam.main, exam.stats[0].value]).toEqual(['50%', '150/300'])
    const duel = buildCard({ template: 'duel', score: 8, total: 10, opponent: 'Bek', timeMs: 41_000 }, uz)
    expect([duel.main, duel.kicker]).toEqual(['8/10', 'Bek bilan duel'])
    const league = buildCard({ template: 'league', tierEmoji: '🥇', tierName: 'Oltin', result: 'trophy', rank: 2, xp: 900 }, uz)
    expect([league.main, league.emoji, league.stats[0].value]).toEqual(['🥇 Oltin', '🏆', '#2'])
    const week = buildCard({ template: 'weekly', xp: 640, words: 35, accuracy: 88, streak: 6 }, uz)
    expect(week.main).toBe('640 XP')
    expect(week.stats).toHaveLength(3)
  })

  it('offers streak cards on milestone days only and fits long main texts', () => {
    expect([7, 30, 100].every(isStreakMilestone)).toBe(true)
    expect(isStreakMilestone(8)).toBe(false)
    expect(mainFontSize('9/10', 'story')).toBeGreaterThan(mainFontSize('B1 yakunlandi', 'story'))
    expect(mainFontSize('9/10', 'square')).toBeLessThan(mainFontSize('9/10', 'story'))
  })

  it('builds the referral link for the QR code', () => {
    expect(referralLink('ab3k', { bot_username: 'yodflip_bot', app_short_name: 'play' }, 'https://x')).toBe('https://t.me/yodflip_bot/play?startapp=ref_ab3k')
    expect(referralLink('ab3k', { bot_username: 'yodflip_bot' }, 'https://x')).toBe('https://t.me/yodflip_bot?start=ref_ab3k')
    expect(referralLink('ab3k', null, 'https://y.uz')).toBe('https://y.uz/?ref=ab3k')
    expect(shortLink('https://t.me/yodflip_bot/play?startapp=ref_ab3k')).toBe('t.me/yodflip_bot/play')
  })
})

describe('export at exact pixel sizes', () => {
  const content = buildCard({ template: 'game', game: 'Match', correct: 5, total: 5, accuracy: 100, durationMs: 1000, xp: 10 }, uz)

  it.each<[CardFormat, number, number]>([
    ['story', 1080, 1920],
    ['square', 1080, 1080],
  ])('%s → %i×%i', async (format, w, h) => {
    const { getByTestId } = render(<ShareCard content={content} format={format} theme="violet" name="Ali" footer="f" link="https://t.me/b" />)
    const node = getByTestId('share-card')
    expect([node.style.width, node.style.height]).toEqual([`${w}px`, `${h}px`])
    const lib = { toBlob: vi.fn(async () => fakePng(w, h)) }
    const blob = await exportCard(node, format, lib)
    expect(blob.size).toBe(33)
    expect(pngSize(new Uint8Array(await new Promise<ArrayBuffer>((ok) => { const r = new FileReader(); r.onload = () => ok(r.result as ArrayBuffer); r.readAsArrayBuffer(blob) })))).toEqual({ width: w, height: h })
    const opts = (lib.toBlob.mock.calls[0] as unknown[])[1] as Record<string, unknown>
    expect(opts).toMatchObject({ width: w, height: h, canvasWidth: w, canvasHeight: h, pixelRatio: 1 })
    expect(CARD_SIZES[format]).toEqual({ width: w, height: h })
  })

  it('rejects an image of the wrong size (then the server fallback is used)', async () => {
    const { getByTestId } = render(<ShareCard content={content} format="story" theme="dark" name={null} footer="f" link="https://t.me/b" />)
    const lib = { toBlob: vi.fn(async () => fakePng(2160, 3840)) }
    await expect(exportCard(getByTestId('share-card'), 'story', lib)).rejects.toThrow('export_wrong_size')
  })

  it('hides the name when asked and draws only inline content (no external images)', () => {
    const { container, queryByTestId } = render(<ShareCard content={content} format="square" theme="yellow" name={null} footer="Yodflip bilan so'z yodlayapman" link="https://t.me/b" />)
    expect(queryByTestId('card-name')).toBeNull()
    expect(container.querySelectorAll('img')).toHaveLength(0)
    expect(container.querySelector('svg[aria-label="QR"]')).toBeTruthy()
    expect(container.textContent).toContain("Yodflip bilan so'z yodlayapman")
  })
})

describe('sharing', () => {
  it('detects Telegram stories without crashing on old clients', () => {
    expect(supportsStory(undefined)).toBe(false)
    expect(supportsStory({} as TelegramWebApp)).toBe(false) // old client: no method
    expect(supportsStory({ shareToStory: () => undefined } as unknown as TelegramWebApp)).toBe(false) // no version check
    const throwing = { shareToStory: () => undefined, isVersionAtLeast: () => { throw new Error('old') } } as unknown as TelegramWebApp
    expect(supportsStory(throwing)).toBe(false)
    const v = (ok: boolean) => ({ shareToStory: () => undefined, isVersionAtLeast: (x: string) => x === '7.8' && ok }) as unknown as TelegramWebApp
    expect(supportsStory(v(false))).toBe(false)
    expect(supportsStory(v(true))).toBe(true)
  })

  it('chooses share buttons per environment', () => {
    expect(shareMethods({ telegram: true, story: true, webShareFiles: false, mobile: true })).toEqual(['story', 'telegram_link', 'download'])
    expect(shareMethods({ telegram: true, story: false, webShareFiles: true, mobile: true })).toEqual(['telegram_link', 'download'])
    expect(shareMethods({ telegram: false, story: false, webShareFiles: true, mobile: true })).toEqual(['webshare', 'download', 'copy'])
    expect(shareMethods({ telegram: false, story: false, webShareFiles: false, mobile: false })).toEqual(['download', 'copy'])
  })

  it('uses the Web Share API with the PNG file, and reports when it is missing', async () => {
    const blob = fakePng(1080, 1920)
    expect(await webShare(blob, 'a.png', 'hi', {})).toBe(false)
    expect(await webShare(blob, 'a.png', 'hi', { share: vi.fn(), canShare: () => false })).toBe(false)
    const share = vi.fn(async () => undefined)
    expect(await webShare(blob, 'a.png', 'hi', { share, canShare: () => true })).toBe(true)
    const arg = (share.mock.calls[0] as unknown[])[0] as { files: File[]; text: string }
    expect(arg.files[0].name).toBe('a.png')
    expect(arg.files[0].type).toBe('image/png')
    const cancelled = vi.fn(async () => {
      throw new DOMException('cancel', 'AbortError')
    })
    expect(await webShare(blob, 'a.png', 'hi', { share: cancelled, canShare: () => true })).toBe(true)
  })
})

describe('share sheet', () => {
  beforeEach(() => {
    useApp.setState({ lang: 'uz', user: { id: 1, display_name: 'Aziz', referral_code: 'ab3k9mzq' } as never, config: { bot_username: 'yodflip_bot', app_short_name: 'play' } as never })
  })

  it('falls back to downloading the PNG with the Instagram hint when Web Share is unavailable', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', async (url: string) => {
      calls.push(String(url))
      return new Response('{}', { status: 201 })
    })
    const created: Blob[] = []
    URL.createObjectURL = vi.fn((b: Blob) => {
      created.push(b)
      return 'blob:x'
    }) as never
    URL.revokeObjectURL = vi.fn()
    htmlToImage.toBlob.mockResolvedValue(fakePng(1080, 1920))
    render(
      <MemoryRouter>
        <ShareButton input={{ template: 'streak', days: 30, best: 30 }} />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByTestId('share-btn'))
    const sheet = await screen.findByTestId('share-sheet')
    expect(sheet.textContent).toContain('🔥 30 kun')
    expect(screen.queryByTestId('share-story')).toBeNull()
    expect(screen.queryByTestId('share-webshare')).toBeNull()
    fireEvent.click(screen.getByTestId('share-download'))
    await waitFor(() => expect(created).toHaveLength(1))
    expect(calls.some((c) => c.endsWith('/share/render/'))).toBe(false) // client export worked: no server fallback
    expect(htmlToImage.toBlob).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ width: 1080, height: 1920 }))
    expect(await screen.findByTestId('share-hint')).toBeTruthy()
    await waitFor(() => expect(calls.some((c) => c.endsWith('/share/events/'))).toBe(true))
  })

  it('switches to the square format and hides the name', async () => {
    render(
      <MemoryRouter>
        <ShareButton input={{ template: 'weekly', xp: 100, words: 5, accuracy: 80, streak: 2 }} />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByTestId('share-btn'))
    await screen.findByTestId('share-sheet')
    fireEvent.click(screen.getByText('Kvadrat 1:1'))
    const cards = screen.getAllByTestId('share-card')
    expect(cards.every((c) => c.getAttribute('data-format') === 'square')).toBe(true)
    expect(screen.getAllByTestId('card-name')).toHaveLength(2) // preview + export node
    fireEvent.click(screen.getByText("Ismimni ko'rsatma"))
    expect(screen.queryAllByTestId('card-name')).toHaveLength(0)
  })
})
