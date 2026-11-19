import type { GameId } from './types'

export interface GameInfo {
  id: GameId
  emoji: string
  color: string // tailwind bg class
  /** Games that need a word source picker (all but daily/review) */
  needsSource: boolean
}

export const GAMES: GameInfo[] = [
  { id: 'match', emoji: '🃏', color: 'bg-primary/15', needsSource: true },
  { id: 'speed', emoji: '⚡', color: 'bg-accent/30', needsSource: true },
  { id: 'builder', emoji: '🧩', color: 'bg-success/15', needsSource: true },
  { id: 'falling', emoji: '🌧️', color: 'bg-sky-400/15', needsSource: true },
  { id: 'memory', emoji: '🧠', color: 'bg-pink-400/15', needsSource: true },
  { id: 'derdiedas', emoji: '🇩🇪', color: 'bg-accent/30', needsSource: true },
  { id: 'review', emoji: '🔁', color: 'bg-error/15', needsSource: false },
  { id: 'daily', emoji: '📅', color: 'bg-primary/15', needsSource: false },
]

export const gameInfo = (id: GameId) => GAMES.find((g) => g.id === id)

/** How many items each game takes from the source. */
export const GAME_LIMITS: Partial<Record<GameId, number>> = {
  speed: 80,
  builder: 10,
  falling: 40,
  memory: 6,
  derdiedas: 30,
  review: 20,
  daily: 10,
  match: 200,
}
