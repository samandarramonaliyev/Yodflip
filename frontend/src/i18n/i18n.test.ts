import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from './en.json'
import ru from './ru.json'
import uz from './uz.json'
import { translate } from './index'

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) && !f.endsWith('.test.ts') ? [p] : []
  })
}

const SRC = join(__dirname, '..')
const used = new Set<string>()
for (const f of files(SRC)) {
  const text = readFileSync(f, 'utf8')
  for (const m of text.matchAll(/\bt\(\s*'([a-z_]+\.[a-zA-Z0-9_.]+)'/g)) used.add(m[1])
}
// dynamic keys
const GAMES = ['match', 'speed', 'builder', 'falling', 'memory', 'derdiedas', 'review', 'daily', 'flashcards', 'learn', 'write']
GAMES.forEach((g) => used.add(`game.${g}`) && used.add(`game.${g}_desc`))
;['A1', 'A2', 'B1', 'B2', 'C1'].forEach((c) => used.add(`cefr.${c}`))
;['learned', 'missed', 'want'].forEach((l) => [`lists.${l}`, `lists.${l}_empty`, `lists.${l}_empty_text`].forEach((k) => used.add(k)))
;['easy', 'medium', 'hard'].forEach((d) => used.add(`play.${d}`))
;['network', 'limit', 'too_large', 'forbidden', 'not_found', 'server', 'generic'].forEach((e) => used.add(`err.${e}`))
const ACH = ['first_game', 'first_scan', 'first_deck', 'perfect_round', 'streak_3', 'streak_7', 'streak_30', 'words_10', 'words_100', 'words_500', 'xp_1000', 'daily_first', 'polyglot', 'deck_master', 'level_complete', 'first_duel', 'duel_wins_10', 'invited_5', 'exam_pack_50', 'exam_pack_100']
ACH.forEach((a) => used.add(`ach.${a}`) && used.add(`ach.${a}_desc`))

;['win', 'draw', 'loss'].forEach((o) => used.add(`duel.${o}`))

;['translation', 'reverse', 'definition'].forEach((k) => used.add(`exam.q_${k}`))

;['tab_switch', 'focus_loss', 'printscreen', 'copy', 'devtools'].forEach((k) => used.add(`exam.v_${k}`))

describe('i18n', () => {
  it.each([
    ['uz', uz],
    ['en', en],
    ['ru', ru],
  ])('%s has every key used in the code', (_, dict) => {
    const missing = [...used].filter((k) => !(k in dict))
    expect(missing).toEqual([])
  })

  it('all locales have the same keys', () => {
    expect(Object.keys(uz).sort()).toEqual(Object.keys(en).sort())
    expect(Object.keys(ru).sort()).toEqual(Object.keys(en).sort())
  })

  it('interpolates variables and falls back', () => {
    expect(translate('en', 'home.streak_days', { n: 3 })).toBe('3-day streak')
    expect(translate('uz', 'unknown.key')).toBe('unknown.key')
  })
})
