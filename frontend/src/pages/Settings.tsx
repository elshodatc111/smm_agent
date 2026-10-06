import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BookOpen, Check, ImagePlus, Moon, Palette, Plug, Save, Sun, Trash2 } from 'lucide-react'
import { Blocks } from '../components/Blocks'
import { Field, FieldSchema, toFormData, useFormValues } from '../components/Fields'
import { Badge, Btn, Card, PageHeader } from '../components/ui'
import { useApp } from '../lib/app'
import { cx } from '../lib/format'

const STATUS: Record<string, [string, string]> = { ok: ['Ulangan', 'ok'], partial: ['Qisman', 'warn'], empty: ['Kiritilmagan', ''] }

function BrandCard({ brand, can }: { brand: any; can: boolean }) {
  const { submit, busy } = useApp()
  const [name, setName] = useState(brand.name)
  const [color, setColor] = useState(brand.brand_color)
  const [theme, setTheme] = useState(brand.theme)
  const [file, setFile] = useState<File | null>(null)
  const [remove, setRemove] = useState(false)
  const [prev, setPrev] = useState('')
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!file) return setPrev(''); const u = URL.createObjectURL(file); setPrev(u); return () => URL.revokeObjectURL(u) }, [file])
  const logo = remove ? '' : prev || brand.logo
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const fd = new FormData()
    fd.append('name', name); fd.append('color', color); fd.append('theme', theme)
    if (file) fd.append('logo', file, file.name)
    if (remove) fd.append('remove_logo', '1')
    await submit('/sozlamalar/brend/', fd, { stay: true })
    setFile(null); setRemove(false)
  }
  const swatch = ['#E11D2E', '#2563EB', '#7C3AED', '#059669', '#EA580C', '#0F172A']
  return (
    <Card title={<span className="inline-flex items-center gap-2"><Palette className="w-4 h-4" /> Brend: nom, logotip, rang</span>}>
      <form onSubmit={save} className="grid grid-cols-1 md:grid-cols-[1fr_300px] gap-5">
        <div className="space-y-3.5">
          <div><label className="label">Tizim nomi</label><input className="input" value={name} maxLength={60} disabled={!can} onChange={(e) => setName(e.target.value)} /><div className="help">Yon panel, brauzer sarlavhasi va kirish sahifasida ko'rinadi.</div></div>
          <div>
            <label className="label">Logotip</label>
            <div className="flex items-center gap-3">
              <div className="w-16 h-16 rounded-xl border border-line bg-surface2 grid place-items-center overflow-hidden">{logo ? <img src={logo} alt="" className="max-w-full max-h-full object-contain" /> : <ImagePlus className="w-6 h-6 text-muted" />}</div>
              <div className="flex flex-wrap gap-2">
                <Btn size="sm" disabled={!can} onClick={() => ref.current?.click()}>Logotip yuklash</Btn>
                {(brand.logo || file) && !remove && <Btn size="sm" disabled={!can} onClick={() => { setFile(null); setRemove(!!brand.logo) }}><Trash2 className="w-3.5 h-3.5" /> Olib tashlash</Btn>}
                <input ref={ref} type="file" hidden accept=".png,.jpg,.jpeg,.webp,.svg" onChange={(e) => { setFile(e.target.files?.[0] || null); setRemove(false); e.target.value = '' }} />
              </div>
            </div>
            <div className="help">PNG, JPG, WEBP yoki SVG · 2 MB gacha.</div>
          </div>
          <div className="grid sm:grid-cols-2 gap-3.5">
            <div>
              <label className="label">Asosiy rang</label>
              <div className="flex gap-2"><input type="color" disabled={!can} className="h-9 w-12 rounded-lg border border-line bg-surface p-1" value={color} onChange={(e) => setColor(e.target.value.toUpperCase())} /><input className="input" value={color} disabled={!can} onChange={(e) => setColor(e.target.value)} /></div>
              <div className="flex gap-1.5 mt-2">{swatch.map((c) => <button key={c} type="button" aria-label={c} disabled={!can} onClick={() => setColor(c)} className={cx('w-6 h-6 rounded-full border-2', color.toUpperCase() === c ? 'border-fg' : 'border-transparent')} style={{ background: c }} />)}</div>
            </div>
            <div>
              <label className="label">Standart mavzu</label>
              <div className="flex gap-2">{[['light', 'Yorug‘', Sun], ['dark', 'Qorong‘i', Moon]].map(([k, l, Ic]: any) => <button key={k} type="button" disabled={!can} onClick={() => setTheme(k)} className={cx('chip flex-1 justify-center', theme === k && 'chip-on')}><Ic className="w-3.5 h-3.5" />{l}</button>)}</div>
            </div>
          </div>
          {can && <Btn variant="primary" type="submit" loading={busy}><Save className="w-4 h-4" /> Brendni saqlash</Btn>}
        </div>
        <div>
          <div className="label">Ko'rinishi</div>
          <div className="rounded-xl border border-line overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2.5 border-b border-line bg-surface">
              {logo ? <img src={logo} alt="" className="w-7 h-7 object-contain" /> : <span className="w-7 h-7 rounded-lg grid place-items-center text-white text-[13px] font-bold" style={{ background: color }}>{(name || 'S')[0]}</span>}
              <b className="text-[14px] truncate">{name || 'Tizim nomi'}</b>
            </div>
            <div className="p-3 space-y-2 bg-surface2/50"><button type="button" className="h-8 px-3 rounded-lg text-white text-[13px] font-semibold" style={{ background: color }}>Asosiy tugma</button><div className="h-2 rounded-full bg-line"><div className="h-2 rounded-full w-2/3" style={{ background: color }} /></div></div>
          </div>
        </div>
      </form>
    </Card>
  )
}

export function Settings({ d }: { d: any }) {
  const loc = useLocation()
  const { submit, busy } = useApp()
  const { values, set } = useFormValues(d.form)
  const F: Record<string, FieldSchema> = Object.fromEntries(d.form.fields.map((f: FieldSchema) => [f.name, f]))
  const [dirty, setDirty] = useState(false)
  useEffect(() => { setDirty(false) }, [d.tab])
  const active = d.tabs.find((t: any) => t.key === d.tab)
  const hasFields = d.sections.some((s: any) => s.fields.length)
  const save = async (e?: React.FormEvent) => { e?.preventDefault(); const r = await submit(loc.pathname + loc.search, toFormData(d.form, values), { stay: true }); if (r) setDirty(false) }

  return (
    <div>
      <PageHeader title="Sozlamalar" subtitle={active?.desc} />
      <div className="grid grid-cols-1 lg:grid-cols-[210px_minmax(0,1fr)] gap-4 items-start">
        <nav className="flex lg:flex-col gap-1 overflow-x-auto no-scrollbar lg:sticky lg:top-[72px] -mx-1 px-1" aria-label="Sozlamalar bo'limlari">
          {d.tabs.map((t: any) => (
            <Link key={t.key} to={`/sozlamalar/?tab=${t.key}`} className={cx('px-3 h-9 rounded-lg text-[13.5px] font-medium whitespace-nowrap inline-flex items-center transition', t.key === d.tab ? 'bg-brandsoft text-fg font-semibold' : 'text-muted hover:text-fg hover:bg-surface2')}>{t.label}</Link>
          ))}
        </nav>
        <div className="space-y-3 min-w-0 pb-16">
          {d.brand && <BrandCard brand={d.brand} can={d.can_edit} />}
          <form onSubmit={save} className="space-y-3" onChange={() => setDirty(true)}>
          {d.sections.map((s: any, i: number) => {
            const st = s.status ? STATUS[s.status] : null
            const fields = s.fields.map((n: string) => F[n]).filter(Boolean)
            if (!fields.length) return null
            return (
              <Card key={i} title={<span className="inline-flex items-center gap-2">{s.title}{st && <Badge tone={st[1]}>{st[0]}</Badge>}</span>}
                actions={<>
                  {s.guide && <Link to={`/yoriqnoma/${s.guide.slug}/`} className="btn btn-sm"><BookOpen className="w-3.5 h-3.5" /> Qanday ulanadi?</Link>}
                  {s.test && <Btn size="sm" disabled={busy} onClick={() => submit(s.test.post, undefined, { stay: true })}><Plug className="w-3.5 h-3.5" /> {s.test.label}</Btn>}
                </>}>
                {s.desc && <p className="text-[13px] text-muted mb-3">{s.desc}</p>}
                <div className="grid sm:grid-cols-2 gap-3.5">
                  {fields.map((f: FieldSchema) => <Field key={f.name} f={{ ...f, disabled: f.disabled || !d.can_edit }} value={values[f.name]} onChange={(v) => { set(f.name, v) }} className={f.kind === 'textarea' ? 'sm:col-span-2' : ''} />)}
                </div>
              </Card>
            )
          })}
          {hasFields && d.can_edit && (
            <div className="sticky bottom-3 z-10 flex items-center justify-end gap-3 rounded-xl border border-line bg-surface/95 backdrop-blur px-4 py-2.5 shadow-card">
              <span className="text-[12.5px] text-muted mr-auto">{dirty ? 'Saqlanmagan o‘zgarishlar bor' : <span className="inline-flex items-center gap-1"><Check className="w-3.5 h-3.5 text-ok" /> Hammasi saqlangan</span>}</span>
              <Btn variant="primary" type="submit" loading={busy}><Save className="w-4 h-4" /> Saqlash</Btn>
            </div>
          )}
          </form>
          {d.extra?.length > 0 && <Blocks blocks={d.extra} />}
        </div>
      </div>
    </div>
  )
}
