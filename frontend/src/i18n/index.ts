import { useCallback } from 'react'
import { useApp } from '../store/app'
import type { UiLang } from '../lib/types'
import en from './en.json'
import ru from './ru.json'
import uz from './uz.json'

export const dictionaries: Record<UiLang, Record<string, string>> = { uz, en, ru }

export type Vars = Record<string, string | number>

export function translate(lang: UiLang, key: string, vars?: Vars): string {
  let s = dictionaries[lang]?.[key] ?? dictionaries.en[key] ?? key
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
  return s
}

export function useT() {
  const lang = useApp((s) => s.lang)
  return useCallback((key: string, vars?: Vars) => translate(lang, key, vars), [lang])
}

export const LANG_NAMES: Record<UiLang, string> = { uz: "O'zbekcha", en: 'English', ru: 'Русский' }
