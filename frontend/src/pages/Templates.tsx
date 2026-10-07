import { useState } from 'react'
import { Bookmark, Cloud as CloudIcon, Pencil, Plus, Trash2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge, Btn, Card, Empty, Modal, PageHeader, useConfirm } from '../components/ui'
import { CloudPicker, CloudFile } from '../components/CloudPicker'
import { RichEditor } from '../components/RichEditor'
import { useApp } from '../lib/app'
import { cx, FMT } from '../lib/format'

const PLATS: [string, string][] = [['', 'Hamma platforma'], ['telegram', 'Telegram'], ['instagram', 'Instagram'], ['youtube', 'YouTube']]
type Row = any

const blank = (): Row => ({ id: 0, name: '', platform: '', media_type: 'text', title: '', text: '', brief: '', time_hint: '', weekday: '', tg_buttons: '', tg_cols: '2', yt_title: '', yt_tags: '', yt_privacy: 'public', files: [] })

function Editor({ d, init, onClose }: { d: any; init: Row; onClose: () => void }) {
  const { submit, busy } = useApp()
  const [v, setV] = useState<Row>(init)
  const [files, setFiles] = useState<CloudFile[]>(init.files || [])
  const [pick, setPick] = useState(false)
  const set = (k: string, val: any) => setV((x: Row) => ({ ...x, [k]: val }))
  const types: string[] = v.platform ? d.allowed[v.platform] || [] : Object.keys(FMT)
  const mt = types.includes(v.media_type) ? v.media_type : types[0]
  const save = async () => {
    const fd = new FormData()
    Object.entries({ ...v, media_type: mt }).forEach(([k, val]) => { if (!['files', 'id'].includes(k) && val !== undefined && val !== null) fd.append(k, String(val)) })
    files.forEach((f) => fd.append('cloud_ids', String(f.id)))
    await submit(v.id ? `/shablonlar/${v.id}/saqlash/` : '/shablonlar/yangi/', fd)
    onClose()
  }
  return (
    <Modal open onClose={onClose} width={720} title={v.id ? 'Shablonni tahrirlash' : 'Yangi shablon'}
      footer={<><Btn onClick={onClose}>Bekor qilish</Btn><Btn variant="primary" loading={busy} onClick={save} disabled={!v.name.trim()}>Saqlash</Btn></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="sm:col-span-2"><label className="label" htmlFor="t_name">Shablon nomi</label><input id="t_name" className="input" value={v.name} maxLength={120} placeholder="Masalan: Dushanba aksiyasi" onChange={(e) => set('name', e.target.value)} autoFocus /></div>
        <div><label className="label" htmlFor="t_pl">Platforma</label><select id="t_pl" className="input" value={v.platform} onChange={(e) => set('platform', e.target.value)}>{PLATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
        <div><label className="label">Post turi</label><div className="flex flex-wrap gap-1.5">{types.map((t) => <button key={t} type="button" onClick={() => set('media_type', t)} className={cx('chip h-8 text-[12.5px] px-3', mt === t && 'chip-on')}>{FMT[t] || t}</button>)}</div></div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="t_text">Matn <span className="font-normal text-muted">— {d.vars_help}</span></label>
          <RichEditor id="t_text" value={v.text} onChange={(x: string) => set('text', x)} rows={6} richOk={!v.platform || v.platform === 'telegram'} placeholder="Tayyor matn. Masalan: {kun} aksiyasi! {biznes} sizni kutadi." />
        </div>
        <div><label className="label" htmlFor="t_wd">Hafta kuni (ixtiyoriy)</label>
          <select id="t_wd" className="input" value={v.weekday} onChange={(e) => set('weekday', e.target.value)}><option value="">Belgilanmagan</option>{d.weekdays.map((w: string, i: number) => <option key={i} value={i}>{w}</option>)}</select></div>
        <div><label className="label" htmlFor="t_time">Odatiy vaqt (ixtiyoriy)</label><input id="t_time" type="time" className="input" value={v.time_hint} onChange={(e) => set('time_hint', e.target.value)} /></div>
        <div className="sm:col-span-2">
          <div className="label">Fayllar (Cloudflare'dan)</div>
          <div className="flex flex-wrap gap-2 items-start">
            {files.map((f) => (
              <div key={f.id} className="relative w-[84px]">
                <div className="aspect-square rounded-lg overflow-hidden bg-surface2 border border-line">{f.kind === 'video' ? <video src={f.url} muted preload="metadata" className="w-full h-full object-cover" /> : <img src={f.url} alt="" className="w-full h-full object-cover" />}</div>
                <button type="button" aria-label="Olib tashlash" onClick={() => setFiles((a) => a.filter((x) => x.id !== f.id))} className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-black/70 text-white grid place-items-center hover:bg-bad"><X className="w-3 h-3" /></button>
                <div className="text-[10.5px] text-muted truncate mt-0.5">{f.name}</div>
              </div>
            ))}
            <Btn size="sm" onClick={() => setPick(true)}><CloudIcon className="w-3.5 h-3.5" /> Fayl biriktirish</Btn>
          </div>
          <p className="help">Shablondan post yaratganda bu fayllar avtomatik qo'shiladi (keyin o'zgartirsa bo'ladi).</p>
        </div>
        {(!v.platform || v.platform === 'telegram') && (
          <div className="sm:col-span-2"><label className="label" htmlFor="t_btn">Telegram tugmalari <span className="font-normal text-muted">— har qatorda: Matn | https://havola</span></label>
            <textarea id="t_btn" className="input" rows={3} value={v.tg_buttons} onChange={(e) => set('tg_buttons', e.target.value)} placeholder={'Ro\'yxatdan o\'tish | https://example.com'} />
            <div className="flex items-center gap-2 mt-1.5 text-[12.5px] text-muted">Qatorda <select className="input h-8 w-auto" value={v.tg_cols} onChange={(e) => set('tg_cols', e.target.value)}><option>1</option><option>2</option><option>3</option></select> tugma</div></div>
        )}
        {(!v.platform || v.platform === 'youtube') && (
          <>
            <div><label className="label" htmlFor="t_yt">YouTube sarlavhasi</label><input id="t_yt" className="input" value={v.yt_title} onChange={(e) => set('yt_title', e.target.value)} /></div>
            <div><label className="label" htmlFor="t_pv">Maxfiylik</label><select id="t_pv" className="input" value={v.yt_privacy} onChange={(e) => set('yt_privacy', e.target.value)}><option value="public">Ochiq</option><option value="unlisted">Havola orqali</option><option value="private">Yopiq</option></select></div>
            <div className="sm:col-span-2"><label className="label" htmlFor="t_tg">YouTube teglari (vergul bilan)</label><input id="t_tg" className="input" value={v.yt_tags} onChange={(e) => set('yt_tags', e.target.value)} /></div>
          </>
        )}
      </div>
      <CloudPicker open={pick} onClose={() => setPick(false)} multi onPick={(fl) => setFiles((a) => [...a, ...fl.filter((f) => !a.some((x) => x.id === f.id))])} />
    </Modal>
  )
}

export function Templates({ d }: { d: any }) {
  const { submit } = useApp()
  const confirm = useConfirm()
  const [edit, setEdit] = useState<Row | null>(null)
  const rows: Row[] = d.rows
  const wd = (r: Row) => (r.weekday === '' ? '' : d.weekdays[r.weekday])
  return (
    <div>
      <PageHeader title="Post shablonlari" subtitle="Tez-tez takrorlanadigan postlar uchun tayyor qolip: bir marta yarating, keyin bir bosishda ishlating"
        actions={d.can_create ? <Btn variant="primary" onClick={() => setEdit(blank())}><Plus className="w-4 h-4" /> Yangi shablon</Btn> : undefined} />
      {!d.has_business && <div className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-[13px] mb-3">Yangi shablon yaratish uchun yuqoridan biznesni tanlang.</div>}
      {!rows.length ? <Card><Empty icon={<Bookmark className="w-6 h-6" />} text="Hali shablon yo'q. «Yangi shablon» tugmasini bosing yoki post sahifasida «Shablon sifatida saqlash» ni ishlating." action={d.can_create ? <Btn variant="primary" onClick={() => setEdit(blank())}><Plus className="w-4 h-4" /> Yangi shablon</Btn> : undefined} /></Card> : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {rows.map((r) => (
            <Card key={r.id} className="flex flex-col gap-2">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1"><div className="font-semibold text-[14px] truncate">{r.name}</div><div className="text-[12px] text-muted truncate">{r.business}</div></div>
                <Badge>{r.platform ? r.platform[0].toUpperCase() + r.platform.slice(1) : 'Hamma'}</Badge><Badge tone="blue">{FMT[r.media_type] || r.media_type}</Badge>
              </div>
              <div className="text-[13px] text-muted line-clamp-3 whitespace-pre-line min-h-[3.2em]">{(r.text || '').replace(/<[^>]+>/g, '') || '— matnsiz —'}</div>
              {r.files.length > 0 && <div className="flex gap-1.5">{r.files.slice(0, 5).map((f: any) => <div key={f.id} className="w-10 h-10 rounded-md overflow-hidden bg-surface2 border border-line">{f.kind === 'video' ? <video src={f.url} muted preload="metadata" className="w-full h-full object-cover" /> : <img src={f.url} alt="" loading="lazy" className="w-full h-full object-cover" />}</div>)}{r.files.length > 5 && <span className="text-[12px] text-muted self-center">+{r.files.length - 5}</span>}</div>}
              <div className="text-[12px] text-muted">{[wd(r), r.time_hint, `${r.uses} marta ishlatilgan`].filter(Boolean).join(' · ')}</div>
              <div className="flex gap-1.5 mt-auto pt-1">
                {d.can_create && <Link to={`/kalendar/yangi/${r.platform ? r.platform + '/' : ''}?shablon=${r.id}`} className="btn btn-primary btn-sm">Ishlatish</Link>}
                {r.can_edit && <Btn size="sm" onClick={() => setEdit(r)}><Pencil className="w-3.5 h-3.5" /> Tahrirlash</Btn>}
                {r.can_delete && <Btn size="sm" variant="danger" className="ml-auto" aria-label="O'chirish" onClick={async () => { if (await confirm(`«${r.name}» shabloni o'chiriladi. Davom etasizmi?`, { danger: true })) submit(`/shablonlar/${r.id}/ochir/`, undefined, { stay: true }) }}><Trash2 className="w-3.5 h-3.5" /></Btn>}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Card className="mt-3"><div className="text-[13px]"><b>O'zgaruvchilar.</b> Matnda yozsangiz, post yaratilganda almashtiriladi: {d.vars_help}</div></Card>
      {edit && <Editor d={d} init={edit} onClose={() => setEdit(null)} />}
    </div>
  )
}
