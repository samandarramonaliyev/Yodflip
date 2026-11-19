import { useNavigate, useParams } from 'react-router-dom'
import { Segmented } from '../components/ui'
import { WordList, type ListKind } from '../components/WordList'
import { useT } from '../i18n'
import { useTelegramBack } from '../lib/hooks'
import { useApp } from '../store/app'

export default function Lists() {
  const { which = 'want' } = useParams<{ which: ListKind }>()
  const t = useT()
  const nav = useNavigate()
  const track = useApp((s) => s.track)
  useTelegramBack('/profile')
  return (
    <div className="page max-w-3xl space-y-4">
      <h1 className="h1">{t('lists.title')}</h1>
      <Segmented
        value={which}
        onChange={(v) => nav(`/lists/${v}`, { replace: true })}
        options={[
          { value: 'learned', label: `✅ ${t('lists.learned')}` },
          { value: 'missed', label: `❌ ${t('lists.missed')}` },
          { value: 'want', label: `⭐ ${t('lists.want')}` },
        ]}
      />
      <WordList which={which} track={track} />
    </div>
  )
}
