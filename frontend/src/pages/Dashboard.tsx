import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, CalendarClock, Eye, FileText, Plus, TrendingUp, Users, Heart, Send, Building2, ChevronRight } from 'lucide-react'
import { Badge, Card, Empty, PageHeader, PlatDot, Segmented, Stat, Progress } from '../components/ui'
import { Chart } from '../components/Charts'
import { A } from '../components/Blocks'
import { useApp } from '../lib/app'
import { cx, delta, fmtDate, FMT, nf, PLAT, pct } from '../lib/format'

type Acc = { id: number; name: string; handle: string; platform: string; platform_label: string; status: string; status_label: string; error: string; last_collect: string; followers: number; followers_delta: number; views: number; views_delta: number | null; er: number | null; posts: number; posts_total: number; scheduled: number; likes: number; comments: number }

function Trend({ v, suffix = '%' }: { v: number | null | undefined; suffix?: string }) {
  if (v === null || v === undefined) return null
  const up = v >= 0
  return <span className={cx('inline-flex items-center gap-0.5 font-semibold', up ? 'text-ok' : 'text-bad')}>{up ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}{delta(v, suffix)}</span>
}

function Mini({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted font-medium truncate">{label}</div>
      <div className="font-bold text-[16px] leading-tight truncate">{value}</div>
      {sub !== undefined && <div className="text-[11px] min-h-[14px]">{sub}</div>}
    </div>
  )
}

export function AccountCard({ a }: { a: Acc }) {
  const bad = a.status === 'error'
  return (
    <Link to={`/ulanishlar/${a.id}/`} className="card p-3.5 block hover:border-brand/50 hover:shadow-pop transition group">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-8 h-8 rounded-lg grid place-items-center text-white text-[11px] font-bold shrink-0" style={{ background: PLAT[a.platform]?.color || '#64748b' }}>{PLAT[a.platform]?.short || '?'}</span>
          <div className="min-w-0"><div className="font-semibold truncate leading-tight">{a.name}</div><div className="text-[11.5px] text-muted truncate">{a.handle ? '@' + a.handle.replace(/^@/, '') : a.platform_label}</div></div>
        </div>
        <Badge tone={a.status === 'active' ? 'ok' : bad ? 'bad' : 'warn'}>{a.status_label}</Badge>
      </div>
      <div className="grid grid-cols-5 gap-2 mt-3">
        <Mini label="Obunachi" value={nf(a.followers)} sub={<Trend v={a.followers_delta} suffix="" />} />
        <Mini label="Ko'rish" value={nf(a.views)} sub={<Trend v={a.views_delta} />} />
        <Mini label="ER" value={a.er === null ? '—' : pct(a.er, 1)} />
        <Mini label="Postlar" value={a.posts} sub={<span className="text-muted">jami {a.posts_total}</span>} />
        <Mini label="Rejada" value={<span className={a.scheduled ? 'text-info' : ''}>{a.scheduled}</span>} sub={<span className="text-muted">kutmoqda</span>} />
      </div>
      {bad && a.error && <div className="mt-2 text-[12px] text-bad flex gap-1.5"><AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" /><span className="line-clamp-2">{a.error}</span></div>}
      {!bad && a.last_collect && <div className="mt-2 text-[11px] text-muted">Oxirgi yig'ish: {a.last_collect}</div>}
    </Link>
  )
}

export function Dashboard({ d }: { d: any }) {
  const [tab, setTab] = useState<'top' | 'worst' | 'types'>('top')
  const k = d.kpi
  const series = d.series.length > 1 ? { kind: 'line' as const, labels: d.series.map((x: any) => x.date.slice(5)), series: [{ name: 'Obunachi', data: d.series.map((x: any) => x.followers) }] } : null
  const types = d.types.length ? { kind: 'bar' as const, labels: d.types.map((t: any) => FMT[t.type] || t.type), series: [{ name: 'ER %', data: d.types.map((t: any) => t.er) }] } : null
  return (
    <>
      <PageHeader title={d.business.name} subtitle="Oxirgi 30 kun · avvalgi davr bilan solishtirish"
        actions={<Link to="/kalendar/yangi/" className="btn btn-primary"><Plus className="w-4 h-4" /> Yangi kontent</Link>} />
      {d.imports.map((j: any) => (
        <Card key={j.id} className="mb-3"><div className="flex items-center justify-between mb-2"><b>Tarixiy import bajarilmoqda</b><span className="text-muted text-[12.5px]">{j.status}</span></div><Progress value={j.progress} /></Card>
      ))}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Stat label="Obunachilar" icon={<Users className="w-4 h-4" />} value={nf(k.followers)} sub={<Trend v={k.followers_delta} suffix="" />} />
        <Stat label="Ko'rishlar" icon={<Eye className="w-4 h-4" />} value={nf(k.views)} sub={<Trend v={k.views_delta} />} />
        <Stat label="O'rtacha ER" icon={<Heart className="w-4 h-4" />} value={k.er === null ? '—' : pct(k.er, 2)} sub="jalb qilish darajasi" />
        <Stat label="Postlar" icon={<FileText className="w-4 h-4" />} value={k.posts} sub={`${d.per_week} ta / hafta`} />
        <Stat label="Rejalashtirilgan" icon={<CalendarClock className="w-4 h-4" />} value={d.accounts.reduce((s: number, a: Acc) => s + a.scheduled, 0)} sub="kutayotgan postlar" />
      </div>

      <h2 className="font-semibold mt-5 mb-2 flex items-center gap-2"><Send className="w-4 h-4 text-muted" /> Ulanishlar bo'yicha statistika <span className="text-muted font-normal text-[12.5px]">· har bir akkaunt alohida</span></h2>
      {d.accounts.length ? (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">{d.accounts.map((a: Acc) => <AccountCard key={a.id} a={a} />)}</div>
      ) : <Card><Empty text={<>Ulanish yo'q. <A to="/ulanishlar/" className="text-info underline">Ulanishlar</A> bo'limidan Telegram, Instagram yoki YouTube ni ulang.</>} /></Card>}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 mt-4">
        <Card title="Obunachilar dinamikasi" className="lg:col-span-7">
          {series ? <Chart spec={series} height={210} /> : <Empty text="Dinamika uchun kamida 2 kunlik ma'lumot kerak." icon={<TrendingUp className="w-8 h-8 opacity-50" />} />}
        </Card>
        <Card title="Yaqin kontent" className="lg:col-span-5" actions={<Link to="/kalendar/" className="text-[12.5px] text-info hover:underline">Kalendar</Link>}>
          {d.upcoming.length ? (
            <ul className="divide-y divide-line -my-1">
              {d.upcoming.map((i: any) => (
                <li key={i.id}><Link to={`/kalendar/${i.id}/`} className="flex items-center justify-between gap-3 py-2 hover:text-brand">
                  <span className="truncate font-medium">{i.title}</span>
                  <span className="text-[12px] text-muted whitespace-nowrap">{fmtDate(i.at)} <Badge className="ml-1">{i.status}</Badge></span>
                </Link></li>
              ))}
            </ul>
          ) : <Empty text={<>Rejalashtirilgan kontent yo'q. <A to="/studiya/" className="text-info underline">AI bilan oylik reja tuzing</A>.</>} />}
        </Card>
      </div>

      <Card className="mt-3" title="Postlar natijasi" actions={<Segmented value={tab} onChange={setTab} items={[{ key: 'top', label: 'Eng yaxshi' }, { key: 'worst', label: 'Eng past' }, { key: 'types', label: 'Format bo\'yicha ER' }]} />}>
        {tab === 'types' ? (types ? <Chart spec={types} height={200} /> : <Empty text="Hali ma'lumot yig'ilmagan." />) : (
          (tab === 'top' ? d.top : d.worst).length ? (
            <ul className="divide-y divide-line -my-1.5">
              {(tab === 'top' ? d.top : d.worst).map((p: any) => (
                <li key={p.id}><Link to={`/tahlil/post/${p.id}/`} className="flex items-center gap-3 py-2 hover:text-brand">
                  <PlatDot p={p.platform} /><span className="truncate flex-1">{p.text || '(matnsiz)'}</span>
                  <span className="text-[12px] text-muted hidden sm:block">{nf(p.views)} ko'rish</span>
                  <Badge tone={tab === 'top' ? 'ok' : 'warn'}>ER {pct(p.er, 2)}</Badge><ChevronRight className="w-4 h-4 text-muted" />
                </Link></li>
              ))}
            </ul>
          ) : <Empty text="Ma'lumot yo'q" />
        )}
      </Card>
    </>
  )
}

export function DashboardAll({ d }: { d: any }) {
  const { setBusiness } = useApp()
  return (
    <>
      <PageHeader title="Barcha bizneslar" subtitle="Oxirgi 30 kun · biznesni tanlab chuqur ko'ring" />
      {d.rows.length === 0 ? <Card><Empty text="Hali biznes qo'shilmagan." action={<Link to="/bizneslar/yangi/" className="btn btn-primary">Biznes qo'shish</Link>} /></Card> : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {d.rows.map((r: any) => (
            <button key={r.id} onClick={() => setBusiness(r.id)} className="card p-4 text-left hover:border-brand/50 hover:shadow-pop transition">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0"><span className="w-9 h-9 rounded-lg bg-brandsoft text-brand grid place-items-center shrink-0"><Building2 className="w-[18px] h-[18px]" /></span><span className="font-bold text-[15px] truncate">{r.name}</span></div>
                <ChevronRight className="w-4 h-4 text-muted" />
              </div>
              <div className="grid grid-cols-4 gap-2 mt-3.5">
                <Mini label="Obunachi" value={nf(r.kpi.followers)} sub={<Trend v={r.kpi.followers_delta} suffix="" />} />
                <Mini label="Ko'rish" value={nf(r.kpi.views)} sub={<Trend v={r.kpi.views_delta} />} />
                <Mini label="Postlar" value={r.kpi.posts} sub={<span className="text-muted">ER {r.kpi.er === null ? '—' : pct(r.kpi.er, 1)}</span>} />
                <Mini label="Rejada" value={<span className={r.scheduled ? 'text-info' : ''}>{r.scheduled}</span>} sub={<span className="text-muted">{r.accounts} ulanish</span>} />
              </div>
              {r.problems.length > 0 && <div className="mt-3 text-[12px] text-bad flex items-start gap-1.5"><AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" /><span>{r.problems.map((p: any) => `${p.name} (${p.status})`).join(', ')}</span></div>}
            </button>
          ))}
        </div>
      )}
    </>
  )
}
