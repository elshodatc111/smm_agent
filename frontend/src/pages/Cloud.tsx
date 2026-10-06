import { useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Check, Cloud as CloudIcon, Copy, Film, Link2, Plug, RotateCw, Search, Trash2, Upload, Zap } from 'lucide-react'
import { A } from '../components/Blocks'
import { Badge, Btn, Card, Empty, PageHeader, Progress, Segmented, Stat, useConfirm } from '../components/ui'
import { Pager } from './Misc'
import { useApp } from '../lib/app'
import { request } from '../lib/api'
import { useToast } from '../lib/toast'
import { cx, fmtDate } from '../lib/format'

function TagBox({ id, tags, can }: { id: number; tags: string; can: boolean }) {
  const [v, setV] = useState((tags || '').split(',').filter(Boolean).join(', '))
  const [ok, setOk] = useState(false)
  if (!can) return <div className="text-[11.5px] text-muted truncate">{v || '—'}</div>
  return <input className={cx('input h-7 text-[12px]', ok && '!border-ok')} value={v} placeholder="teglar…" onChange={(e) => setV(e.target.value)}
    onBlur={async () => { try { const r = await request(`/cloudflare/${id}/teg/`, { method: 'POST', body: { tags: v }, silent: true }); setV((r.data.tags || []).join(', ')); setOk(true); setTimeout(() => setOk(false), 900) } catch { /* toast */ } }} />
}

export function Cloud({ d }: { d: any }) {
  const nav = useNavigate()
  const loc = useLocation()
  const { submit, busy } = useApp()
  const confirm = useConfirm()
  const toast = useToast()
  const [sel, setSel] = useState<number[]>([])
  const [tags, setTags] = useState('')
  const [q, setQ] = useState(d.f.q || '')
  const [copied, setCopied] = useState<number | null>(null)
  const up = useRef<HTMLInputElement>(null)
  const rows: any[] = d.rows

  const go = (patch: Record<string, string>) => {
    const p = new URLSearchParams(loc.search); p.delete('p')
    Object.entries(patch).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)))
    nav(loc.pathname + (p.toString() ? '?' + p.toString() : ''))
  }
  const upload = (fl: File[]) => { if (!fl.length) return; const fd = new FormData(); fl.forEach((f) => fd.append('files', f, f.name)); if (tags) fd.append('tags', tags); submit('/cloudflare/yuklash/', fd, { stay: true }).then(() => setTags('')) }
  const link = async (id: number) => {
    try {
      const r = await request(`/cloudflare/${id}/havola/`, { method: 'POST', silent: true })
      if (!r.data.url) return toast.push('warning', "Havola yo'q")
      try { await navigator.clipboard.writeText(r.data.url); setCopied(id); setTimeout(() => setCopied(null), 1500) } catch { toast.push('info', r.data.url) }
    } catch { /* toast */ }
  }
  const selectable = rows.filter((r) => r.status !== 'deleted').map((r) => r.id)
  const tone = (c: string) => (c === 'ok' ? 'ok' : c === 'bad' ? 'bad' : c === 'warn' ? 'warn' : '')

  return (
    <div>
      <PageHeader title="Cloudflare ombori" subtitle={d.bucket ? `Bucket: ${d.bucket}` : 'Media fayllar ombori'}
        actions={<>
          <Btn onClick={() => submit('/cloudflare/sinov/', undefined, { stay: true })} disabled={busy}><Plug className="w-4 h-4" /> Ulanishni tekshirish</Btn>
          <Btn onClick={() => submit('/cloudflare/avto/', undefined, { stay: true })} disabled={busy}><Zap className="w-4 h-4" /> {d.auto ? 'Avto-yuklash: yoqilgan' : "Avto-yuklash: o'chiq"}</Btn>
        </>} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Card className="lg:col-span-2"><div className="flex items-center justify-between text-[13px] mb-1.5"><span className="font-semibold">Joy: {d.used} / {d.limit}</span><span className="text-muted">{d.pct}%</span></div><Progress value={d.pct} tone={d.pct > 85 ? 'bad' : undefined} />
          <div className="flex gap-2 mt-2 flex-wrap"><Badge tone={d.r2_ok ? 'ok' : 'bad'}>R2 {d.r2_ok ? 'ulangan' : 'sozlanmagan'}</Badge><Badge tone={d.kv_ok ? 'ok' : 'warn'}>Worker {d.kv_ok ? 'ulangan' : 'yo‘q'}</Badge>{!d.r2_ok && <A to="/sozlamalar/?tab=xizmatlar" className="text-[12px] text-info underline">Sozlash</A>}</div></Card>
        <Stat label="Yuklangan" value={d.counts.uploaded} icon={<CloudIcon className="w-4 h-4" />} />
        <Stat label="Xato / yuklanmoqda" value={`${d.counts.failed} / ${d.counts.pending}`} tone={d.counts.failed ? 'bad' : ''} />
      </div>

      {d.can_edit && d.has_business && (
        <Card className="mb-3">
          <div className="flex flex-wrap items-center gap-2" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(Array.from(e.dataTransfer.files)) }}>
            <Btn variant="primary" onClick={() => up.current?.click()} loading={busy}><Upload className="w-4 h-4" /> Fayl yuklash</Btn>
            <input ref={up} type="file" hidden multiple accept="image/*,video/*,.pdf" onChange={(e) => { upload(Array.from(e.target.files || [])); e.target.value = '' }} />
            <input className="input w-[240px]" placeholder="Teglar: aksiya, kurs, logotip" value={tags} onChange={(e) => setTags(e.target.value)} />
            <span className="text-[12.5px] text-muted">Fayllarni shu yerga tashlash ham mumkin (rasm, mp4/mov, pdf).</span>
          </div>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <form className="relative" onSubmit={(e) => { e.preventDefault(); go({ q }) }}><Search className="w-4 h-4 absolute left-3 top-2.5 text-muted" /><input className="input pl-9 w-[260px]" placeholder="Nomi, teg yoki post…" value={q} onChange={(e) => setQ(e.target.value)} /></form>
        <Segmented items={[{ key: '', label: 'Faol' }, { key: 'failed', label: 'Xato' }, { key: 'pending', label: 'Yuklanmoqda' }, { key: 'deleted', label: "O'chirilgan" }]} value={d.f.status} onChange={(k) => go({ status: k })} />
        {d.all_tags.length > 0 && <select className="input h-8 w-auto text-[12.5px]" value={d.f.tag} onChange={(e) => go({ tag: e.target.value })}><option value="">Barcha teglar</option>{d.all_tags.map((t: string) => <option key={t} value={t}>#{t}</option>)}</select>}
        {d.can_edit && (
          <span className="ml-auto flex gap-2">
            {sel.length > 0 && <Btn variant="danger" size="sm" onClick={async () => { if (await confirm(`${sel.length} ta fayl Cloudflare'dan o'chiriladi. Davom etasizmi?`, { danger: true })) { await submit('/cloudflare/tanlangan-ochir/', { ids: sel }, { stay: true }); setSel([]) } }}><Trash2 className="w-3.5 h-3.5" /> Tanlanganlarni o'chirish ({sel.length})</Btn>}
            <Btn size="sm" onClick={async () => { if (await confirm("Nashr bo'lgan postlarning hamma fayli o'chiriladi. Davom etasizmi?", { danger: true })) submit('/cloudflare/tozalash/', undefined, { stay: true }) }}>Nashr bo'lganlarni tozalash</Btn>
          </span>
        )}
      </div>

      {!rows.length ? <Card><Empty text="Fayl topilmadi." /></Card> : (
        <>
          {d.can_edit && <label className="flex items-center gap-2 text-[12.5px] text-muted mb-2 cursor-pointer w-fit"><input type="checkbox" className="accent-[var(--brand)]" checked={sel.length > 0 && sel.length === selectable.length} onChange={(e) => setSel(e.target.checked ? selectable : [])} /> Hammasini belgilash</label>}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6 gap-3">
            {rows.map((r) => (
              <div key={r.id} className={cx('card overflow-hidden flex flex-col', sel.includes(r.id) && 'ring-2 ring-brand')}>
                <div className="relative aspect-[4/3] bg-surface2">
                  {r.status === 'uploaded' ? (r.kind === 'video' ? <video src={r.url} muted preload="metadata" className="w-full h-full object-cover" /> : <img src={r.url} alt="" loading="lazy" className="w-full h-full object-cover" />) : <div className="w-full h-full grid place-items-center text-muted"><Film className="w-6 h-6" /></div>}
                  {d.can_edit && r.status !== 'deleted' && <input type="checkbox" aria-label="Tanlash" className="absolute top-2 left-2 w-4 h-4 accent-[var(--brand)]" checked={sel.includes(r.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, r.id] : s.filter((x) => x !== r.id)))} />}
                  <Badge tone={tone(r.cls)} className="absolute top-2 right-2">{r.label}</Badge>
                </div>
                <div className="p-2.5 space-y-1.5 flex-1 flex flex-col">
                  <div className="text-[12.5px] font-medium truncate" title={r.name}>{r.name}</div>
                  <div className="text-[11.5px] text-muted truncate">{r.size}{r.item_id ? <> · <A to={`/kalendar/${r.item_id}/`} className="hover:underline text-info">{r.item_title}</A></> : ''} · {fmtDate(r.at)}</div>
                  {r.error && <div className="text-[11.5px] text-bad line-clamp-2">{r.error}</div>}
                  <TagBox id={r.id} tags={r.tags} can={d.can_edit && r.status !== 'deleted'} />
                  <div className="flex gap-1 mt-auto pt-1">
                    {r.status === 'uploaded' && <Btn size="sm" onClick={() => link(r.id)} title="7 kunlik havolani nusxalash">{copied === r.id ? <Check className="w-3.5 h-3.5" /> : <Link2 className="w-3.5 h-3.5" />}</Btn>}
                    {r.status === 'uploaded' && <a className="btn btn-sm" href={r.url} target="_blank" rel="noopener" aria-label="Ochish"><Copy className="w-3.5 h-3.5 hidden" />Ochish</a>}
                    {r.status === 'failed' && d.can_edit && <Btn size="sm" onClick={() => submit(`/cloudflare/${r.id}/qayta/`, undefined, { stay: true })}><RotateCw className="w-3.5 h-3.5" /></Btn>}
                    {r.status !== 'deleted' && d.can_edit && <Btn size="sm" variant="danger" className="ml-auto" aria-label="O'chirish" onClick={async () => { if (await confirm("Fayl Cloudflare'dan o'chiriladi. Davom etasizmi?", { danger: true })) submit(`/cloudflare/${r.id}/ochir/`, undefined, { stay: true }) }}><Trash2 className="w-3.5 h-3.5" /></Btn>}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Pager pager={d.pager} />
        </>
      )}
    </div>
  )
}
