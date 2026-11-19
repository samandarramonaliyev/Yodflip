import { shuffle } from './matchMachine'
import { sidesFor } from './direction'
import type { GameId, GameItem, Track } from './types'

/** Build up to `n` multiple-choice options (answer + distractors from the same pool). Null if too few. */
export function makeOptions(item: GameItem, pool: GameItem[], game: GameId, track: Track, reverse: boolean, n = 4): string[] | null {
  const answer = sidesFor(item, game, track, reverse).answer
  const others = shuffle(
    [...new Set(pool.filter((p) => p.key !== item.key).map((p) => sidesFor(p, game, track, reverse).answer))].filter(
      (a) => a && a.toLowerCase() !== answer.toLowerCase(),
    ),
  )
  if (others.length < n - 1) return others.length >= 1 ? shuffle([answer, ...others]) : null
  return shuffle([answer, ...others.slice(0, n - 1)])
}

export function now() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}
