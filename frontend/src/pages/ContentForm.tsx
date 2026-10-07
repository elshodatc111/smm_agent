import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ArrowLeft, Cloud, Clock, FileText, ImagePlus, Sparkles, Upload, Wand2, X, ChevronLeft, ChevronRight, Eye, Pencil, Crop } from 'lucide-react'
import { Btn, Card, Collapse, Modal, PageHeader, Segmented, Spinner } from '../components/ui'
import { Field, FieldSchema, FormSchema, toFormData, useFormValues } from '../components/Fields'
import { RichEditor } from '../components/RichEditor'
import { CloudPicker, CloudFile } from '../components/CloudPicker'
import { ImageEditor } from '../components/ImageEditor'
import { clearDraftFiles, loadDraftFiles, saveDraftFiles } from '../lib/draftdb'
import { PostPreview, PvData, PvMedia } from '../components/PostPreview'
import { A } from '../components/Blocks'
import { useApp } from '../lib/app'
import { useToast } from '../lib/toast'
import { csrfToken, getJson, request } from '../lib/api'
import { cx, FMT, PLAT } from '../lib/format'
import { visLen } from '../lib/richtext'

const RATIO: Record<string, number> = { ig_4x5: 0.8, ig_1x1: 1, ig_191: 1.91, v_9x16: 9 / 16, h_16x9: 16 / 9 }
const TYPE_HINT: Record<string, string> = {
  image: '1 ta rasm (JPG/PNG/WEBP)', album: '2–10 ta rasm/video', carousel: '2–10 ta rasm/video', video: '1 ta video (MP4/MOV)',
  short: 'Vertikal (9:16) video, ≤60 soniya', reel: 'Vertikal (9:16) video, ≤90 soniya', story: 'Vertikal (9:16) rasm yoki video',
}
type Local = { key: string; file: File; url: string; kind: 'image' | 'video' }
type Cl = CloudFile

function parseButtons(raw: string, cols: number): string[][] {
  const rows: string[][] = []
  const flat: string[] = []
  raw.split('\n').map((l) => l.trim()).filter(Boolean).forEach((line) => {
    const parts = line.split('||').map((p) => p.trim()).filter(Boolean)
    if (parts.length > 1) rows.push(parts.map((p) => p.split('|')[0].trim()))
    else flat.push(line.split('|')[0].trim())
  })
  for (let i = 0; i < flat.length; i += cols) rows.push(flat.slice(i, i + cols))
  return rows
}
const kindOf = (f: File): 'image' | 'video' => (f.type.startsWith('video') || /\.(mp4|mov|m4v|webm)$/i.test(f.name) ? 'video' : 'image')

export function ContentForm({ d }: { d: any }) {
  const schema: FormSchema = d.form
  const { values, set, setValues } = useFormValues(schema)
  const { submit, busy } = useApp()
  const toast = useToast()
  const loc = useLocation()
  const F = useMemo(() => Object.fromEntries(schema.fields.map((f) => [f.name, f])) as Record<string, FieldSchema>, [schema])
  const [locals, setLocals] = useState<Local[]>([])
  const [clouds, setClouds] = useState<Cl[]>([])
  const [pick, setPick] = useState(false)
  const [drag, setDrag] = useState(false)
  const [mobileTab, setMobileTab] = useState<'edit' | 'preview'>('edit')
  const [exact, setExact] = useState<{ url?: string; err?: string; loading?: boolean } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [editFile, setEditFile] = useState<File | null>(null)
  const [editTarget, setEditTarget] = useState<{ src: 'l' | 'c' | 'e'; k: string } | null>(null)
  const fixed: string = d.fixed || ''
  const existing: PvMedia[] = d.existing_media || []

  // --- tanlangan akkauntlar / platformalar
  const accs: { pk: string; label: string; platform: string }[] = d.targets
  const chosen: string[] = values.targets || []
  const plats = useMemo(() => Array.from(new Set(chosen.map((pk) => d.acc_map[pk]?.platform).filter(Boolean))) as string[], [chosen, d.acc_map])
  // Yangi forma: bitta akkaunt bo'lsa avtomatik belgilanadi
  useEffect(() => {
    if (fixed && accs.length === 1 && !chosen.length && !d.bound && !d.item_id) set('targets', [accs[0].pk])
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // --- post turlari: tanlangan platformalar kesishmasi
  const typeField = F.media_type
  const allTypes = (typeField?.choices || []).map(([v, l]) => [String(v), l] as [string, string]).filter(([v]) => v)
  const okTypes = useMemo(() => {
    if (!plats.length) return allTypes.map(([v]) => v)
    return allTypes.map(([v]) => v).filter((t) => plats.every((p) => (d.allowed[p] || []).includes(t)))
  }, [plats, allTypes.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const mt: string = values.media_type
  useEffect(() => {
    if (okTypes.length && !okTypes.includes(mt)) set('media_type', okTypes[0])
  }, [okTypes.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  const noCommon = plats.length > 0 && okTypes.length === 0

  const multi = mt === 'album' || mt === 'carousel' || mt === 'text'
  const needMedia = mt !== 'text'
  const kinds = mt === 'video' || mt === 'short' || mt === 'reel' ? 'video' : mt === 'story' || multi ? 'image,video' : 'image'
  const accept = kinds === 'video' ? 'video/*' : kinds === 'image' ? 'image/*' : 'image/*,video/*'

  // --- fayllar
  const addFiles = (fl: File[]) => {
    const add = fl.filter((f) => /^(image|video)\//.test(f.type) || /\.(jpe?g|png|webp|gif|mp4|mov|m4v|webm)$/i.test(f.name)).map((file) => ({ key: Math.random().toString(36).slice(2), file, url: URL.createObjectURL(file), kind: kindOf(file) }))
    if (!add.length) return
    setLocals((cur) => (multi ? [...cur, ...add] : [add[add.length - 1]]))
    if (!multi) setClouds([])
    // Turni avtomatik aniqlash
    const all = [...(multi ? locals : []), ...add]
    if (mt === 'text') {
      const guess = all.length > 1 ? 'album' : all[0].kind === 'video' ? 'video' : 'image'
      const t = okTypes.includes(guess) ? guess : okTypes.find((x) => x !== 'text')
      if (t) set('media_type', t)
    }
  }
  const dropped = (e: React.DragEvent) => { e.preventDefault(); setDrag(false); addFiles(Array.from(e.dataTransfer.files)) }
  useEffect(() => () => locals.forEach((l) => URL.revokeObjectURL(l.url)), []) // eslint-disable-line react-hooks/exhaustive-deps
  const items = useMemo(() => [
    ...existing.map((m) => ({ k: 'e' + m.id, url: m.url, kind: m.kind, label: 'Biriktirilgan', src: 'e' as const })),
    ...locals.map((l) => ({ k: l.key, url: l.url, kind: l.kind, label: l.file.name, src: 'l' as const })),
    ...clouds.map((c) => ({ k: 'c' + c.id, url: c.url, kind: c.kind, label: c.name, src: 'c' as const })),
  ], [existing, locals, clouds])
  const move = (i: number, dir: number) => {
    // Faqat bir turdagi (mahalliy yoki bulut) fayllar tartibi o'zgaradi
    const it = items[i], nb = items[i + dir]
    if (!it || !nb || it.src !== nb.src) return
    if (it.src === 'l') setLocals((c) => { const a = [...c]; const x = a.findIndex((v) => v.key === it.k), y = a.findIndex((v) => v.key === nb.k); [a[x], a[y]] = [a[y], a[x]]; return a })
    if (it.src === 'c') setClouds((c) => { const a = [...c]; const x = a.findIndex((v) => 'c' + v.id === it.k), y = a.findIndex((v) => 'c' + v.id === nb.k); [a[x], a[y]] = [a[y], a[x]]; return a })
  }
  const remove = (it: (typeof items)[number]) => {
    if (it.src === 'l') setLocals((c) => c.filter((v) => v.key !== it.k))
    else if (it.src === 'c') setClouds((c) => c.filter((v) => 'c' + v.id !== it.k))
  }
  const startCrop = async (it: (typeof items)[number]) => {
    try {
      if (it.src === 'l') setEditFile(locals.find((l) => l.key === it.k)!.file)
      else {
        const r = await fetch(it.src === 'c' ? `/cloudflare/${it.k.slice(1)}/fayl/` : it.url, { credentials: 'same-origin' })
        if (!r.ok) throw new Error()
        const b = await r.blob()
        setEditFile(new File([b], it.label.length > 3 && it.src === 'c' ? it.label : 'rasm.jpg', { type: b.type || 'image/jpeg' }))
      }
      setEditTarget({ src: it.src, k: it.k })
    } catch { toast.push('error', 'Rasmni ochib bo\'lmadi. Qayta urinib ko\'ring.') }
  }
  const cropDone = (nf: File) => {
    const t = editTarget
    if (!t) return
    if (t.src === 'l') setLocals((c) => c.map((l) => (l.key === t.k ? { ...l, file: nf, url: URL.createObjectURL(nf) } : l)))
    else if (t.src === 'c') { setClouds((c) => c.filter((x) => 'c' + x.id !== t.k)); setLocals((c) => (multi ? [...c, { key: Math.random().toString(36).slice(2), file: nf, url: URL.createObjectURL(nf), kind: 'image' as const }] : [{ key: 'x', file: nf, url: URL.createObjectURL(nf), kind: 'image' as const }])) }
    else { const fd = new FormData(); fd.append('file', nf, nf.name); submit(`/kalendar/${d.item_id}/fayl/${t.k.slice(1)}/almashtir/`, fd, { stay: true }) }
  }
  // Tur o'zgarganda ortiqcha fayllar olib tashlanadi (bitta fayl turlari)
  useEffect(() => {
    if (needMedia && !multi) { setLocals((c) => c.slice(-1)); setClouds((c) => (locals.length ? [] : c.slice(-1))) }
    if (!needMedia) { setLocals([]); setClouds([]) }
  }, [mt]) // eslint-disable-line react-hooks/exhaustive-deps

  // --- o'lcham/kadr
  const sizeKey = values.media_size || 'orig'
  const ratio = RATIO[sizeKey] || 0
  const fit = values.fit_mode || 'pad'
  useEffect(() => {
    // Tur bo'yicha tavsiya etilgan o'lcham (foydalanuvchi qo'lda tanlamagan bo'lsa)
    if (sizeKey === 'orig' && ['reel', 'short', 'story'].includes(mt)) set('media_size', 'v_9x16')
  }, [mt]) // eslint-disable-line react-hooks/exhaustive-deps
  const crop = { x: Number(values.crop_x || 0.5), y: Number(values.crop_y || 0.5), z: Number(values.crop_zoom || 1) }
  const onCrop = (x: number | null, y: number | null, z: number | null) => setValues((v) => ({ ...v, ...(x !== null ? { crop_x: String(x) } : {}), ...(y !== null ? { crop_y: String(y) } : {}), ...(z !== null ? { crop_zoom: String(z) } : {}) }))

  // --- oldindan ko'rish
  const sel = useMemo(() => {
    const o: Record<string, { name: string; handle: string }[]> = {}
    chosen.forEach((pk) => { const a = d.acc_map[pk]; if (a) (o[a.platform] ||= []).push({ name: a.name, handle: a.handle }) })
    return o
  }, [chosen, d.acc_map])
  const media: PvMedia[] = items.filter((i) => i.kind).map((i) => ({ url: i.url, kind: i.kind as any }))
  const cols = Number(values.tg_cols || 2)
  const pv: PvData = { text: values.text || '', mt, sel, media, ytTitle: values.yt_title, ratio, fit, crop, buttons: parseButtons(values.tg_buttons || '', cols) }
  const only = fixed ? [fixed] : undefined

  const doExact = async () => {
    const first = items.find((i) => i.kind === 'image')
    if (!first) return
    setExact({ loading: true })
    const fd = new FormData()
    fd.append('size', sizeKey); fd.append('fit', fit); fd.append('cx', String(crop.x)); fd.append('cy', String(crop.y)); fd.append('cz', String(crop.z)); fd.append('plat', plats[0] || fixed || '')
    if (first.src === 'l') fd.append('file', locals.find((l) => l.key === first.k)!.file)
    else if (first.src === 'c') fd.append('cloud_id', first.k.slice(1))
    else fd.append('aid', first.k.slice(1))
    try {
      const r = await fetch('/kalendar/aniq-korinish/', { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrfToken() }, credentials: 'same-origin' })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Xato')
      setExact({ url: URL.createObjectURL(await r.blob()) })
    } catch (e: any) { setExact({ err: e.message || 'Xato' }) }
  }

  // --- AI va vaqt
  const [topic, setTopic] = useState('')
  const [ai, setAi] = useState<{ busy?: string; err?: string; variants?: string[]; hashtags?: string; why?: string; script?: { text: string; title: string; id: number } } | null>(null)
  const post = async (url: string, data: Record<string, string>) => (await request(url, { method: 'POST', body: data, silent: true })).data
  const firstPlat = plats[0] || fixed || 'telegram'
  const runAi = async (kind: 'matn' | 'ssenariy' | 'youtube') => {
    setAi({ busy: kind })
    try {
      const r = kind === 'matn' ? await post('/kalendar/ai/matn/', { platform: firstPlat, media_type: mt, topic, current: values.text || '' })
        : kind === 'ssenariy' ? await post('/kalendar/ai/ssenariy/', { platform: firstPlat, media_type: mt, topic })
          : await post('/kalendar/ai/youtube/', { media_type: mt, topic, text: values.text || '' })
      if (r.error) return setAi({ err: r.error })
      if (kind === 'youtube') {
        setValues((v) => ({ ...v, yt_title: r.title || '', yt_tags: r.tags || '', ...(r.privacy ? { yt_privacy: r.privacy } : {}) }))
        return setAi({ why: 'YouTube sarlavhasi va teglari to\'ldirildi. ' + (r.why || '') })
      }
      if (kind === 'ssenariy') return setAi({ script: { text: r.text, title: r.title, id: r.script_id } })
      setAi({ variants: r.variants, hashtags: r.hashtags, why: r.why })
    } catch { setAi({ err: 'Server bilan aloqa xatosi.' }) }
  }
  const useVariant = (v: string) => { set('text', ai?.hashtags && !v.includes('#') ? `${v}\n\n${ai.hashtags}` : v); setAi(null) }

  const [slots, setSlots] = useState<any>(null)
  const loadSlots = async () => {
    if (!plats.length) return setSlots({ error: 'Avval platformani belgilang.' })
    setSlots({ loading: true })
    try { setSlots(await getJson(`/kalendar/vaqt/?platform=${plats.join(',')}${d.item_id ? '&item=' + d.item_id : ''}`)) } catch { setSlots({ error: 'Server bilan aloqa xatosi.' }) }
  }

  // --- qoralama (brauzerda avtomatik saqlanadi)
  const dkey = 'draft:' + loc.pathname
  const [restored, setRestored] = useState(false)
  const draftReady = useRef(false)
  useEffect(() => {
    if (d.item_id) return
    try {
      const raw = localStorage.getItem(dkey)
      if (raw && !values.text && !values.title) { const o = JSON.parse(raw); setValues((v) => ({ ...v, text: o.text || '', title: o.title || '', tg_buttons: o.tg_buttons || v.tg_buttons })); setRestored(true) }
    } catch { /* ignore */ }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (d.item_id) return
    const t = setTimeout(() => { try { if (values.text || values.title) localStorage.setItem(dkey, JSON.stringify({ text: values.text, title: values.title, tg_buttons: values.tg_buttons })); else localStorage.removeItem(dkey) } catch { /* ignore */ } }, 500)
    return () => clearTimeout(t)
  }, [values.text, values.title, values.tg_buttons]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (d.item_id) return
    loadDraftFiles(dkey).then((fs) => { draftReady.current = true; if (fs.length) { setLocals(fs.map((file) => ({ key: Math.random().toString(36).slice(2), file, url: URL.createObjectURL(file), kind: kindOf(file) }))); setRestored(true) } })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!d.item_id && draftReady.current) saveDraftFiles(dkey, locals.map((l) => l.file)) }, [locals]) // eslint-disable-line react-hooks/exhaustive-deps

  // --- yuborish
  const save = async (e?: React.FormEvent) => {
    e?.preventDefault()
    const fd = toFormData(schema, values)
    locals.forEach((l) => fd.append('files', l.file, l.file.name))
    clouds.forEach((c) => fd.append('cloud_ids', String(c.id)))
    const res = await submit(loc.pathname + loc.search, fd)
    if (res && res.data?.kind !== 'content_form') { try { localStorage.removeItem(dkey) } catch { /* ignore */ } clearDraftFiles(dkey) }
  }
  const errs = [...schema.errors, ...schema.fields.filter((f) => f.errors.length && !['text', 'media_type', 'targets', 'scheduled_at'].includes(f.name)).map((f) => `${f.label}: ${f.errors.join(' ')}`)]
  const tgLen = visLen(values.text || '')
  const richOk = !plats.length || plats.includes('telegram')

  const edit = (
    <div className="space-y-3 min-w-0">
      {(errs.length > 0 || noCommon) && (
        <div className="rounded-lg border border-bad/40 bg-bad/10 text-bad px-3 py-2 text-[13px] space-y-0.5">
          {noCommon && <div>Tanlangan platformalar uchun umumiy post turi yo'q. Platformalarni alohida postlarda tanlang.</div>}
          {errs.map((m, i) => <div key={i}>{m}</div>)}
        </div>
      )}
      {restored && <div className="rounded-lg border border-line bg-surface2 px-3 py-1.5 text-[12.5px] flex items-center justify-between">Brauzerda saqlangan qoralama tiklandi.<button type="button" className="underline" onClick={() => { setValues((v) => ({ ...v, text: '', title: '' })); setLocals([]); setRestored(false); try { localStorage.removeItem(dkey) } catch { /* ignore */ } }}>Tozalash</button></div>}

      <Card pad={false}>
        <div className="p-3.5 space-y-3">
          <div>
            <div className="label">Qayerga nashr qilinadi{!fixed ? '' : ` — ${PLAT[fixed]?.name || fixed}`}</div>
            {accs.length ? (
              <div className="flex flex-wrap gap-2">
                {accs.map((a) => { const on = chosen.includes(a.pk); return (
                  <button type="button" key={a.pk} className={cx('chip', on && 'chip-on')} onClick={() => set('targets', on ? chosen.filter((x) => x !== a.pk) : [...chosen, a.pk])}>
                    <i className="w-2 h-2 rounded-full" style={{ background: PLAT[a.platform]?.color }} />{a.label}
                  </button>) })}
              </div>
            ) : <div className="text-[13px] text-muted">Akkaunt ulanmagan. <A to="/ulanishlar/">Akkaunt ulash</A> — usiz post qoralama bo'lib qoladi.</div>}
          </div>
          <div>
            <div className="label">Post turi</div>
            <Segmented items={allTypes.map(([v, l]) => ({ key: v, label: FMT[v] || l }))} value={mt} onChange={(k) => okTypes.includes(k) && set('media_type', k)} className={cx()} />
            {allTypes.some(([v]) => !okTypes.includes(v)) && <div className="help">{plats.length ? `Mumkin turlar: ${okTypes.map((t) => FMT[t] || t).join(', ')}` : ''}</div>}
          </div>
        </div>
      </Card>

      <Card pad={false}>
        <div className="p-3.5 space-y-3">
          {(
            <div>
              <div className="flex items-center justify-between mb-1"><div className="label !mb-0">Fayl{multi ? 'lar' : ''} <span className="font-normal text-muted">— {mt === 'text' ? "rasm yoki video qo'shsangiz post turi avtomatik tanlanadi" : TYPE_HINT[mt] || ''}</span></div></div>
              <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={dropped}
                className={cx('rounded-xl border-2 border-dashed p-3 transition', drag ? 'border-brand bg-brandsoft' : 'border-line bg-surface2/50')}>
                <div className="flex flex-wrap items-center gap-2">
                  <Btn size="sm" onClick={() => fileRef.current?.click()}><Upload className="w-3.5 h-3.5" /> Kompyuterdan tanlash</Btn>
                  <Btn size="sm" onClick={() => setPick(true)}><Cloud className="w-3.5 h-3.5" /> Cloudflare'dan</Btn>
                  <span className="text-[12.5px] text-muted">yoki faylni shu yerga tashlang</span>
                  <input ref={fileRef} type="file" hidden accept={accept} multiple={multi} onChange={(e) => { addFiles(Array.from(e.target.files || [])); e.target.value = '' }} />
                </div>
                {items.length > 0 && (
                  <div className="flex flex-wrap gap-2.5 mt-3">
                    {items.map((it, i) => (
                      <div key={it.k} className="w-[104px]">
                        <div className="relative aspect-square rounded-lg overflow-hidden bg-surface border border-line">
                          {it.kind === 'video' ? <video src={it.url} muted preload="metadata" className="w-full h-full object-cover" /> : <img src={it.url} alt="" className="w-full h-full object-cover" />}
                          <span className="absolute top-1 left-1 text-[10px] px-1.5 rounded bg-black/60 text-white">{i + 1}</span>
                          {it.kind === 'image' && <button type="button" aria-label="Kesish" title="Kesish" onClick={() => startCrop(it)} className="absolute bottom-1 left-1 h-6 px-1.5 rounded-md bg-black/65 text-white text-[11px] inline-flex items-center gap-1 hover:bg-brand"><Crop className="w-3 h-3" /> Kesish</button>}
                          {it.src !== 'e' && <button type="button" aria-label="Olib tashlash" onClick={() => remove(it)} className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white grid place-items-center hover:bg-bad"><X className="w-3 h-3" /></button>}
                        </div>
                        <div className="flex items-center justify-between mt-1 gap-1">
                          <span className="text-[11px] text-muted truncate">{it.src === 'c' ? '☁ ' : ''}{it.label}</span>
                          {multi && it.src !== 'e' && <span className="flex shrink-0"><button type="button" aria-label="Oldinga" disabled={i === 0 || items[i - 1].src !== it.src} onClick={() => move(i, -1)} className="disabled:opacity-30"><ChevronLeft className="w-3.5 h-3.5" /></button><button type="button" aria-label="Orqaga" disabled={i === items.length - 1 || items[i + 1].src !== it.src} onClick={() => move(i, 1)} className="disabled:opacity-30"><ChevronRight className="w-3.5 h-3.5" /></button></span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {!items.length && <div className="text-[12.5px] text-muted mt-2 flex items-center gap-1.5"><ImagePlus className="w-4 h-4" /> Hali fayl tanlanmagan.</div>}
              </div>
              {items.some((i) => i.kind === 'image') && (
                <div className="grid sm:grid-cols-2 gap-3 mt-3">
                  {F.media_size && <Field f={F.media_size} value={values.media_size} onChange={(v) => set('media_size', v)} />}
                  {F.fit_mode && sizeKey !== 'orig' && <Field f={F.fit_mode} value={values.fit_mode} onChange={(v) => set('fit_mode', v)} />}
                </div>
              )}
            </div>
          )}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="label !mb-0" htmlFor="id_text">Matn / caption</label>
              <span className={cx('text-[12px]', plats.includes('telegram') && tgLen > (needMedia ? 1024 : 4096) ? 'text-bad font-semibold' : 'text-muted')}>{tgLen} belgi</span>
            </div>
            <RichEditor id="id_text" value={values.text || ''} onChange={(v) => set('text', v)} rows={items.length ? 6 : 8} richOk={richOk} placeholder="Postning to'liq matni. #hashtag larni ham shu yerga yozing." />
            {F.text.errors.length > 0 && <div className="text-[12px] text-bad mt-1">{F.text.errors.join(' ')}</div>}
          </div>
          <div className="rounded-xl bg-surface2/60 border border-line p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand shrink-0" />
              <input className="input flex-1 min-w-[160px] h-8" placeholder="AI uchun mavzu (ixtiyoriy)…" value={topic} onChange={(e) => setTopic(e.target.value)} />
              <Btn size="sm" loading={ai?.busy === 'matn'} onClick={() => runAi('matn')}><Wand2 className="w-3.5 h-3.5" /> Matn yozish</Btn>
              {['video', 'reel', 'short', 'story'].includes(mt) && <Btn size="sm" loading={ai?.busy === 'ssenariy'} onClick={() => runAi('ssenariy')}><FileText className="w-3.5 h-3.5" /> Ssenariy</Btn>}
            </div>
            {ai?.err && <div className="text-[12.5px] text-bad mt-2">{ai.err}</div>}
            {ai?.variants && (
              <div className="mt-2 grid gap-2">
                {ai.variants.map((v, i) => <button key={i} type="button" onClick={() => useVariant(v)} className="text-left rounded-lg border border-line bg-surface p-2.5 text-[13px] whitespace-pre-wrap hover:border-brand transition"><b className="block text-[12px] mb-1">Variant {i + 1} — bosib matnga qo'ying</b>{v}</button>)}
                {ai.hashtags && <div className="help">Hashtaglar: {ai.hashtags}</div>}{ai.why && <div className="help">Nega: {ai.why}</div>}
              </div>
            )}
            {ai?.script && (
              <div className="mt-2 rounded-lg border border-line bg-surface p-2.5">
                <b className="text-[13px]">{ai.script.title || 'Ssenariy'}</b>
                <pre className="whitespace-pre-wrap text-[12.5px] max-h-60 overflow-auto my-2 font-sans">{ai.script.text}</pre>
                <div className="flex gap-2"><Btn size="sm" onClick={() => { set('notes', (values.notes ? values.notes + '\n\n' : '') + ai.script!.text); setAi({ why: 'Ssenariy ichki izohga saqlandi (nashrga chiqmaydi).' }) }}>Ichki izohga saqlash</Btn></div>
              </div>
            )}
            {ai?.why && !ai.variants && <div className="help">{ai.why}</div>}
          </div>
        </div>
      </Card>

      <Card pad={false}>
        <div className="p-3.5 space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <Field f={F.scheduled_at} value={values.scheduled_at} onChange={(v) => set('scheduled_at', v)} />
            <Field f={F.title} value={values.title} onChange={(v) => set('title', v)} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {F.auto_time && <Field f={F.auto_time} value={values.auto_time} onChange={(v) => set('auto_time', v)} />}
            <Btn size="sm" onClick={loadSlots} loading={!!slots?.loading}><Clock className="w-3.5 h-3.5" /> Eng yaxshi vaqtlarni ko'rsat</Btn>
          </div>
          {slots?.error && <div className="text-[12.5px] text-bad">{slots.error}</div>}
          {slots?.slots && Object.entries(slots.slots as Record<string, any[]>).map(([pl, list]) => (
            <div key={pl}>
              <div className="text-[12px] font-semibold text-muted mb-1">{PLAT[pl]?.name || pl}</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {!list.length && <span className="help">Bo'sh qulay vaqt topilmadi.</span>}
                {list.map((s) => <button key={s.value} type="button" onClick={() => set('scheduled_at', s.value)} className={cx('text-left rounded-lg border p-2 text-[12px] transition', values.scheduled_at === s.value ? 'border-brand bg-brandsoft' : 'border-line hover:border-brand/60')}><b className="block text-[13px]">{s.label}</b>Baho: {s.score}/100{s.data_based ? ' · statistika' : ' · umumiy'}<span className="block text-muted">{s.reason}</span></button>)}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {(plats.includes('youtube') || plats.includes('telegram')) && (
        <Card pad={false}>
          <div className="p-3.5 space-y-3">
            {plats.includes('telegram') && (
              <div>
                <div className="grid sm:grid-cols-[1fr_200px] gap-3">
                  <Field f={F.tg_buttons} value={values.tg_buttons} onChange={(v) => set('tg_buttons', v)} />
                  <Field f={F.tg_cols} value={values.tg_cols} onChange={(v) => set('tg_cols', v)} />
                </div>
                <div className="help">Telegram tugmalari. Bir qatorda ikkitasi uchun: <code>A | https://… || B | https://…</code></div>
              </div>
            )}
            {plats.includes('youtube') && (
              <div className="space-y-3">
                <div className="flex items-center justify-between"><div className="text-[13px] font-semibold">YouTube</div><Btn size="sm" loading={ai?.busy === 'youtube'} onClick={() => runAi('youtube')}><Wand2 className="w-3.5 h-3.5" /> AI bilan to'ldirish</Btn></div>
                <div className="grid sm:grid-cols-3 gap-3">
                  <Field f={F.yt_title} value={values.yt_title} onChange={(v) => set('yt_title', v)} className="sm:col-span-2" />
                  <Field f={F.yt_privacy} value={values.yt_privacy} onChange={(v) => set('yt_privacy', v)} />
                  <Field f={F.yt_tags} value={values.yt_tags} onChange={(v) => set('yt_tags', v)} className="sm:col-span-3" />
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      <Collapse title="Qo'shimcha: maqsad, mas'ul, ichki izoh" hint="ixtiyoriy">
        <div className="grid sm:grid-cols-2 gap-3">
          {['goal', 'hook_idea', 'cta', 'assignee', 'due_at'].filter((n) => F[n]).map((n) => <Field key={n} f={F[n]} value={values[n]} onChange={(v) => set(n, v)} />)}
          {F.brief && <Field f={F.brief} value={values.brief} onChange={(v) => set('brief', v)} className="sm:col-span-2" />}
          {F.notes && <Field f={F.notes} value={values.notes} onChange={(v) => set('notes', v)} className="sm:col-span-2" />}
        </div>
      </Collapse>
    </div>
  )

  return (
    <form onSubmit={save} className="pb-20 lg:pb-0">
      <PageHeader title={d.title} back={<A to={d.back} className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-fg mb-1"><ArrowLeft className="w-3.5 h-3.5" /> Orqaga</A>}
        actions={<><A to={d.back} className="btn">Bekor qilish</A><Btn variant="primary" type="submit" loading={busy}>Saqlash</Btn></>} />
      {d.plat_brief && <div className="mb-3"><Collapse title="Bu platforma bo'yicha tavsiyalar (statistikadan)"><div className="text-[12.5px] whitespace-pre-line">{d.plat_brief}</div></Collapse></div>}
      {d.tpl_list?.length > 0 && !d.item_id && <div className="flex flex-wrap items-center gap-2 mb-3 text-[12.5px]"><span className="text-muted">Shablon:</span>{d.tpl_list.slice(0, 8).map((t: any) => <A key={t.url} to={t.url} className="chip h-7 text-[12px]">{t.name}</A>)}</div>}

      <div className="lg:hidden mb-3"><Segmented items={[{ key: 'edit', label: <><Pencil className="w-3.5 h-3.5" /> Tahrirlash</> }, { key: 'preview', label: <><Eye className="w-3.5 h-3.5" /> Ko'rinish</> }]} value={mobileTab} onChange={setMobileTab} className="w-full [&>button]:flex-1 [&>button]:justify-center" /></div>
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_400px] gap-4 items-start">
        <div className={cx('min-w-0', mobileTab === 'preview' && 'hidden lg:block')}>{edit}</div>
        <aside className={cx('min-w-0 lg:sticky lg:top-[72px]', mobileTab === 'edit' && 'hidden lg:block')}>
          <Card title="Oldindan ko'rish" bodyClass="max-h-[calc(100vh-150px)] overflow-y-auto">
            <PostPreview data={pv} only={only} onCrop={onCrop} onExact={doExact} />
          </Card>
        </aside>
      </div>

      <div className="lg:hidden fixed bottom-14 inset-x-0 z-20 p-2.5 bg-surface/95 backdrop-blur border-t border-line flex gap-2">
        <A to={d.back} className="btn flex-1 justify-center">Bekor</A><Btn variant="primary" type="submit" loading={busy} className="flex-[2] justify-center">Saqlash</Btn>
      </div>

      <CloudPicker open={pick} onClose={() => setPick(false)} kinds={kinds} multi={multi} onPick={(fs) => {
        setClouds((c) => (multi ? [...c, ...fs.filter((f) => !c.some((x) => x.id === f.id))] : fs.slice(-1)))
        if (!multi) setLocals([])
        if (mt === 'text') { const g = fs.length > 1 ? 'album' : fs[0].kind === 'video' ? 'video' : 'image'; if (okTypes.includes(g)) set('media_type', g) }
      }} />
      <ImageEditor file={editFile} ratio={ratio} onClose={() => { setEditFile(null); setEditTarget(null) }} onDone={cropDone} />
      <Modal open={!!exact} onClose={() => setExact(null)} title="Aniq natija (nashrdagi kadr)" width={520}>
        {exact?.loading && <div className="py-10 flex justify-center"><Spinner className="w-6 h-6" /></div>}
        {exact?.err && <div className="text-bad text-[13px]">{exact.err}</div>}
        {exact?.url && <img src={exact.url} alt="" className="mx-auto max-h-[70vh] rounded-lg" />}
      </Modal>
    </form>
  )
}
