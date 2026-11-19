import confetti from 'canvas-confetti'
import { haptic } from './telegram'
import { play } from './sound'

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Small confetti burst from an element (or the screen centre). */
export function burst(el?: Element | null, big = false) {
  if (reduced()) return
  let origin = { x: 0.5, y: 0.5 }
  if (el) {
    const r = el.getBoundingClientRect()
    origin = { x: (r.left + r.width / 2) / window.innerWidth, y: (r.top + r.height / 2) / window.innerHeight }
  }
  void confetti({
    particleCount: big ? 120 : 28,
    spread: big ? 90 : 55,
    startVelocity: big ? 38 : 22,
    scalar: big ? 1 : 0.7,
    ticks: big ? 200 : 90,
    origin,
    colors: ['#6C5CE7', '#00B894', '#FDCB6E', '#FF7675'],
    disableForReducedMotion: true,
  })
}

export function feedbackCorrect(el?: Element | null) {
  play('success')
  haptic('success')
  burst(el)
}

export function feedbackWrong() {
  play('miss')
  haptic('error')
}

export function feedbackWin() {
  play('win')
  haptic('success')
  burst(null, true)
}
