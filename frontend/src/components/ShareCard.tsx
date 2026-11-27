import { forwardRef } from 'react'
import { CARD_SIZES, mainFontSize, shortLink, THEMES, type CardContent, type CardFormat, type CardTheme } from '../lib/share'
import { QrCode } from './QrCode'

export interface ShareCardProps {
  content: CardContent
  format: CardFormat
  theme: CardTheme
  name: string | null // null = "Ismimni ko'rsatma"
  footer: string
  link: string
}

function Logo({ size, theme }: { size: number; theme: CardTheme }) {
  const back = theme === 'yellow' ? '#FFFFFF' : '#FDCB6E'
  const front = theme === 'yellow' ? '#6C5CE7' : theme === 'violet' ? '#2D2A6E' : '#6C5CE7'
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <rect x="6" y="10" width="34" height="44" rx="8" fill={back} transform="rotate(-10 23 32)" />
      <rect x="22" y="8" width="34" height="44" rx="8" fill={front} />
      <path d="M32 18 L39 30 L46 18 M39 30 L39 42" stroke="#fff" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

/** The card at its real pixel size (1080 wide). Only inline SVG and text: nothing can taint the canvas. */
export const ShareCard = forwardRef<HTMLDivElement, ShareCardProps>(function ShareCard({ content, format, theme, name, footer, link }, ref) {
  const { width, height } = CARD_SIZES[format]
  const c = THEMES[theme]
  const story = format === 'story'
  const s = (px: number) => (story ? px : Math.round(px * 0.8))
  const shape = (i: number, style: React.CSSProperties) => (
    <div key={i} style={{ position: 'absolute', borderRadius: 48, background: c.shapes[i], opacity: theme === 'dark' ? 0.35 : 0.5, ...style }} />
  )
  return (
    <div
      ref={ref}
      data-testid="share-card"
      data-format={format}
      style={{
        width,
        height,
        position: 'relative',
        overflow: 'hidden',
        background: c.bg,
        color: c.fg,
        fontFamily: "'Nunito', sans-serif",
        boxSizing: 'border-box',
        padding: story ? '96px 80px 80px' : '64px 72px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
      }}
    >
      {/* playful flash-card shapes */}
      {shape(0, { width: 360, height: 460, top: -120, left: -140, transform: 'rotate(-18deg)' })}
      {shape(1, { width: 300, height: 380, top: story ? 380 : 260, right: -170, transform: 'rotate(14deg)' })}
      {shape(2, { width: 260, height: 330, bottom: story ? 420 : 200, left: -150, transform: 'rotate(10deg)' })}
      {shape(3, { width: 340, height: 420, bottom: -200, right: -100, transform: 'rotate(-12deg)' })}

      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 20 }}>
        <Logo size={s(104)} theme={theme} />
        <span style={{ fontSize: s(72), fontWeight: 900, letterSpacing: -1 }}>Yodflip</span>
      </div>

      <div style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: s(28), width: '100%' }}>
        <div style={{ fontSize: s(150), lineHeight: 1 }}>{content.emoji}</div>
        <div style={{ fontSize: s(54), fontWeight: 800, color: c.sub, maxWidth: '92%' }}>{content.kicker}</div>
        <div data-testid="card-main" style={{ fontSize: mainFontSize(content.main, format), fontWeight: 900, lineHeight: 1.02, letterSpacing: -2, color: c.fg, maxWidth: '100%', wordBreak: 'break-word' }}>
          {content.main}
        </div>
        <div style={{ display: 'flex', gap: 24, marginTop: s(24), justifyContent: 'center', width: '100%' }}>
          {content.stats.map((st) => (
            <div key={st.label} data-testid="card-stat" style={{ flex: 1, maxWidth: 300, background: c.panel, borderRadius: 36, padding: `${s(28)}px 16px` }}>
              <div style={{ fontSize: s(64), fontWeight: 900, color: c.accent }}>{st.value}</div>
              <div style={{ fontSize: s(32), fontWeight: 700, color: c.sub, marginTop: 6 }}>{st.label}</div>
            </div>
          ))}
        </div>
        {name && (
          <div data-testid="card-name" style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: s(36) }}>
            <span style={{ width: s(96), height: s(96), borderRadius: '50%', background: c.accent, color: theme === 'yellow' ? '#FFFFFF' : '#2D3436', display: 'grid', placeItems: 'center', fontSize: s(44), fontWeight: 900 }}>
              {[...name.trim()][0]?.toUpperCase() || '★'}
            </span>
            <span style={{ fontSize: s(48), fontWeight: 800 }}>{name}</span>
          </div>
        )}
      </div>

      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 36, background: c.panel, borderRadius: 44, padding: story ? 32 : 24, width: '100%', boxSizing: 'border-box' }}>
        <div style={{ background: '#FFFFFF', borderRadius: 28, padding: 14, lineHeight: 0 }}>
          <QrCode value={link} size={story ? 200 : 150} />
        </div>
        <div style={{ textAlign: 'left', flex: 1 }}>
          <div style={{ fontSize: s(46), fontWeight: 900, lineHeight: 1.15 }}>{footer}</div>
          <div style={{ fontSize: s(34), fontWeight: 700, color: c.sub, marginTop: 10 }}>{shortLink(link)}</div>
        </div>
      </div>
    </div>
  )
})
