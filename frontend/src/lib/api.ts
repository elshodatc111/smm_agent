/** Django bilan aloqa: JSON GET/POST, CSRF, yo'naltirishni kuzatish va bir martalik xabarlar (flash). */
export type Msg = { level: string; text: string }
export class ApiError extends Error {
  status: number
  data: any
  constructor(status: number, message: string, data?: any) {
    super(message)
    this.status = status
    this.data = data
  }
}

type Listener = (m: Msg[]) => void
const listeners = new Set<Listener>()
export const onMessages = (fn: Listener) => {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}
const emit = (m: Msg[]) => m.length && listeners.forEach((l) => l(m))

export function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export type Result = { data: any; path: string; status: number; redirected: boolean }

export type Body = FormData | URLSearchParams | Record<string, any> | null | undefined

function toBody(body: Body): BodyInit | undefined {
  if (!body) return undefined
  if (body instanceof FormData || body instanceof URLSearchParams) return body
  const p = new URLSearchParams()
  Object.entries(body).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)))
    else if (v !== undefined && v !== null) p.append(k, typeof v === 'boolean' ? (v ? 'on' : '') : String(v))
  })
  return p
}

export async function request(path: string, opts: { method?: string; body?: Body; signal?: AbortSignal; silent?: boolean } = {}): Promise<Result> {
  const method = opts.method || 'GET'
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Requested-With': 'fetch' }
  if (method !== 'GET') headers['X-CSRFToken'] = csrfToken()
  const res = await fetch(path, { method, headers, body: toBody(opts.body), credentials: 'same-origin', redirect: 'follow', signal: opts.signal })
  const ct = res.headers.get('content-type') || ''
  let data: any = null
  if (ct.includes('json')) data = await res.json().catch(() => null)
  else if (res.status !== 204) data = await res.text().catch(() => '')
  if (data && Array.isArray(data.messages) && !opts.silent) emit(data.messages)
  const u = new URL(res.url, location.origin)
  const final = u.pathname + u.search
  if (!res.ok) {
    const msg = (data && (data.detail || data.title || data.error)) || `Server xatosi (${res.status})`
    throw new ApiError(res.status, msg, data)
  }
  return { data, path: final, status: res.status, redirected: res.redirected }
}

export const getJson = async (path: string, signal?: AbortSignal) => (await request(path, { signal })).data
export const postJson = async (path: string, body?: Body) => request(path, { method: 'POST', body })

/** Server manzili React sahifasimi (true) yoki fayl/yuklab olish/tashqi manzilmi (false). */
export function isAppPath(url: string): boolean {
  if (!url || !url.startsWith('/') || url.startsWith('//')) return false
  const p = url.split('?')[0]
  if (/^\/(static|media|api|h|brend|sw\.js|manifest|oflayn|admin)\b/.test(p)) return false
  if (/\/fayl\/(pdf|xlsx)?\/?$/.test(p) && !/\/fayl\/\d+/.test(p)) return false
  if (/^\/cloudflare\/\d+\/fayl\/$/.test(p)) return false
  if (/^\/kalendar\/\d+\/media\/\d+\/$/.test(p)) return false
  if (/^\/hisobotlar\/\d+\/(fayl\/\w+|korinish)\/$/.test(p)) return false
  if (/[?&]csv=1/.test(url)) return false
  return true
}
export const appUrl = (p: string) => '/app' + p
