import { useState } from 'react'
import { useT } from '../i18n'
import { useApp } from '../store/app'

interface Point {
  date: string
  xp: number
  correct: number
}

/** 7-day XP bars. Single series: one hue, no legend; hover/tap shows the value; sr-only table. */
export function XpChart({ data }: { data: Point[] }) {
  const t = useT()
  const lang = useApp((s) => s.lang)
  const [active, setActive] = useState<number | null>(null)
  const max = Math.max(10, ...data.map((d) => d.xp))
  const UZ_DAYS = ['Ya', 'Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh']
  const locale = lang
  const day = (iso: string) => {
    if (lang === 'uz') return UZ_DAYS[new Date(iso + 'T00:00:00').getDay()]
    try {
      return new Date(iso + 'T00:00:00').toLocaleDateString(locale, { weekday: 'short' })
    } catch {
      return iso.slice(5)
    }
  }
  const best = data.reduce((b, d, i) => (d.xp > (data[b]?.xp ?? 0) ? i : b), 0)

  return (
    <figure>
      <figcaption className="h2 mb-3">{t('profile.activity')}</figcaption>
      <div className="relative flex h-36 items-end gap-[2px] border-b border-line" onMouseLeave={() => setActive(null)} aria-hidden>
        {data.map((d, i) => {
          const h = d.xp ? Math.max(4, (d.xp / max) * 100) : 0
          const show = active === i || (active === null && i === best && d.xp > 0)
          return (
            <button
              key={d.date}
              type="button"
              tabIndex={-1}
              className="group relative flex h-full flex-1 items-end justify-center px-[10%]"
              onMouseEnter={() => setActive(i)}
              onClick={() => setActive(i)}
            >
              {show && (
                <span className="absolute z-10 -translate-y-1 whitespace-nowrap rounded-lg bg-card px-2 py-0.5 text-xs font-extrabold text-ink shadow-soft" style={{ bottom: `${h}%` }}>
                  {d.xp} XP
                </span>
              )}
              <span className={`w-full max-w-[28px] rounded-t-[4px] transition-colors ${active === i ? 'bg-primary-dark' : 'bg-primary'}`} style={{ height: `${h}%` }} />
            </button>
          )
        })}
      </div>
      <div className="mt-1 flex gap-[2px]" aria-hidden>
        {data.map((d) => (
          <span key={d.date} className="flex-1 text-center text-[11px] font-bold capitalize text-muted">
            {day(d.date)}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>{t('profile.activity')}</caption>
        <thead>
          <tr>
            <th>{t('profile.date')}</th>
            <th>XP</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <td>{d.date}</td>
              <td>{d.xp}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
