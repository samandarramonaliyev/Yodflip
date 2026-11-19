import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

/** A 3D flipping card. `front` is shown when flipped=false. */
export function FlipCard({
  flipped,
  front,
  back,
  className = '',
  duration = 0.35,
}: {
  flipped: boolean
  front: ReactNode
  back: ReactNode
  className?: string
  duration?: number
}) {
  return (
    <div className={`flip-scene ${className}`}>
      <motion.div className="flip-inner" initial={false} animate={{ rotateY: flipped ? 180 : 0 }} transition={{ duration, ease: [0.4, 0.2, 0.2, 1] }}>
        <div className="flip-face">{front}</div>
        <div className="flip-face flip-back">{back}</div>
      </motion.div>
    </div>
  )
}
