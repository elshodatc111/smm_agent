import { ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Bell, ChevronsLeft, ChevronsRight, LogOut, Menu, Moon, Plus, Search, Sun, X, CalendarDays, Cloud, BarChart3, ChevronDown, Check, Building2 } from 'lucide-react'
import { useApp } from '../lib/app'
import { cx } from '../lib/format'
import { Icon } from './icons'
import { Drawer } from './ui'

function Logo({ small }: { small?: boolean }) {
  const { session } = useApp()
  const b = session.brand
  return (
    <div className="flex items-center gap-2.5 min-w-0">
      {b.logo ? <img src={b.logo} alt="" className="w-8 h-8 rounded-lg object-contain bg-surface2 shrink-0" /> : <span className="w-8 h-8 rounded-lg bg-brand text-white grid place-items-center font-bold shrink-0">{(b.name || 'S')[0]}</span>}
      {!small && <span className="font-bold text-[15px] tracking-tight truncate">{b.name}</span>}
    </div>
  )
}

function NavList({ collapsed, onGo }: { collapsed?: boolean; onGo?: () => void }) {
  const { session } = useApp()
  const loc = useLocation()
  const full = loc.pathname + loc.search
  const active = (url: string) => (url === '/' ? loc.pathname === '/' : loc.pathname.startsWith(url) && !(url === '/kalendar/' && /^\/kalendar\/(yangi|savat)/.test(loc.pathname)) && !(url === '/tahlil/' && loc.pathname.startsWith('/tahlil/postlar')))
  const [shut, setShut] = useState<Record<string, boolean>>(() => { try { return JSON.parse(localStorage.getItem('navs') || '{"Tizim":true}') } catch { return { Tizim: true } } })
  const flip = (t: string) => setShut((x) => { const n = { ...x, [t]: !x[t] }; try { localStorage.setItem('navs', JSON.stringify(n)) } catch { /* ignore */ } return n })
  return (
    <nav className="flex-1 overflow-y-auto px-2.5 pb-3 space-y-2.5" aria-label="Asosiy menyu">
      {(session.nav || []).map((sec) => {
        const hasActive = sec.items.some((it) => active(it.url))
        const closed = !collapsed && !!shut[sec.title] && !hasActive
        return (
        <div key={sec.title}>
          {!collapsed && <button type="button" onClick={() => flip(sec.title)} className="w-full flex items-center justify-between px-2.5 pb-1 text-[10.5px] font-bold uppercase tracking-[.08em] text-muted/80 hover:text-fg">{sec.title}<ChevronDown className={cx('w-3.5 h-3.5 transition', closed && '-rotate-90')} /></button>}
          {collapsed && <div className="mx-2 my-1 border-t border-line first:hidden" />}
          <div className={cx('space-y-0.5', closed && 'hidden')}>
            {sec.items.map((it) => {
              const on = active(it.url)
              return (
                <NavLink key={it.url + it.label} to={it.url} onClick={onGo} title={collapsed ? it.label : undefined}
                  className={cx('flex items-center gap-2.5 rounded-lg px-2.5 h-8 text-[13.5px] font-medium transition', collapsed && 'justify-center px-0', on ? 'bg-brandsoft text-fg' : 'text-fg/75 hover:bg-surface2 hover:text-fg')}>
                  <span className={cx(on ? 'text-brand' : 'text-muted')}><Icon name={it.icon} /></span>
                  {!collapsed && <span className="truncate">{it.label}</span>}
                </NavLink>
              )
            })}
          </div>
        </div>
        )
      })}
    </nav>
  )
}

function BusinessSwitch() {
  const { session, setBusiness } = useApp()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const cur = session.business
  const items = session.businesses || []
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} className="btn max-w-[240px] sm:min-w-[190px] justify-between gap-2">
        <span className="flex items-center gap-2 min-w-0"><Building2 className="w-4 h-4 text-muted shrink-0" /><span className="truncate">{cur ? cur.name : 'Barcha bizneslar'}</span></span>
        <ChevronDown className="w-4 h-4 text-muted shrink-0" />
      </button>
      {open && (
        <div className="pop absolute left-0 top-[calc(100%+6px)] z-50 w-[270px] max-h-[60vh] overflow-auto card shadow-pop p-1.5">
          {[{ id: null as number | null, name: 'Barcha bizneslar' }, ...items].map((b) => (
            <button key={String(b.id)} onClick={() => { setOpen(false); setBusiness(b.id) }}
              className={cx('w-full flex items-center justify-between gap-2 px-2.5 h-9 rounded-md text-left text-[13.5px] hover:bg-surface2', (cur?.id ?? null) === b.id && 'bg-brandsoft font-semibold')}>
              <span className="truncate">{b.name}</span>{(cur?.id ?? null) === b.id && <Check className="w-4 h-4 text-brand" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SearchBox() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  return (
    <form className="relative hidden md:block flex-1 max-w-[380px]" onSubmit={(e) => { e.preventDefault(); if (q.trim()) nav('/qidiruv/?q=' + encodeURIComponent(q.trim())) }}>
      <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
      <input className="input pl-9 bg-surface2/70" type="search" placeholder="Qidiruv: post, fayl, g'oya…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Qidiruv" />
    </form>
  )
}

function InstallBtn() {
  const [ev, setEv] = useState<any>(null)
  useEffect(() => {
    const h = (e: any) => { e.preventDefault(); setEv(e) }
    window.addEventListener('beforeinstallprompt', h)
    return () => window.removeEventListener('beforeinstallprompt', h)
  }, [])
  if (!ev) return null
  return <button className="btn hidden lg:inline-flex" onClick={() => { ev.prompt(); ev.userChoice.finally(() => setEv(null)) }}>📲 O'rnatish</button>
}

export function Shell({ children }: { children: ReactNode }) {
  const { session, theme, toggleTheme, submit } = useApp()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('navc') === '1')
  const [menu, setMenu] = useState(false)
  const [user, setUser] = useState(false)
  const loc = useLocation()
  useEffect(() => { setMenu(false) }, [loc.pathname])
  const toggle = () => { setCollapsed(!collapsed); try { localStorage.setItem('navc', collapsed ? '0' : '1') } catch { /* ignore */ } }
  const unread = session.unread || 0
  const bottom = useMemo(() => [
    { to: '/kalendar/', label: 'Kalendar', I: CalendarDays },
    { to: '/cloudflare/', label: 'Fayllar', I: Cloud },
    { to: '/kalendar/yangi/', label: 'Yangi', I: Plus, main: true },
    { to: '/tahlil/', label: 'Tahlil', I: BarChart3 },
  ], [])
  return (
    <div className="h-full flex">
      <aside className={cx('hidden lg:flex flex-col shrink-0 bg-surface border-r border-line transition-[width] duration-200', collapsed ? 'w-[68px]' : 'w-[238px]')}>
        <div className={cx('h-[56px] flex items-center shrink-0', collapsed ? 'justify-center' : 'px-4')}><Link to="/"><Logo small={collapsed} /></Link></div>
        <NavList collapsed={collapsed} />
        <button onClick={toggle} className="h-10 border-t border-line flex items-center justify-center gap-2 text-muted hover:text-fg text-[12.5px]" title="Menyuni yig'ish">
          {collapsed ? <ChevronsRight className="w-4 h-4" /> : <><ChevronsLeft className="w-4 h-4" /> Yig'ish</>}
        </button>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-[56px] shrink-0 bg-surface/90 backdrop-blur border-b border-line flex items-center gap-2 px-3 lg:px-5 z-30">
          <button className="btn btn-icon btn-ghost lg:hidden" onClick={() => setMenu(true)} aria-label="Menyu"><Menu className="w-5 h-5" /></button>
          <Link to="/" className="lg:hidden"><Logo small /></Link>
          <BusinessSwitch />
          <SearchBox />
          <div className="flex-1" />
          <InstallBtn />
          {session.business && <Link to="/kalendar/yangi/" className="btn btn-primary hidden sm:inline-flex"><Plus className="w-4 h-4" /> Yangi kontent</Link>}
          <Link to="/bildirishnomalar/" className="btn btn-icon btn-ghost relative" title="Bildirishnomalar" aria-label="Bildirishnomalar">
            <Bell className="w-[18px] h-[18px]" />
            {unread > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[17px] h-[17px] px-1 rounded-full bg-brand text-white text-[10.5px] font-bold grid place-items-center">{unread > 99 ? '99+' : unread}</span>}
          </Link>
          <button className="btn btn-icon btn-ghost" onClick={toggleTheme} title="Qorong'u / yorug' mavzu" aria-label="Mavzu">{theme === 'dark' ? <Sun className="w-[18px] h-[18px]" /> : <Moon className="w-[18px] h-[18px]" />}</button>
          <div className="relative">
            <button className="btn btn-ghost px-1.5 gap-2" onClick={() => setUser(!user)} aria-label="Hisob">
              <span className="w-7 h-7 rounded-full bg-brandsoft text-brand grid place-items-center font-bold text-[12.5px]">{(session.user?.name || '?')[0]?.toUpperCase()}</span>
              <span className="hidden xl:block max-w-[140px] truncate">{session.user?.name}</span>
            </button>
            {user && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setUser(false)} />
                <div className="pop absolute right-0 top-[calc(100%+6px)] z-50 w-[220px] card shadow-pop p-1.5">
                  <div className="px-2.5 py-2 border-b border-line mb-1"><div className="font-semibold truncate">{session.user?.name}</div><div className="text-muted text-[12px]">{session.user?.is_admin ? 'Administrator' : session.user?.username}</div></div>
                  <button className="w-full flex items-center gap-2 px-2.5 h-9 rounded-md hover:bg-surface2 text-left" onClick={() => { setUser(false); submit('/chiqish/') }}><LogOut className="w-4 h-4" /> Chiqish</button>
                </div>
              </>
            )}
          </div>
        </header>
        <main className="flex-1 min-h-0 overflow-y-auto overscroll-contain" id="main">
          <div className="px-3 sm:px-4 lg:px-5 py-4 pb-24 lg:pb-6 max-w-[1560px] mx-auto">{children}</div>
        </main>
        <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur border-t border-line grid grid-cols-5 safe-b" aria-label="Tezkor menyu">
          {bottom.map(({ to, label, I, main }) => {
            const on = loc.pathname.startsWith(to) && !(to === '/kalendar/' && loc.pathname.startsWith('/kalendar/yangi'))
            return (
              <Link key={to} to={to} className={cx('flex flex-col items-center justify-center gap-0.5 h-[58px] text-[10.5px] font-medium', on ? 'text-brand' : 'text-muted')}>
                {main ? <span className="w-11 h-11 -mt-5 rounded-full bg-brand text-white grid place-items-center shadow-pop"><I className="w-6 h-6" /></span> : <I className="w-5 h-5" />}
                {!main && label}
              </Link>
            )
          })}
          <button onClick={() => setMenu(true)} className="flex flex-col items-center justify-center gap-0.5 h-[58px] text-[10.5px] font-medium text-muted"><Menu className="w-5 h-5" />Menyu</button>
        </nav>
      </div>

      <Drawer open={menu} onClose={() => setMenu(false)} side="left" width={300} title={<Logo />}>
        <div className="-mx-3 -my-3 h-full flex flex-col"><NavList onGo={() => setMenu(false)} /></div>
      </Drawer>
    </div>
  )
}
