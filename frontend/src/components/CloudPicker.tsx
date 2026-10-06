import { useEffect, useState } from 'react'
import { Cloud, Search } from 'lucide-react'
import { getJson } from '../lib/api'
import { Btn, Empty, Modal, Spinner } from './ui'
import { cx } from '../lib/format'

export type CloudFile = { id: number; name: string; kind: 'image' | 'video'; url: string; size?: string; tags?: string[]; post?: string; at?: string; ready?: boolean }

/** Cloudflare omboridagi fayllardan tanlash oynasi (post formasida va boshqa joylarda). */
export function CloudPicker({ open, onClose, kinds = 'image,video', multi, onPick }: { open: boolean; onClose: () => void; kinds?: string; multi?: boolean; onPick: (files: CloudFile[]) => void }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<CloudFile[] | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<CloudFile[]>([])

  useEffect(() => {
    if (!open) return
    setSel([]); setRows(null); setErr('')
    const t = setTimeout(() => {
      getJson(`/cloudflare/tanlash/?kind=${encodeURIComponent(kinds)}&q=${encodeURIComponent(q)}`)
        .then((r) => (r.error ? setErr(r.error) : setRows(r.files)))
        .catch(() => setErr('Server bilan aloqa xatosi.'))
    }, q ? 250 : 0)
    return () => clearTimeout(t)
  }, [open, q, kinds])

  const toggle = (f: CloudFile) => {
    if (!f.ready) return
    setSel((s) => (multi ? (s.some((x) => x.id === f.id) ? s.filter((x) => x.id !== f.id) : [...s, f]) : [f]))
  }
  return (
    <Modal open={open} onClose={onClose} title={<span className="inline-flex items-center gap-2"><Cloud className="w-4 h-4" /> Cloudflare'dan tanlash</span>} width={760}
      footer={<><span className="text-muted text-[12.5px] mr-auto">{sel.length ? `${sel.length} ta tanlandi` : multi ? "Bir nechta fayl tanlash mumkin" : 'Faylni bosing'}</span><Btn onClick={onClose}>Bekor qilish</Btn><Btn variant="primary" disabled={!sel.length} onClick={() => { onPick(sel); onClose() }}>Biriktirish</Btn></>}>
      <div className="relative mb-3">
        <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted" />
        <input className="input pl-9" placeholder="Nomi, teg yoki post bo'yicha qidirish…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      </div>
      {err ? <div className="text-bad text-[13px]">{err}</div> : rows === null ? <div className="py-10 flex justify-center"><Spinner className="w-6 h-6" /></div> : !rows.length ? <Empty text="Fayl topilmadi. Cloudflare bo'limidan fayl yuklang." /> : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 max-h-[52vh] overflow-y-auto pr-1">
          {rows.map((f) => {
            const on = sel.some((x) => x.id === f.id)
            return (
              <button type="button" key={f.id} onClick={() => toggle(f)} disabled={!f.ready}
                className={cx('text-left rounded-xl border overflow-hidden transition bg-surface', on ? 'border-brand ring-2 ring-brand/30' : 'border-line hover:border-brand/50', !f.ready && 'opacity-50')}>
                <div className="aspect-[4/3] bg-surface2 overflow-hidden">
                  {f.ready ? (f.kind === 'video' ? <video src={f.url} muted preload="metadata" className="w-full h-full object-cover" /> : <img src={f.url} alt="" loading="lazy" className="w-full h-full object-cover" />) : <div className="w-full h-full grid place-items-center text-[12px] text-muted">Yuklanmoqda…</div>}
                </div>
                <div className="px-2 py-1.5"><div className="truncate text-[12px] font-medium">{f.name}</div><div className="text-[11px] text-muted truncate">{f.size}{f.post ? ` · ${f.post}` : ''}</div></div>
              </button>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
