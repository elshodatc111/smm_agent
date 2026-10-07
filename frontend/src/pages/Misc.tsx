import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle, Bell, Check, ChevronLeft, ChevronRight, Cpu, HardDrive, MemoryStick, Clock, Sparkles, Search, Download, FileSearch, ExternalLink, Heart, MessageCircle, Share2, Bookmark, Eye } from 'lucide-react'
import { Badge, Btn, Card, Empty, PageHeader, PlatDot, Progress, Segmented, Stat, Spinner } from '../components/ui'
import { A, DataTable, Rich } from '../components/Blocks'
import { Chart } from '../components/Charts'
import { useApp } from '../lib/app'
import { cx, fmtDate, fmtShort, FMT, nf, PLAT, pct } from '../lib/format'
import { Field } from '../components/Fields'



export function Pager({ pager }: { pager: { n: number; pages: number; count: number } }) {
  const nav = useNavigate()
  const loc = useLocation()
  if (!pager || pager.pages <= 1) return null
  const go = (n: number) => { const p = new URLSearchParams(loc.search); p.set('p', String(n)); nav(loc.pathname + '?' + p.toString()) }
  return (
    <div className="flex items-center justify-center gap-3 mt-3">
      <Btn size="sm" disabled={pager.n <= 1} onClick={() => go(pager.n - 1)}><ChevronLeft className="w-4 h-4" /></Btn>
      <span className="text-muted text-[13px]">{pager.n} / {pager.pages} <span className="opacity-70">· {pager.count} ta</span></span>
      <Btn size="sm" disabled={pager.n >= pager.pages} onClick={() => go(pager.n + 1)}><ChevronRight className="w-4 h-4" /></Btn>
    </div>
  )
}

/* ---------- Bildirishnomalar ---------- */
export function Notifications({ d }: { d: any }) {
  const { submit } = useApp()
  const [prefs, setPrefs] = useState<Record<string, { web: boolean; telegram: boolean }>>(() => Object.fromEntries(d.types.map((t: any) => [t.key, { web: t.web, telegram: t.telegram }])))
  const [tab, setTab] = useState<'list' | 'prefs'>('list')
  const save = async () => {
    const fd = new FormData()
    Object.entries(prefs).forEach(([k, v]) => { if (v.web) fd.append(`web_${k}`, 'on'); if (v.telegram) fd.append(`tg_${k}`, 'on') })
    await submit('/bildirishnomalar/sozlash/', fd, { stay: true })
  }
  const tone = (s: string) => (s === 'critical' ? 'bad' : s === 'warn' ? 'warn' : 'blue')
  const lbl = (s: string) => ({ critical: 'Jiddiy', warn: 'Ogohlantirish', info: "Ma'lumot" } as any)[s] || s
  return (
    <>
      <PageHeader title="Bildirishnomalar" actions={<><Segmented value={tab} onChange={setTab} items={[{ key: 'list', label: 'Ro\'yxat' }, { key: 'prefs', label: 'Sozlama' }]} />{tab === 'list' && <Btn onClick={() => submit('/bildirishnomalar/')}><Check className="w-4 h-4" /> Hammasini o'qilgan</Btn>}</>} />
      {tab === 'list' ? (
        <Card pad={false}>
          {d.items.length === 0 ? <Empty text="Bildirishnoma yo'q." icon={<Bell className="w-8 h-8 opacity-50" />} /> : (
            <ul className="divide-y divide-line">
              {d.items.map((n: any) => (
                <li key={n.id} className={cx('flex items-start gap-3 px-4 py-3', !n.read && 'bg-brandsoft/40')}>
                  <Badge tone={tone(n.severity)} className="mt-0.5 shrink-0">{lbl(n.severity)}</Badge>
                  <div className="min-w-0 flex-1">
                    <div className={cx('leading-snug', !n.read && 'font-semibold')}>{n.link ? <A to={n.link} className="hover:text-brand hover:underline">{n.title}</A> : n.title}</div>
                    {n.body && <div className="text-muted text-[12.5px] mt-0.5 whitespace-pre-line">{n.body}</div>}
                  </div>
                  <span className="text-[12px] text-muted whitespace-nowrap">{fmtShort(n.at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : (
        <Card title="Qaysi bildirishnomani qayerda olish">
          <div className="overflow-x-auto -mx-4">
            <table className="w-full text-[13.5px] min-w-[420px]">
              <thead><tr><th className="th">Tur</th><th className="th text-center">Platforma</th><th className="th text-center">Telegram</th></tr></thead>
              <tbody>{d.types.map((t: any) => (
                <tr key={t.key}><td className="td">{t.label}</td>
                  {(['web', 'telegram'] as const).map((c) => <td key={c} className="td text-center"><input type="checkbox" className="w-4 h-4 accent-[var(--brand)]" checked={prefs[t.key][c]} onChange={(e) => setPrefs({ ...prefs, [t.key]: { ...prefs[t.key], [c]: e.target.checked } })} /></td>)}
                </tr>))}</tbody>
            </table>
          </div>
          <p className="help">Telegram uchun profilingizda Telegram ID bog'langan bo'lishi kerak (admin «Foydalanuvchilar» bo'limida kiritadi).</p>
          <Btn variant="primary" className="mt-3" onClick={save}>Saqlash</Btn>
        </Card>
      )}
      {tab === 'list' && <Pager pager={d.pager} />}
    </>
  )
}

/* ---------- Audit va faoliyat ---------- */
export function Audit({ d }: { d: any }) {
  const nav = useNavigate()
  const [q, setQ] = useState(d.q)
  return (
    <>
      <PageHeader title="Audit jurnali" subtitle="Faqat qo'shiladi: o'zgartirib yoki o'chirib bo'lmaydi" actions={
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); nav('/audit/?q=' + encodeURIComponent(q)) }}><input className="input w-[200px]" placeholder="Amal bo'yicha qidirish" value={q} onChange={(e) => setQ(e.target.value)} /><Btn type="submit"><Search className="w-4 h-4" /></Btn></form>} />
      <DataTable columns={['Vaqt', 'Foydalanuvchi', 'Amal', 'Obyekt', 'Tafsilot']} rows={d.rows.map((r: any) => [fmtDate(r.at), r.user, r.action, r.target || '—', r.detail || '—'])} empty="Yozuv topilmadi." />
      <Pager pager={d.pager} />
    </>
  )
}

export function Activity({ d }: { d: any }) {
  const nav = useNavigate()
  const [f, setF] = useState(d.f)
  const apply = (e?: React.FormEvent) => { e?.preventDefault(); const p = new URLSearchParams(); Object.entries(f).forEach(([k, v]) => v && p.set(k, String(v))); nav('/faoliyat/?' + p.toString()) }
  const sel = (k: string, opts: [string, string][], ph: string) => (
    <select className="input w-auto min-w-[140px]" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}><option value="">{ph}</option>{opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
  )
  return (
    <>
      <PageHeader title="Faoliyat jurnali" subtitle="Har bir xodim qachon nima qilgani shu yerda saqlanadi. Har kuni ertalab «kecha kim nima qildi» xulosasi adminga Telegram orqali ham boradi." />
      <Card className="mb-3" bodyClass="!p-3">
        <form onSubmit={apply} className="flex flex-wrap gap-2 items-center">
          {sel('user', d.users.map((u: any) => [String(u.id), u.name]), 'Barcha xodimlar')}
          {sel('action', d.groups.map((g: any) => [g.key, g.label]), 'Barcha amallar')}
          <input type="date" className="input w-auto" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} />
          <input type="date" className="input w-auto" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} />
          <Btn variant="primary" type="submit">Saralash</Btn><Btn onClick={() => nav('/faoliyat/')}>Tozalash</Btn>
        </form>
      </Card>
      <DataTable columns={['Vaqt', 'Xodim', 'Nima qildi', 'Tafsilot']} rows={d.rows.map((r: any) => [r.at, { t: r.who }, r.what, r.link ? { t: r.detail || 'Ochish', u: r.link } : r.detail || '—'])} empty="Yozuv topilmadi." />
      <Pager pager={d.pager} />
    </>
  )
}

/* ---------- Yo'riqnoma ---------- */
export function Guide({ d }: { d: any }) {
  const loc = useLocation()
  return (
    <>
      <PageHeader title="Yo'riqnoma" subtitle="Sozlash va ishlatish bo'yicha bosqichma-bosqich qo'llanmalar" />
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 items-start">
        <Card pad={false} className="lg:sticky lg:top-0 max-h-[70vh] overflow-auto">
          <ul className="p-1.5">
            {d.guides.map((g: any) => (
              <li key={g.slug}><Link to={`/yoriqnoma/${g.slug}/`} className={cx('block px-3 py-2 rounded-lg text-[13.5px] hover:bg-surface2', loc.pathname.includes(g.slug) && 'bg-brandsoft font-semibold')}>{g.title}</Link></li>
            ))}
          </ul>
        </Card>
        <Card>{d.html ? <Rich html={d.html} /> : <Empty text="Chap tomondan bo'limni tanlang." icon={<FileSearch className="w-8 h-8 opacity-50" />} />}</Card>
      </div>
    </>
  )
}

/* ---------- Tizim holati ---------- */
export function Health({ d }: { d: any }) {
  const { submit } = useApp()
  const s = d.s
  const nav = useNavigate()
  const tone = (st: string) => (st === 'good' || st === 'active' ? 'ok' : st === 'cooldown' ? 'warn' : 'bad')
  return (
    <>
      <PageHeader title="Tizim holati" actions={<><Btn onClick={() => nav('/tizim/vazifalar/')}>Vazifalar navbati</Btn><Btn onClick={() => submit('/tizim/zaxira/')}>Zaxira nusxa olish</Btn></>} />
      {s.tips?.length > 0 && <Card className="mb-3" title="Tavsiyalar">{s.tips.map((t: string, i: number) => <div key={i} className="rounded-lg bg-warn/10 text-warn px-3 py-2 text-[13px] mb-1.5">{t}</div>)}</Card>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="CPU" icon={<Cpu className="w-4 h-4" />} value={`${s.server.cpu ?? '—'}%`} />
        <Stat label="RAM" icon={<MemoryStick className="w-4 h-4" />} value={`${s.server.ram ?? '—'}%`} />
        <Stat label="Disk" icon={<HardDrive className="w-4 h-4" />} value={`${s.server.disk_pct}%`} sub={`bo'sh ${s.server.disk_free_gb} GB`} />
        <Stat label="Ishlash vaqti" icon={<Clock className="w-4 h-4" />} value={`${s.server.uptime_h} s`} sub={`DB: ${s.server.db} ${s.server.db_ok ? '✔' : '✘'}`} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
        <Card title="Navbat va worker">
          <div className="flex items-center gap-2"><span>Worker:</span><Badge tone={s.queue.worker_alive ? 'ok' : 'bad'}>{s.queue.worker_alive ? 'ishlayapti' : 'javob bermayapti'}</Badge></div>
          <p className="text-muted mt-2 text-[13px]">Kutish: {s.queue.oldest_wait_min} daq · 24 soatda xato: {s.queue.failed_24h}</p>
          <div className="flex flex-wrap gap-1.5 mt-2">{Object.entries(s.queue.counts).map(([k, v]) => <Badge key={k}>{k}: {String(v)}</Badge>)}</div>
        </Card>
        <Card title="Cloudflare / R2">
          <div className="flex items-center gap-2">Worker: {s.worker.configured ? <><Badge tone={s.worker.ok ? 'ok' : 'warn'}>{s.worker.ok ? 'ulangan' : 'tekshirilmagan'}</Badge><span className="text-muted text-[13px]">bugungi klik {s.worker.clicks_today}</span></> : <Badge tone="warn">sozlanmagan</Badge>}</div>
          <p className="text-[13px] mt-2">Vaqtinchalik fayllar (R2): {s.r2.used_gb} / {s.r2.cap_gb} GB ({s.r2.pct}%), {s.r2.files} ta fayl</p>
          <div className="mt-2"><Progress value={s.r2.pct} tone={s.r2.pct > 85 ? 'bad' : undefined} /></div>
        </Card>
      </div>
      <div className="mt-3 space-y-3">
        <DataTable title="Ma'lumot provayderlari" columns={['Provayder', 'Holat', '24 soatda', 'Qoldiq', 'Izoh']} rows={s.providers.map((p: any) => [p.name, { t: p.status, b: tone(p.status) }, `${p.requests_24h} (${p.error_pct}% xato)`, `${p.remaining ?? '—'}${p.days_left ? ` · ~${p.days_left} kun` : ''}`, p.last_switch || p.last_error || ''])} />
        <DataTable title="AI provayderlar" columns={['Provayder', 'Kalitlar', 'Sovishda', '24 soatda', 'Xato', 'Holat']} rows={s.ai.map((p: any) => [p.name, `${p.active_keys}/${p.keys}`, p.cooldown, p.requests_24h, p.errors, { t: p.enabled ? 'faol' : "o'chiq", b: p.enabled ? 'ok' : 'warn' }])} />
        <DataTable title="Ulanishlar" columns={['Hisob', 'Biznes', 'Holat', 'Token', 'Xato']} rows={s.connections.map((c: any) => [{ t: c.name, u: `/ulanishlar/${c.id}/` }, c.business, { t: c.status, b: c.status === 'active' ? 'ok' : 'bad' }, c.expires || '—', c.error || ''])} />
      </div>
    </>
  )
}

/* ---------- Rol ruxsatlari matritsasi ---------- */
export function RoleMatrix({ d }: { d: any }) {
  const { submit, busy } = useApp()
  const [have, setHave] = useState<Set<string>>(() => new Set(d.have))
  const toggle = (c: string) => { const n = new Set(have); n.has(c) ? n.delete(c) : n.add(c); setHave(n) }
  const col = (a: string) => d.modules.map(([m]: string[]) => `${m}.${a}`)
  const row = (m: string) => d.actions.map(([a]: string[]) => `${m}.${a}`)
  const setMany = (codes: string[], on: boolean) => { const n = new Set(have); codes.forEach((c) => (on ? n.add(c) : n.delete(c))); setHave(n) }
  const save = () => { const fd = new FormData(); have.forEach((c) => fd.append('codes', c)); submit(`/foydalanuvchilar/rollar/${d.role.id}/`, fd, { stay: true }) }
  return (
    <>
      <PageHeader title={`Rol: ${d.role.name}`} subtitle={d.role.description} actions={<>
        <Link to="/foydalanuvchilar/rollar/" className="btn">Orqaga</Link>
        {d.can && !d.role.is_system && <ActionDelete id={d.role.id} />}
        {d.can && <Btn variant="primary" loading={busy} onClick={save}>Saqlash</Btn>}</>} />
      <Card pad={false}>
        <div className="overflow-auto max-h-[calc(100vh-220px)]">
          <table className="w-full text-[13.5px] min-w-[640px]">
            <thead className="sticky top-0 z-10"><tr><th className="th bg-surface2">Modul</th>{d.actions.map(([a, l]: string[]) => (
              <th key={a} className="th bg-surface2 text-center"><label className="cursor-pointer flex flex-col items-center gap-1">{l}{d.can && <input type="checkbox" className="w-3.5 h-3.5 accent-[var(--brand)]" checked={col(a).every((c: string) => have.has(c))} onChange={(e) => setMany(col(a), e.target.checked)} />}</label></th>))}</tr></thead>
            <tbody>{d.modules.map(([m, ml]: string[]) => (
              <tr key={m} className="hover:bg-surface2/50"><td className="td font-medium"><label className="flex items-center gap-2 cursor-pointer">{d.can && <input type="checkbox" className="w-3.5 h-3.5 accent-[var(--brand)]" checked={row(m).every((c: string) => have.has(c))} onChange={(e) => setMany(row(m), e.target.checked)} />}{ml}</label></td>
                {d.actions.map(([a]: string[]) => <td key={a} className="td text-center"><input type="checkbox" disabled={!d.can} className="w-4 h-4 accent-[var(--brand)]" checked={have.has(`${m}.${a}`)} onChange={() => toggle(`${m}.${a}`)} /></td>)}</tr>))}</tbody>
          </table>
        </div>
      </Card>
    </>
  )
}
function ActionDelete({ id }: { id: number }) {
  const { submit } = useApp()
  return <Btn variant="danger" onClick={() => { if (window.confirm("Rol o'chirilsinmi?")) submit(`/foydalanuvchilar/rollar/${id}/ochir/`) }}>Rolni o'chirish</Btn>
}

/* ---------- Media tahlil natijasi ---------- */
const tone = (c: string) => (c === 'ok' ? 'var(--ok)' : c === 'warn' ? 'var(--warn)' : 'var(--bad)')
export function MediaDetail({ d }: { d: any }) {
  const c = d.card
  return (
    <>
      <PageHeader title={d.name} subtitle={`${d.business} · ${nf(d.size)} bayt · ${d.at}`} actions={<Link to="/studiya/?tab=tahlil" className="btn">← Tahlillar</Link>} />
      {d.running && <Card className="mb-3"><div className="flex items-center gap-2"><Spinner /> Tahlil davom etmoqda… (katta videolar bir necha daqiqa oladi). Sahifani birozdan keyin yangilang.</div></Card>}
      {d.status === 'failed' && <Card className="mb-3"><Badge tone="bad">Xato</Badge> Tahlil bajarilmadi. Faylni qayta yuklab ko'ring.</Card>}
      {c && (
        <div className="space-y-3">
          <Card>
            <div className="flex flex-wrap items-center gap-5">
              {c.total !== null && <div className="w-24 h-24 rounded-full grid place-items-center shrink-0" style={{ background: `conic-gradient(${tone(c.total_cls)} ${c.total * 3.6}deg, var(--surface-2) 0)` }}><div className="w-[74px] h-[74px] rounded-full bg-surface grid place-items-center text-center"><span><b className="text-[22px]">{c.total}</b><br /><small className="text-muted">/ 100</small></span></div></div>}
              <div className="flex-1 min-w-[240px]">
                {c.verdict && <div className="font-bold text-[16px]" style={{ color: tone(c.verdict.cls) }}>{c.verdict.title}</div>}
                {c.verdict && <div className="text-muted text-[13px]">{c.verdict.text}</div>}
                {c.summary && <p className="mt-2">{c.summary}</p>}
                <div className="flex flex-wrap gap-1.5 mt-2">{c.hook_text && <Badge>🪝 Hook: {c.hook_text}</Badge>}<Badge>📣 CTA: {c.cta_text}</Badge>{c.pacing && <Badge>⏱ Sur'at: {c.pacing}</Badge>}</div>
              </div>
            </div>
          </Card>
          {c.scores?.length > 0 && <Card title="Mezonlar bo'yicha baho"><div className="grid sm:grid-cols-2 gap-x-6 gap-y-2.5">{c.scores.map((s: any) => (
            <div key={s.label} className="grid grid-cols-[130px_1fr_34px] items-center gap-2 text-[13px]"><span>{s.label}</span><div className="h-2 rounded-full bg-surface2 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${s.pct}%`, background: tone(s.cls) }} /></div><b>{s.v}</b></div>))}</div></Card>}
          {c.scenes?.length > 0 && <Card title="Video sahna-sahna">
            <div className="flex items-end gap-1 h-24">{c.scenes.map((s: any, i: number) => <div key={i} title={`${s.t}: ${s.what}`} className="flex-1 rounded-t" style={{ height: s.h, background: tone(s.cls) }} />)}</div>
            <div className="flex gap-1 text-[10.5px] text-muted mt-1">{c.scenes.map((s: any, i: number) => <span key={i} className="flex-1 text-center truncate">{s.t}</span>)}</div>
            <div className="mt-3 divide-y divide-line">{c.scenes.map((s: any, i: number) => <div key={i} className="flex items-start gap-3 py-2"><b className="w-16 shrink-0 text-[13px]">{s.t}</b><div className="flex-1 text-[13.5px]">{s.what}{s.note && <div className="text-muted text-[12.5px]">{s.note}</div>}</div><Badge tone={s.cls}>{Math.round(s.att)}</Badge></div>)}</div></Card>}
          {c.fit?.length > 0 && <Card title="Qaysi platformaga mos?"><div className="flex flex-wrap gap-2">{c.fit.map((f: any) => <Badge key={f.label} tone={f.cls}>{f.label}: {f.v}/10</Badge>)}</div></Card>}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Card title="👍 Kuchli tomonlari">{c.strengths.length ? c.strengths.map((x: string, i: number) => <div key={i} className="py-1.5 border-b border-line last:border-0">{x}</div>) : '—'}</Card>
            <Card title="🛠 Nima tuzatish kerak">{c.improvements.length ? c.improvements.map((x: any, i: number) => <div key={i} className="py-1.5 border-b border-line last:border-0">{x.prio && <Badge tone={x.cls} className="mr-1.5">{x.prio}</Badge>}{x.fix}</div>) : '—'}</Card>
          </div>
          {d.degraded && <p className="text-bad text-[12.5px]">Qisman tahlil: ba'zi bosqichlar bajarilmadi (AI yoki transkripsiya mavjud emas edi).</p>}
        </div>
      )}
      {!c && !d.running && d.has_analysis && <Card className="mb-3"><Badge tone="warn">AI xulosa yo'q</Badge> Texnik ma'lumot pastda. AI kaliti yoki limitni tekshiring.</Card>}
      <Card className="mt-3" title="Texnik ma'lumot va transkripsiya">
        <div className="grid sm:grid-cols-3 gap-3">{d.tech.map(([k, v]: string[]) => <div key={k}><div className="text-muted text-[12px]">{k}</div><div className="break-words">{v}</div></div>)}</div>
        {d.transcript && <><h3 className="font-semibold mt-3 mb-1">Transkripsiya</h3><div className="whitespace-pre-wrap text-[13.5px]">{d.transcript}</div></>}
        {d.raw && <details className="mt-3"><summary className="cursor-pointer font-semibold">Xom AI javobi</summary><pre className="bg-surface2 rounded-lg p-3 text-[12px] max-h-[260px] overflow-auto mt-2 whitespace-pre-wrap">{d.raw}</pre></details>}
      </Card>
    </>
  )
}

/* ---------- Yangi kontent: platforma tanlash ---------- */
export function ContentChoose({ d }: { d: any }) {
  return (
    <>
      <PageHeader title="Yangi kontent" subtitle="Qaysi platforma uchun post tayyorlaysiz? Har birining o'z formasi, AI xulosasi va ko'rinishi bor." actions={<Link to="/kalendar/" className="btn">Orqaga</Link>} />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {d.cards.map((c: any) => (
          <Link key={c.key} to={`/kalendar/yangi/${c.key}/${c.q}`} className={cx('card p-5 block hover:border-brand/50 hover:shadow-pop transition', !c.n && 'opacity-60')}>
            <div className="flex items-center gap-3"><span className="w-11 h-11 rounded-xl grid place-items-center text-white font-bold" style={{ background: PLAT[c.key]?.color }}>{PLAT[c.key]?.short}</span><div><h2 className="font-bold text-[16px] leading-tight">{c.name}</h2><div className="text-muted text-[12.5px]">{c.types}</div></div></div>
            <div className="mt-3">{c.n ? <Badge tone="ok">{c.n} ta akkaunt ulangan</Badge> : <Badge tone="bad">akkaunt ulanmagan</Badge>}</div>
            <ul className="mt-3 space-y-1 text-[12.5px] text-muted list-disc pl-4">{c.tips.map((t: string) => <li key={t}>{t}</li>)}</ul>
          </Link>
        ))}
      </div>
    </>
  )
}

/* ---------- Postlar statistikasi ---------- */
export function PostList({ d }: { d: any }) {
  const nav = useNavigate()
  const loc = useLocation()
  const set = (k: string, v: string) => { const p = new URLSearchParams(loc.search); v ? p.set(k, v) : p.delete(k); p.delete('p'); nav(loc.pathname + '?' + p.toString()) }
  return (
    <>
      <PageHeader title="Postlar statistikasi" subtitle="Har bir post uchun raqamlar va AI tahlil — postni bosing" />
      <Card className="mb-3" bodyClass="!p-3">
        <div className="flex flex-wrap gap-2">
          <select className="input w-auto min-w-[170px]" value={d.f.account} onChange={(e) => set('account', e.target.value)}><option value="">Barcha ulanishlar</option>{d.accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
          <select className="input w-auto min-w-[140px]" value={d.f.format} onChange={(e) => set('format', e.target.value)}><option value="">Barcha formatlar</option>{d.formats.map(([k, v]: string[]) => <option key={k} value={k}>{v}</option>)}</select>
          <select className="input w-auto min-w-[160px]" value={d.f.sort} onChange={(e) => set('sort', e.target.value)}><option value="date">Sana bo'yicha</option><option value="views">Ko'rish bo'yicha</option><option value="er">ER bo'yicha</option><option value="likes">Layk bo'yicha</option></select>
        </div>
      </Card>
      <Card pad={false} className="overflow-hidden">
        {d.rows.length === 0 ? <Empty text="Hali post statistikasi yo'q. Ma'lumot yig'ilgach shu yerda chiqadi." /> : (
          <>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-[13.5px]">
                <thead><tr><th className="th">Post</th><th className="th">Ulanish</th><th className="th">Sana</th><th className="th text-right">Ko'rish</th><th className="th text-right">Layk</th><th className="th text-right">Izoh</th><th className="th text-right">ER</th><th className="th" /></tr></thead>
                <tbody>{d.rows.map((r: any) => (
                  <tr key={r.id} className="hover:bg-surface2/50 cursor-pointer" onClick={() => nav(`/tahlil/post/${r.id}/`)}>
                    <td className="td max-w-[340px]"><div className="flex items-center gap-2"><PlatDot p={r.platform} /><span className="truncate">{r.text || '(matnsiz)'}</span></div><div className="text-[11.5px] text-muted ml-4.5 pl-[18px]">{r.format}</div></td>
                    <td className="td whitespace-nowrap">{r.account}</td><td className="td whitespace-nowrap text-muted">{r.date}</td>
                    <td className="td text-right">{nf(r.views)}</td><td className="td text-right">{nf(r.likes)}</td><td className="td text-right">{nf(r.comments)}</td>
                    <td className="td text-right font-semibold">{r.er === null ? '—' : pct(r.er, 2)}</td><td className="td text-right"><ChevronRight className="w-4 h-4 text-muted inline" /></td>
                  </tr>))}</tbody>
              </table>
            </div>
            <ul className="md:hidden divide-y divide-line">{d.rows.map((r: any) => (
              <li key={r.id}><Link to={`/tahlil/post/${r.id}/`} className="block px-4 py-3">
                <div className="flex items-center gap-2"><PlatDot p={r.platform} /><span className="truncate font-medium">{r.text || '(matnsiz)'}</span></div>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-[12px] text-muted"><span>{r.account} · {r.format}</span><span>{r.date}</span></div>
                <div className="flex gap-4 mt-1.5 text-[12.5px]"><span><Eye className="w-3.5 h-3.5 inline mr-1" />{nf(r.views)}</span><span><Heart className="w-3.5 h-3.5 inline mr-1" />{nf(r.likes)}</span><span><MessageCircle className="w-3.5 h-3.5 inline mr-1" />{nf(r.comments)}</span><b>ER {r.er === null ? '—' : pct(r.er, 2)}</b></div>
              </Link></li>))}</ul>
          </>
        )}
      </Card>
      <Pager pager={d.pager} />
    </>
  )
}

/* ---------- Bitta post: raqamlar + AI tahlil ---------- */
export function PostInsight({ d }: { d: any }) {
  const { submit, busy } = useApp()
  const [tab, setTab] = useState<'nums' | 'ai'>('nums')
  const n = d.now
  const ins = d.insight
  const verdict = ins ? ({ winner: ['G\'olib post', 'ok'], average: ['O\'rtacha', 'blue'], weak: ['Past natija', 'warn'] } as any)[ins.verdict] || [ins.verdict, ''] : null
  const hist = d.history.length > 1 ? { kind: 'line' as const, labels: d.history.map((h: any) => `${h.age_h}s`), series: [{ name: "Ko'rish", data: d.history.map((h: any) => h.views || 0) }, { name: 'Layk', data: d.history.map((h: any) => h.likes || 0) }] } : null
  const rel = (v: number | null) => (v === null || v === undefined ? null : v)
  return (
    <>
      <PageHeader title="Post statistikasi" subtitle={<span className="flex items-center gap-2"><PlatDot p={d.platform} />{d.account} · {d.format} · {d.published}</span>}
        actions={<><Link to="/tahlil/postlar/" className="btn">← Postlar</Link>{d.item_id && <Link to={`/kalendar/${d.item_id}/`} className="btn">Kontentni ochish</Link>}{d.url && <a href={d.url} target="_blank" rel="noopener" className="btn"><ExternalLink className="w-4 h-4" /> Postni ochish</a>}</>} />
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <div className="lg:col-span-5 space-y-3">
          <Card title="Post matni"><div className="whitespace-pre-wrap break-words text-[13.5px] max-h-[260px] overflow-auto">{d.text || '(matnsiz)'}</div>{d.hashtags.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{d.hashtags.map((h: string) => <Badge key={h} tone="blue">{h.startsWith('#') ? h : '#' + h}</Badge>)}</div>}</Card>
          {d.winner && <Card className="border-ok/40 bg-ok/5"><div className="flex items-center gap-2 text-ok font-semibold"><Sparkles className="w-4 h-4" /> Bu post o'rtachadan sezilarli yaxshi chiqqan (g'olib)</div></Card>}
        </div>
        <div className="lg:col-span-7 space-y-3">
          <Segmented value={tab} onChange={setTab} items={[{ key: 'nums', label: 'Raqamlar' }, { key: 'ai', label: '✨ AI tahlil' }]} />
          {tab === 'nums' ? (
            <>
              {n ? (
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2.5">
                  {[['Ko\'rish', n.views, Eye], ['Qamrov', n.reach, Eye], ['Layk', n.likes, Heart], ['Izoh', n.comments, MessageCircle], ['Ulashish', n.shares, Share2], ['Saqlash', n.saves, Bookmark]].map(([l, v, I]: any) => (
                    <div key={l} className="card px-3 py-2.5"><div className="text-[11.5px] text-muted flex items-center gap-1"><I className="w-3.5 h-3.5" />{l}</div><div className="text-[19px] font-bold">{nf(v)}</div></div>))}
                </div>
              ) : <Card><Empty text="Bu post uchun hali raqam yig'ilmagan." /></Card>}
              {n && (
                <Card title="Biznes o'rtachasi bilan solishtirish (oxirgi 30 kun)">
                  <div className="grid sm:grid-cols-2 gap-4">
                    {[['ER', n.er, d.baseline.er, rel(d.ratio.er), true], ["Ko'rish", n.views, d.baseline.views, rel(d.ratio.views), false]].map(([l, v, b, r, isP]: any) => (
                      <div key={l}>
                        <div className="flex justify-between text-[13px] mb-1"><span className="font-semibold">{l}</span><span className={cx('font-semibold', r && r >= 1 ? 'text-ok' : 'text-bad')}>{r ? `×${r.toFixed(2)}` : '—'}</span></div>
                        <div className="text-[12.5px] text-muted">Bu post: <b className="text-fg">{isP ? pct(v, 2) : nf(v)}</b> · Median: <b className="text-fg">{b === null || b === undefined ? '—' : isP ? pct(b, 2) : nf(b)}</b></div>
                        <div className="mt-1.5"><Progress value={r ? Math.min(100, (r / 2) * 100) : 0} tone={r && r >= 1 ? 'ok' : 'bad'} /></div>
                      </div>))}
                  </div>
                  <p className="help">Median {d.baseline.n} ta postdan hisoblangan. ×1.00 — o'rtacha daraja.</p>
                </Card>
              )}
              {hist && <Card title="Dinamika (post yoshi bo'yicha)"><Chart spec={hist} height={200} /></Card>}
            </>
          ) : (
            <Card title="«Nega shunday natija?» — AI tahlil" actions={d.can_ai && <Btn variant="primary" size="sm" loading={busy} onClick={() => submit(`/tahlil/post/${d.id}/`)}><Sparkles className="w-3.5 h-3.5" /> {ins ? 'Qayta tahlil' : 'Tahlil qilish'}</Btn>}>
              {!ins ? <Empty text="Hali AI tahlil yaratilmagan. AI faqat yuqoridagi aniq raqamlarga tayanadi (taxmin qilmaydi)." icon={<Sparkles className="w-8 h-8 opacity-50" />} /> : (
                <div className="space-y-3">
                  <div className="flex items-center gap-2"><Badge tone={verdict[1]}>{verdict[0]}</Badge><span className="text-muted text-[12px]">{ins.at}</span></div>
                  {ins.summary && <p className="leading-relaxed">{ins.summary}</p>}
                  {([['reasons', 'Sabablar', 'ok'], ['repeat', 'Takrorlash', 'blue'], ['change', "O'zgartirish", 'warn']] as const).map(([k, t, tn]) => ins[k].length > 0 && (
                    <div key={k}><div className="font-semibold text-[13px] mb-1 flex items-center gap-2"><Badge tone={tn}>{t}</Badge></div><ul className="list-disc pl-5 space-y-1 text-[13.5px]">{ins[k].map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>))}
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
