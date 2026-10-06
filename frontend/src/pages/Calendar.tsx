import { useMemo, useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight, List, Plus, Zap, Image as Img, Video } from 'lucide-react'
import { Badge, Btn, Card, Drawer, Empty, PageHeader, Segmented } from '../components/ui'
import { A } from '../components/Blocks'
import { useApp } from '../lib/app'
import { request } from '../lib/api'
import { useToast } from '../lib/toast'
import { cx, monthName, statusTone, FMT } from '../lib/format'

type Item = { id: number; title: string; status: string; status_label: string; format: string; type: string; platforms: string[]; rule: string; time: string; when: string; thumb: string; business?: string }
const WD = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya']
const DOT: Record<string, string> = { published: 'bg-ok', scheduled: 'bg-info', failed: 'bg-bad', draft: 'bg-muted', publishing: 'bg-warn' }
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function Chip({ it, drag, onDragStart }: { it: Item; drag?: boolean; onDragStart?: (e: React.DragEvent) => void }) {
  return (
    <Link to={`/kalendar/${it.id}/`} draggable={drag} onDragStart={onDragStart} onClick={(e) => e.stopPropagation()} title={`${it.title} · ${it.status_label}`}
      className="flex items-center gap-1 rounded-md px-1.5 py-[3px] text-[11.5px] leading-tight bg-surface2 hover:bg-brandsoft border border-line/70 truncate">
      <i className={cx('w-1.5 h-1.5 rounded-full shrink-0', DOT[it.status] || 'bg-muted')} />
      <span className="text-muted shrink-0">{it.time}</span>
      <span className="truncate font-medium">{it.title}</span>
    </Link>
  )
}

function Row({ it }: { it: Item }) {
  return (
    <Link to={`/kalendar/${it.id}/`} className="flex items-center gap-3 p-2.5 rounded-lg border border-line bg-surface hover:border-brand/50 transition">
      <div className="w-12 h-12 rounded-lg bg-surface2 overflow-hidden shrink-0 grid place-items-center text-muted">
        {it.thumb ? <img src={it.thumb} alt="" className="w-full h-full object-cover" /> : it.type === 'video' || it.type === 'reel' || it.type === 'short' ? <Video className="w-5 h-5" /> : <Img className="w-5 h-5" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-medium text-[13.5px] truncate">{it.title}</div>
        <div className="text-[12px] text-muted truncate">{it.when || 'Vaqt belgilanmagan'} · {it.format} · {it.platforms.join(' ') || '—'}{it.business ? ` · ${it.business}` : ''}</div>
      </div>
      <Badge tone={statusTone(it.status)}>{it.status_label}</Badge>
    </Link>
  )
}

export function Calendar({ d }: { d: any }) {
  const nav = useNavigate()
  const loc = useLocation()
  const qc = useQueryClient()
  const toast = useToast()
  const { submit, busy } = useApp()
  const [view, setView] = useState<'month' | 'list'>('month')
  const [day, setDay] = useState<string | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const days: Record<string, Item[]> = d.days
  const [y, m] = d.month.split('-').map(Number)

  const cells = useMemo(() => {
    const first = new Date(y, m - 1, 1)
    const lead = (first.getDay() + 6) % 7
    const n = new Date(y, m, 0).getDate()
    const total = Math.ceil((lead + n) / 7) * 7
    return Array.from({ length: total }, (_, i) => { const dt = new Date(y, m - 1, 1 - lead + i); return { key: iso(dt), n: dt.getDate(), in: dt.getMonth() === m - 1 } })
  }, [y, m])

  const q = (patch: Record<string, string>) => {
    const p = new URLSearchParams(loc.search)
    Object.entries(patch).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)))
    const s = p.toString()
    return `/kalendar/${s ? '?' + s : ''}`
  }
  const setF = (k: string, v: string) => nav(q({ [k]: v }))

  const onDrop = async (e: React.DragEvent, date: string) => {
    e.preventDefault(); setOver(null)
    const id = e.dataTransfer.getData('text/plain')
    if (!id || !d.can_move) return
    try {
      const r = await request(`/kalendar/${id}/koch/`, { method: 'POST', body: { date } })
      toast.push('success', `Ko'chirildi: ${r.data.when}${r.data.note ? ' — ' + r.data.note : ''}`)
      qc.invalidateQueries({ queryKey: ['page'] })
    } catch (err: any) { toast.push('error', err.message) }
  }
  const dayItems = day ? days[day] || [] : []
  const addUrl = (date: string) => `/kalendar/yangi/?date=${date}`
  const selCls = 'input h-8 w-auto text-[12.5px] pr-7'

  return (
    <div>
      <PageHeader title="Kalendar" subtitle={`${monthName(d.month)} · ${d.list.length} ta post`}
        actions={<>
          <Segmented items={[{ key: 'month', label: <><CalendarDays className="w-3.5 h-3.5" /> Oy</> }, { key: 'list', label: <><List className="w-3.5 h-3.5" /> Ro'yxat</> }]} value={view} onChange={setView} />
          {d.can_create && <Link to={`/kalendar/yangi/`} className="btn btn-primary"><Plus className="w-4 h-4" /> Yangi kontent</Link>}
        </>} />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="inline-flex items-center rounded-lg border border-line bg-surface">
          <Link to={q({ m: d.prev })} className="btn-icon btn btn-ghost" aria-label="Oldingi oy"><ChevronLeft className="w-4 h-4" /></Link>
          <Link to={q({ m: '' })} className="px-3 text-[13px] font-semibold min-w-[130px] text-center">{monthName(d.month)}</Link>
          <Link to={q({ m: d.next })} className="btn-icon btn btn-ghost" aria-label="Keyingi oy"><ChevronRight className="w-4 h-4" /></Link>
        </div>
        <select className={selCls} value={d.f.status} onChange={(e) => setF('status', e.target.value)} aria-label="Holat"><option value="">Barcha holatlar</option>{d.statuses.map(([k, v]: [string, string]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className={selCls} value={d.f.p} onChange={(e) => setF('p', e.target.value)} aria-label="Platforma"><option value="">Barcha platformalar</option><option value="telegram">Telegram</option><option value="instagram">Instagram</option><option value="youtube">YouTube</option></select>
        <select className={selCls} value={d.f.f} onChange={(e) => setF('f', e.target.value)} aria-label="Format"><option value="">Barcha formatlar</option>{Object.entries(FMT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        {(d.f.status || d.f.p || d.f.f) && <Link to={q({ status: '', p: '', f: '' })} className="text-[12.5px] text-muted hover:text-fg underline">Tozalash</Link>}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-3 items-start">
        <div>
          {view === 'month' ? (
            <>
              {/* Desktop: oy to'ri */}
              <div className="hidden md:block card overflow-hidden">
                <div className="grid grid-cols-7 border-b border-line bg-surface2/60">{WD.map((w) => <div key={w} className="px-2 py-1.5 text-[11.5px] font-semibold text-muted text-center">{w}</div>)}</div>
                <div className="grid grid-cols-7" style={{ gridAutoRows: 'minmax(94px, calc((100vh - 290px) / 6))' }}>
                  {cells.map((c, i) => {
                    const its = days[c.key] || []
                    return (
                      <div key={c.key} onClick={() => setDay(c.key)} onDragOver={(e) => { if (d.can_move) { e.preventDefault(); setOver(c.key) } }} onDragLeave={() => setOver(null)} onDrop={(e) => onDrop(e, c.key)}
                        className={cx('group p-1 border-b border-r border-line/70 cursor-pointer transition overflow-hidden', (i + 1) % 7 === 0 && 'border-r-0', !c.in && 'bg-surface2/40', over === c.key && 'bg-brandsoft', 'hover:bg-surface2/70')}>
                        <div className="flex items-center justify-between px-0.5">
                          <span className={cx('text-[12px] w-6 h-6 grid place-items-center rounded-full', c.key === d.today ? 'bg-brand text-white font-bold' : c.in ? 'font-medium' : 'text-muted')}>{c.n}</span>
                          {d.can_create && c.in && <Link to={addUrl(c.key)} onClick={(e) => e.stopPropagation()} aria-label="Post qo'shish" className="opacity-0 group-hover:opacity-100 w-5 h-5 grid place-items-center text-muted hover:text-brand"><Plus className="w-3.5 h-3.5" /></Link>}
                        </div>
                        <div className="space-y-[3px] mt-0.5">
                          {its.slice(0, 3).map((it) => <Chip key={it.id} it={it} drag={d.can_move && !['published', 'publishing'].includes(it.status)} onDragStart={(e) => e.dataTransfer.setData('text/plain', String(it.id))} />)}
                          {its.length > 3 && <div className="text-[11px] text-muted px-1">+{its.length - 3} ta yana</div>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
              {/* Mobil: kunlar bo'yicha ro'yxat */}
              <div className="md:hidden space-y-3">
                {Object.keys(days).sort().length === 0 && <Card><Empty text="Bu oyda rejalashtirilgan post yo'q." action={d.can_create ? <Link to="/kalendar/yangi/" className="btn btn-primary">Yangi kontent</Link> : undefined} /></Card>}
                {Object.keys(days).sort().map((k) => (
                  <div key={k}>
                    <div className="text-[12px] font-semibold text-muted mb-1.5 px-0.5">{new Date(k + 'T00:00').toLocaleDateString('uz-UZ', { day: 'numeric', month: 'long', weekday: 'short' })}{k === d.today ? ' · bugun' : ''}</div>
                    <div className="space-y-1.5">{days[k].map((it) => <Row key={it.id} it={it} />)}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="space-y-1.5">{d.list.length ? d.list.map((it: Item) => <Row key={it.id} it={it} />) : <Card><Empty text="Bu oyda rejalashtirilgan post yo'q." /></Card>}</div>
          )}
        </div>

        <Card title={`Qoralamalar (${d.unscheduled.length})`} bodyClass="space-y-1.5 max-h-[calc(100vh-250px)] overflow-y-auto"
          actions={d.can_autotime ? <Btn size="sm" loading={busy} onClick={() => submit('/kalendar/avto-vaqt/')}><Zap className="w-3.5 h-3.5" /> Vaqt qo'yish</Btn> : undefined}>
          {d.unscheduled.length ? d.unscheduled.map((it: Item) => <Row key={it.id} it={it} />) : <Empty text="Vaqti belgilanmagan post yo'q." />}
        </Card>
      </div>

      <Drawer open={!!day} onClose={() => setDay(null)} title={day ? new Date(day + 'T00:00').toLocaleDateString('uz-UZ', { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' }) : ''}
        footer={day && d.can_create ? <A to={addUrl(day)} className="btn btn-primary"><Plus className="w-4 h-4" /> Shu kunga post qo'shish</A> : undefined}>
        <div className="space-y-2">{dayItems.length ? dayItems.map((it) => <Row key={it.id} it={it} />) : <Empty text="Bu kunda post yo'q." />}</div>
      </Drawer>
    </div>
  )
}
