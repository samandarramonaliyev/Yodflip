import { Copy } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { SpeakButton } from '../components/WordActions'
import { EmptyState, ErrorState, ListSkeleton, Spinner, toast } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { Deck } from '../lib/types'
import { useApp } from '../store/app'

export default function SharedDeck() {
  const { code } = useParams()
  const t = useT()
  const nav = useNavigate()
  const user = useApp((s) => s.user)
  const setTrack = useApp((s) => s.setTrack)
  const { data: deck, error, loading, reload } = useAsync(() => api.publicGet<Deck>(`/decks/shared/${code}/`), [code])
  const [busy, setBusy] = useState(false)

  const copy = async () => {
    if (!user) {
      nav(`/login?next=/d/${code}`)
      return
    }
    setBusy(true)
    try {
      const d = await api.post<Deck>(`/decks/shared/${code}/`)
      setTrack(d.track)
      toast.ok(t('decks.copied'))
      nav(`/decks/${d.id}`)
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>
  if (loading || !deck) return <div className="page"><ListSkeleton rows={5} /></div>

  return (
    <div className="page max-w-3xl space-y-4">
      <div className="card space-y-2 p-5">
        <div className="text-sm font-bold text-muted">
          {deck.track === 'en' ? 'EN · English' : 'DE · Deutsch'} · {t('decks.by', { name: deck.owner_name })}
        </div>
        <h1 className="h1">{deck.name}</h1>
        {deck.description && <p className="text-muted">{deck.description}</p>}
        {deck.is_owner ? (
          <Link to={`/decks/${deck.id}`} className="btn-soft w-full">
            {t('decks.open_mine')}
          </Link>
        ) : (
          <button className="btn-primary w-full" onClick={copy} disabled={busy}>
            {busy ? <Spinner className="h-5 w-5" /> : <Copy className="h-5 w-5" />} {t('decks.copy_to_mine')}
          </button>
        )}
      </div>
      {!deck.cards?.length ? (
        <EmptyState title={t('decks.no_cards')} />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {deck.cards.map((c) => (
            <li key={c.id} className="card flex items-center gap-3 p-3">
              <SpeakButton text={c.term} track={deck.track} />
              <div className="min-w-0">
                <div className="font-black">{c.term}</div>
                <div className="font-bold text-primary">{c.translation}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
