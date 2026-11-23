import { useT } from '../i18n'
import { speakIn, useTts } from '../lib/tts'
import { Segmented, Toggle } from './ui'

/** Pronunciation: voices, speed, auto-play (kept on this device). */
export function TtsSettings() {
  const t = useT()
  const { de, en, speed, auto, set } = useTts()
  return (
    <div className="space-y-3 border-t border-line pt-4" data-testid="tts-settings">
      <div className="font-bold">🔊 {t('tts.title')}</div>
      <div>
        <div className="mb-1 text-sm text-muted">{t('tts.de_voice')}</div>
        <Segmented
          value={de}
          onChange={(v: 'female' | 'male') => {
            set({ de: v })
            void speakIn('der Bahnhof', 'de')
          }}
          options={[
            { value: 'female', label: t('tts.female') },
            { value: 'male', label: t('tts.male') },
          ]}
        />
      </div>
      <div>
        <div className="mb-1 text-sm text-muted">{t('tts.en_accent')}</div>
        <Segmented
          value={en}
          onChange={(v: 'us' | 'uk') => {
            set({ en: v })
            void speakIn('water', 'en')
          }}
          options={[
            { value: 'us', label: '🇺🇸 US' },
            { value: 'uk', label: '🇬🇧 UK' },
          ]}
        />
      </div>
      <div>
        <div className="mb-1 text-sm text-muted">{t('tts.speed')}</div>
        <Segmented value={String(speed)} onChange={(v) => set({ speed: Number(v) })} options={['0.8', '1', '1.2'].map((v) => ({ value: v, label: `${v}×` }))} />
      </div>
      <Toggle checked={auto} onChange={(v) => set({ auto: v })} label={t('tts.auto')} />
    </div>
  )
}
