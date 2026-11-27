/** Safe localStorage wrappers (private mode / blocked storage never crash the app). */
export function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function save(key: string, value: unknown): void {
  try {
    if (value === undefined || value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* ignore */
  }
}

/** Invite code the app was opened with (?ref=<code>): sent once when a new account is created. */
export function captureRefCode(search: string): void {
  const code = new URLSearchParams(search).get('ref')
  if (code && /^[A-Za-z0-9]{1,12}$/.test(code)) save('wf.ref', code.toLowerCase())
}
export const refCode = (): string | undefined => load<string | null>('wf.ref', null) ?? undefined
