import qrcode from 'qrcode-generator'
import { useMemo } from 'react'

/** QR code as inline SVG (no network, no canvas: safe inside exported share cards). */
export function QrCode({ value, size = 160, fg = '#2D3436', bg = '#FFFFFF', className = '' }: { value: string; size?: number; fg?: string; bg?: string; className?: string }) {
  const { n, path } = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(value)
    qr.make()
    const count = qr.getModuleCount()
    let d = ''
    for (let r = 0; r < count; r++) for (let c = 0; c < count; c++) if (qr.isDark(r, c)) d += `M${c + 2},${r + 2}h1v1h-1z`
    return { n: count + 4, path: d }
  }, [value])
  return (
    <svg className={className} width={size} height={size} viewBox={`0 0 ${n} ${n}`} shapeRendering="crispEdges" role="img" aria-label="QR">
      <rect width={n} height={n} fill={bg} />
      <path d={path} fill={fg} />
    </svg>
  )
}
