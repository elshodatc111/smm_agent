import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Body, getJson, request, Result, ApiError } from './api'
import { useToast } from './toast'

export type NavItem = { label: string; url: string; icon: string; key: string }
export type Session = {
  brand: { name: string; brand_color: string; theme: string; logo: string }
  authenticated: boolean
  user?: { id: number; username: string; name: string; is_admin: boolean; theme: string }
  nav?: { title: string; items: NavItem[] }[]
  businesses?: { id: number; name: string }[]
  business?: { id: number; name: string } | null
  unread?: number
}

type Ctx = {
  session: Session
  refreshSession: () => Promise<void>
  /** POST yuboradi, natijani (yo'naltirilgan sahifani) keshga qo'yadi va kerak bo'lsa o'tadi. */
  submit: (path: string, body?: Body, o?: { stay?: boolean; method?: string }) => Promise<Result | null>
  busy: boolean
  theme: 'light' | 'dark'
  toggleTheme: () => void
  setBusiness: (id: number | null) => Promise<void>
}
const AppCtx = createContext<Ctx>(null as unknown as Ctx)
export const useApp = () => useContext(AppCtx)

const boot: any = (window as any).__BOOT__ || {}

function hexToRgb(h: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(h.trim())
  if (!m) return '225 29 46'
  const n = parseInt(m[1], 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}

export function applyBrand(b: Session['brand']) {
  const r = document.documentElement
  if (b.brand_color) r.style.setProperty('--c-brand', hexToRgb(b.brand_color))
  if (b.name) document.title = b.name
  const m = document.querySelector('meta[name=theme-color]')
  if (m && b.brand_color) m.setAttribute('content', b.brand_color)
}

export function useSessionQuery() {
  return useQuery<Session>({ queryKey: ['session'], queryFn: () => getJson('/api/v1/session/'), staleTime: 30_000, refetchOnWindowFocus: true,
    initialData: boot.brand ? ({ brand: boot.brand, authenticated: false, __boot: true } as any) : undefined, initialDataUpdatedAt: 0 })
}

export function AppProvider({ session, children }: { session: Session; children: ReactNode }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const loc = useLocation()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (document.documentElement.getAttribute('data-theme') as any) || 'light')

  useEffect(() => { applyBrand(session.brand) }, [session.brand])
  useEffect(() => {
    const t = session.user?.theme || localStorage.getItem('theme') || session.brand.theme || 'light'
    document.documentElement.setAttribute('data-theme', t)
    setTheme(t as any)
  }, [session.user?.theme, session.brand.theme])

  const refreshSession = useCallback(async () => { await qc.invalidateQueries({ queryKey: ['session'] }) }, [qc])

  const submit = useCallback<Ctx['submit']>(async (path, body, o) => {
    setBusy(true)
    try {
      const res = await request(path, { method: o?.method || 'POST', body })
      const d = res.data
      if (d && typeof d === 'object' && d.kind) {
        qc.setQueryData(['page', res.path], d)
        if (!o?.stay && res.path !== loc.pathname + loc.search) nav(res.path)
        else if (o?.stay) qc.invalidateQueries({ queryKey: ['page'] })
      } else if (res.status === 204 || typeof d === 'string') {
        qc.invalidateQueries({ queryKey: ['page'] })
      }
      qc.invalidateQueries({ queryKey: ['session'] })
      return res
    } catch (e) {
      const err = e as ApiError
      toast.push('error', err.message || 'Xato yuz berdi')
      return null
    } finally {
      setBusy(false)
    }
  }, [qc, nav, loc, toast])

  const toggleTheme = useCallback(() => {
    const t = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', t)
    try { localStorage.setItem('theme', t) } catch { /* ignore */ }
    setTheme(t)
    request('/mavzu/', { method: 'POST', body: { theme: t }, silent: true }).catch(() => {})
  }, [theme])

  const setBusiness = useCallback(async (id: number | null) => {
    await request('/biznes-tanlash/', { method: 'POST', body: { business: id ?? '' } })
    qc.invalidateQueries({ queryKey: ['page'] })
    await qc.invalidateQueries({ queryKey: ['session'] })
    nav('/')
  }, [qc, nav])

  return <AppCtx.Provider value={{ session, refreshSession, submit, busy, theme, toggleTheme, setBusiness }}>{children}</AppCtx.Provider>
}
