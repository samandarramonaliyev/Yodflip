import { load, save } from './storage'

/** All API calls are relative (/api/...): Django serves this app and the API on one origin. */
const API = '/api'

export interface Tokens {
  access: string
  refresh: string
}

let tokens: Tokens | null = load<Tokens | null>('wf.tokens', null)
let onLogout: (() => void) | null = null

export function setTokens(t: Tokens | null) {
  tokens = t
  save('wf.tokens', t)
}
export function getTokens() {
  return tokens
}
export function setLogoutHandler(fn: () => void) {
  onLogout = fn
}

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(status: number, data: unknown) {
    const detail =
      data && typeof data === 'object' && 'detail' in data ? String((data as { detail: unknown }).detail) : `HTTP ${status}`
    super(detail)
    this.status = status
    this.data = data
  }
}

let refreshing: Promise<boolean> | null = null

async function refresh(): Promise<boolean> {
  if (!tokens?.refresh) return false
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: tokens!.refresh }),
      })
      if (!r.ok) return false
      const data = await r.json()
      setTokens({ access: data.access, refresh: data.refresh || tokens!.refresh })
      return true
    } catch {
      return false
    } finally {
      setTimeout(() => (refreshing = null), 0)
    }
  })()
  return refreshing
}

type Query = Record<string, string | number | boolean | null | undefined>

function qs(query?: Query) {
  if (!query) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function request<T>(
  method: string,
  path: string,
  opts: { body?: unknown; query?: Query; form?: FormData; raw?: boolean; auth?: boolean } = {},
): Promise<T> {
  const doFetch = () => {
    const headers: Record<string, string> = {}
    if (opts.auth !== false && tokens?.access) headers.Authorization = `Bearer ${tokens.access}`
    let body: BodyInit | undefined
    if (opts.form) body = opts.form
    else if (opts.body !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(opts.body)
    }
    return fetch(`${API}${path}${qs(opts.query)}`, { method, headers, body })
  }
  let res: Response
  try {
    res = await doFetch()
  } catch {
    throw new ApiError(0, { detail: 'network_error' })
  }
  if (res.status === 401 && opts.auth !== false && tokens?.refresh) {
    if (await refresh()) res = await doFetch()
    else {
      setTokens(null)
      onLogout?.()
    }
  }
  if (opts.raw) {
    if (!res.ok) throw new ApiError(res.status, null)
    return res as unknown as T
  }
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text.slice(0, 200) }
  }
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

export const api = {
  request,
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  del: <T = null>(path: string, query?: Query) => request<T>('DELETE', path, { query }),
  form: <T>(path: string, form: FormData) => request<T>('POST', path, { form }),
  publicGet: <T>(path: string, query?: Query) => request<T>('GET', path, { query, auth: false }),
  publicPost: <T>(path: string, body?: unknown) => request<T>('POST', path, { body, auth: false }),
  download: async (path: string, filename: string) => {
    const res = await request<Response>('GET', path, { raw: true })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}

/** Map an error to an i18n key. */
export function errorKey(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return 'err.network'
    if (e.status === 429) return 'err.limit'
    if (e.status === 413) return 'err.too_large'
    if (e.status === 403) return 'err.forbidden'
    if (e.status === 404) return 'err.not_found'
    if (e.status >= 500) return 'err.server'
  }
  return 'err.generic'
}
