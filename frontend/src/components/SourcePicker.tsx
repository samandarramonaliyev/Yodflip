import { Lock } from 'lucide-react'
import { useState } from 'react'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { Deck, LevelRow, WordSet } from '../lib/types'
import { useApp } from '../store/app'
import type { Source } from '../games/types'
import { ListSkeleton, Segmented } from './ui'

export interface SourceChoice {
  source: Source
  level?: string
  pack?: string
  id?: number
  label: string
}

type Tab = 'levels' | 'decks' | 'sets' | 'lists'

export function SourcePicker({ value, onChange }: { value: SourceChoice | null; onChange: (c: SourceChoice) => void }) {
  const t = useT()
  const track = useApp((s) => s.track)
  const lang = useApp((s) => s.lang)
  const [tab, setTab] = useState<Tab>('levels')
  const levels = useAsync(() => api.get<{ levels: LevelRow[] }>('/words/levels/', { track }), [track])
  const decks = useAsync(() => api.get<Deck[]>('/decks/', { track }), [track])
  const sets = useAsync(() => api.get<WordSet[]>('/sets/', { track }), [track])

  const isSel = (c: Partial<SourceChoice>) =>
    value?.source === c.source && value?.level === c.level && value?.pack === c.pack && value?.id === c.id

  const Item = ({ c, sub, disabled }: { c: SourceChoice; sub?: string; disabled?: boolean }) => (
    <button
      disabled={disabled}
      onClick={() => onChange(c)}
      className={`flex min-h-[52px] w-full items-center justify-between gap-2 rounded-2xl px-4 text-left font-bold transition ${
        isSel(c) ? 'bg-primary text-white' : 'bg-line/60 hover:bg-line'
      } disabled:opacity-50`}
    >
      <span className="truncate">{c.label}</span>
      {sub && <span className={`shrink-0 text-xs ${isSel(c) ? 'text-white/80' : 'text-muted'}`}>{sub}</span>}
      {disabled && <Lock className="h-4 w-4 shrink-0" />}
    </button>
  )

  return (
    <div className="space-y-3">
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'levels', label: t('src.levels') },
          { value: 'decks', label: t('src.decks') },
          { value: 'sets', label: t('src.sets') },
          { value: 'lists', label: t('src.lists') },
        ]}
      />
      <div className="max-h-[46vh] space-y-2 overflow-y-auto pr-1">
        {tab === 'levels' &&
          (levels.loading ? (
            <ListSkeleton rows={4} height="h-12" />
          ) : (
            levels.data?.levels.map((lv) => (
              <div key={lv.level} className="space-y-2">
                <Item c={{ source: 'level', level: lv.level, label: t('levels.all_words', { level: lv.level }) }} sub={`${lv.percent}%`} disabled={!lv.unlocked} />
                {lv.unlocked && (
                  <div className="grid grid-cols-2 gap-2 pl-3">
                    {lv.packs.map((p) => (
                      <Item key={p.slug} c={{ source: 'level', level: lv.level, pack: p.slug, label: `${p.emoji} ${p.name[lang]}` }} sub={`${p.total}`} />
                    ))}
                  </div>
                )}
              </div>
            ))
          ))}
        {tab === 'decks' &&
          (decks.loading ? (
            <ListSkeleton rows={3} height="h-12" />
          ) : decks.data?.length ? (
            decks.data.map((d) => <Item key={d.id} c={{ source: 'deck', id: d.id, label: d.name }} sub={t('decks.cards_n', { n: d.card_count })} />)
          ) : (
            <p className="py-6 text-center text-muted">{t('decks.empty')}</p>
          ))}
        {tab === 'sets' &&
          (sets.loading ? (
            <ListSkeleton rows={3} height="h-12" />
          ) : sets.data?.length ? (
            sets.data.map((s) => <Item key={s.id} c={{ source: 'set', id: s.id, label: s.name }} sub={t('sets.pairs_n', { n: s.pair_count })} />)
          ) : (
            <p className="py-6 text-center text-muted">{t('sets.empty')}</p>
          ))}
        {tab === 'lists' && (
          <>
            <Item c={{ source: 'missed', label: `❌ ${t('lists.missed')}` }} />
            <Item c={{ source: 'want', label: `⭐ ${t('lists.want')}` }} />
            <Item c={{ source: 'learned', label: `✅ ${t('lists.learned')}` }} />
          </>
        )}
      </div>
    </div>
  )
}
