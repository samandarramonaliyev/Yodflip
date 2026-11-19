/** Normalise an answer for comparison: lowercase, trim, strip punctuation, unify apostrophes. */
export function normalize(s: string): string {
  return (s || '')
    .toLowerCase()
    .normalize('NFC')
    .replace(/[ʻʼ‘’`´]/g, "'")
    .replace(/[.,!?;:()"«»]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Strip a leading "to " (EN verbs) or article (DE nouns) for lenient comparisons. */
export function stripLead(s: string): string {
  return s.replace(/^(to|der|die|das)\s+/, '')
}

export function levenshtein(a: string, b: string): number {
  if (a === b) return 0
  if (!a.length) return b.length
  if (!b.length) return a.length
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
    }
    prev = cur
  }
  return prev[b.length]
}

export type Verdict = 'exact' | 'typo' | 'wrong'

/**
 * Check a typed answer. The expected answer may contain alternatives separated by "," "/" or ";".
 * Small typos are accepted: 1 edit for words ≤ 6 chars, 2 edits for longer ones.
 */
export function checkAnswer(input: string, expected: string): Verdict {
  const given = normalize(input)
  if (!given) return 'wrong'
  const options = expected
    .split(/[,/;]|\(|\)/)
    .map(normalize)
    .filter(Boolean)
  options.push(normalize(expected))
  let best: Verdict = 'wrong'
  for (const opt of options) {
    for (const [g, o] of [
      [given, opt],
      [stripLead(given), stripLead(opt)],
    ]) {
      if (g === o) return 'exact'
      const allowed = o.length <= 3 ? 0 : o.length <= 6 ? 1 : 2
      if (levenshtein(g, o) <= allowed) best = 'typo'
    }
  }
  return best
}
