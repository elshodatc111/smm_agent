import { useRef, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowUp, BarChart3, Cloud, Copy, ExternalLink, Pencil, Replace, Trash2, Upload, Send, Bookmark } from 'lucide-react'
import { ActionButton, A, Rich } from '../components/Blocks'
import { Badge, Btn, Card, Empty, PageHeader, Segmented, useConfirm } from '../components/ui'
import { PostPreview, PvData } from '../components/PostPreview'
import { CloudPicker } from '../components/CloudPicker'
import { useApp } from '../lib/app'
import { bytes, cx, FMT, PLAT, statusTone } from '../lib/format'
import { richHtml } from '../lib/richtext'

type Tab = 'info' | 'files' | 'task' | 'results' | 'history'

function KV({ k, v }: { k: string; v?: string }) {
  if (!v) return null
  return <div className="grid grid-cols-[110px_1fr] gap-2 text-[13px] py-1"><span className="text-muted">{k}</span><span className="whitespace-pre-wrap break-words">{v}</span></div>
}

function Files({ d }: { d: any }) {
  const { submit, busy } = useApp()
  const confirm = useConfirm()
  const [pick, setPick] = useState(false)
  const up = useRef<HTMLInputElement>(null)
  const rep = useRef<HTMLInputElement>(null)
  const [repId, setRepId] = useState<number | null>(null)
  const base = `/kalendar/${d.id}`
  const add = (fl: File[]) => { if (!fl.length) return; const fd = new FormData(); fl.forEach((f) => fd.append('files', f, f.name)); submit(`${base}/fayl/`, fd) }
  return (
    <div className="space-y-3">
      {d.can_edit && (
        <div className="flex flex-wrap gap-2">
          <Btn size="sm" loading={busy} onClick={() => up.current?.click()}><Upload className="w-3.5 h-3.5" /> Kompyuterdan qo'shish</Btn>
          <Btn size="sm" onClick={() => setPick(true)}><Cloud className="w-3.5 h-3.5" /> Cloudflare'dan</Btn>
          <input ref={up} type="file" hidden multiple accept="image/*,video/*" onChange={(e) => { add(Array.from(e.target.files || [])); e.target.value = '' }} />
          <input ref={rep} type="file" hidden accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f && repId) { const fd = new FormData(); fd.append('file', f, f.name); submit(`${base}/fayl/${repId}/almashtir/`, fd) } e.target.value = '' }} />
        </div>
      )}
      {!d.assets.length ? <Empty text="Hali fayl biriktirilmagan." /> : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {d.assets.map((a: any, i: number) => (
            <div key={a.id} className="rounded-xl border border-line overflow-hidden bg-surface">
              <div className="aspect-[4/3] bg-surface2">{a.kind === 'video' ? <video src={a.url} controls preload="metadata" className="w-full h-full object-cover" /> : a.kind === 'image' ? <img src={a.url} alt="" className="w-full h-full object-cover" /> : <div className="h-full grid place-items-center text-muted text-[12px]">{a.kind}</div>}</div>
              <div className="p-2">
                <div className="text-[12px] font-medium truncate">{a.name}</div>
                <div className="text-[11px] text-muted">{bytes(a.size)}</div>
                {d.can_edit && (
                  <div className="flex gap-1 mt-1.5">
                    <Btn size="icon" aria-label="Yuqoriga" disabled={i === 0 || busy} onClick={() => submit(`${base}/fayl/${a.id}/surish/`, { dir: 'up' })}><ArrowUp className="w-3.5 h-3.5" /></Btn>
                    <Btn size="icon" aria-label="Pastga" disabled={i === d.assets.length - 1 || busy} onClick={() => submit(`${base}/fayl/${a.id}/surish/`, { dir: 'down' })}><ArrowDown className="w-3.5 h-3.5" /></Btn>
                    {a.kind === 'image' && <Btn size="icon" aria-label="Almashtirish" title="Tahrirlangan rasm bilan almashtirish" onClick={() => { setRepId(a.id); rep.current?.click() }}><Replace className="w-3.5 h-3.5" /></Btn>}
                    <Btn size="icon" variant="danger" aria-label="O'chirish" className="ml-auto" onClick={async () => { if (await confirm(`«${a.name}» postdan olib tashlansinmi?`, { danger: true })) submit(`${base}/fayl/${a.id}/ochir/`) }}><Trash2 className="w-3.5 h-3.5" /></Btn>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      <CloudPicker open={pick} onClose={() => setPick(false)} multi onPick={(fs) => { const fd = new FormData(); fs.forEach((f) => fd.append('cloud_ids', String(f.id))); submit(`${base}/fayl/`, fd) }} />
    </div>
  )
}

function Task({ d }: { d: any }) {
  const { submit, busy } = useApp()
  const t = d.task
  const [assignee, setAssignee] = useState('')
  const [due, setDue] = useState(d.due_local || '')
  const [brief, setBrief] = useState(d.brief || '')
  const [text, setText] = useState('')
  const base = `/kalendar/${d.id}`
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-muted">Vazifa holati:</span><Badge tone={t.cls === 'ok' ? 'ok' : t.cls === 'bad' ? 'bad' : t.cls === 'warn' ? 'warn' : ''}>{t.label || '—'}</Badge>
        {t.late && <Badge tone="bad">Muddat o'tgan</Badge>}{t.due_text && <span className="text-[12.5px] text-muted">Muddat: {t.due_text}</span>}
        <span className="flex gap-2 ml-auto">{t.steps.map((s: any) => <Btn key={s.key} size="sm" variant={s.cls === 'primary' ? 'primary' : s.cls === 'danger' ? 'danger' : s.cls === 'blue' ? 'blue' : ''} disabled={busy} onClick={() => submit(`${base}/vazifa/holat/${s.key}/`)}>{s.label}</Btn>)}</span>
      </div>
      {t.can_assign && (
        <form className="grid sm:grid-cols-2 gap-3 rounded-xl border border-line p-3" onSubmit={(e) => { e.preventDefault(); submit(`${base}/vazifa/`, { assignee, due_at: due, brief }) }}>
          <div><label className="label">Mas'ul</label><select className="input" value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">{d.info.assignee !== '—' ? `Hozir: ${d.info.assignee}` : 'Tanlanmagan'}</option>{d.staff.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
          <div><label className="label">Muddat</label><input className="input" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} /></div>
          <div className="sm:col-span-2"><label className="label">Topshiriq</label><textarea className="input" rows={2} value={brief} onChange={(e) => setBrief(e.target.value)} /></div>
          <div className="sm:col-span-2"><Btn variant="primary" type="submit" loading={busy}>Vazifani saqlash</Btn></div>
        </form>
      )}
      <div>
        <div className="text-[13px] font-semibold mb-2">Izohlar ({d.comments.length})</div>
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {d.comments.map((c: any, i: number) => (
            <div key={i} className={cx('rounded-lg px-3 py-2 text-[13px]', c.kind === 'system' ? 'bg-surface2 text-muted' : 'border border-line')}>
              <div className="text-[11.5px] text-muted mb-0.5"><b className="text-fg">{c.user}</b> · {c.at}</div><div className="whitespace-pre-wrap">{c.text}</div>
            </div>
          ))}
          {!d.comments.length && <div className="text-muted text-[13px]">Izoh yo'q.</div>}
        </div>
        {d.can_comment && (
          <form className="flex gap-2 mt-2" onSubmit={async (e) => { e.preventDefault(); if (text.trim()) { await submit(`${base}/izoh/`, { text }); setText('') } }}>
            <input className="input" placeholder="Izoh yozing…" value={text} onChange={(e) => setText(e.target.value)} /><Btn variant="primary" type="submit" disabled={!text.trim() || busy}><Send className="w-4 h-4" /></Btn>
          </form>
        )}
      </div>
    </div>
  )
}

export function ContentDetail({ d }: { d: any }) {
  const { submit } = useApp()
  const [tab, setTab] = useState<Tab>('info')
  const base = `/kalendar/${d.id}`
  const pv: PvData = { text: d.pv.text, mt: d.pv.mt, sel: d.pv.sel, media: d.pv.media, ytTitle: d.pv.ytTitle, ratio: d.pv.ratio, fit: d.pv.fit, crop: d.pv.crop, buttons: d.pv.buttons }
  const plats = Object.keys(d.pv.sel)
  return (
    <div>
      <PageHeader
        back={<A to="/kalendar/" className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-fg mb-1"><ArrowLeft className="w-3.5 h-3.5" /> Kalendar</A>}
        title={d.title}
        subtitle={<span className="inline-flex flex-wrap items-center gap-2"><Badge tone={statusTone(d.status)}>{d.status_label}</Badge><span>{d.format}</span><span>· {d.scheduled}</span><Badge tone={d.rule_cls}>{d.rule_label}</Badge>{d.business && <span>· {d.business}</span>}</span>}
        actions={<>
          {d.can_edit && <A to={`${base}/tahrir/`} className="btn"><Pencil className="w-4 h-4" /> Tahrirlash</A>}
          {d.can_create && <Btn onClick={() => submit(`${base}/nusxa/`)}><Copy className="w-4 h-4" /> Nusxa</Btn>}
          {d.can_create && <Btn onClick={() => submit(`${base}/shablon/`)} title="Shablon sifatida saqlash"><Bookmark className="w-4 h-4" /></Btn>}
        </>} />

      {d.ai_draft && <div className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-[13px] mb-3 flex items-center justify-between gap-3">AI yozgan qoralama — nashrdan oldin ko'rib chiqing.<Btn size="sm" onClick={() => submit(`${base}/ai-korildi/`)}>Ko'rib chiqdim</Btn></div>}
      <div className="flex flex-wrap gap-2 mb-3">{d.acts.map((a: any, i: number) => <ActionButton key={i} a={{ label: a.label, post: a.post, cls: a.cls, confirm: a.confirm }} />)}</div>
      {d.probs.length > 0 && (
        <div className="rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 mb-3 text-[13px] space-y-0.5">
          {d.probs.map((p: any, i: number) => <div key={i}><b>{PLAT[p.platform]?.name || p.platform}</b>: {p.msg}</div>)}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] gap-4 items-start">
        <div className="min-w-0 space-y-3">
          <Segmented<Tab> items={[{ key: 'info', label: 'Umumiy' }, { key: 'files', label: 'Fayllar', badge: <span className="text-[11px] text-muted">{d.assets.length}</span> }, { key: 'task', label: 'Vazifa', badge: <span className="text-[11px] text-muted">{d.comments.length}</span> }, { key: 'results', label: 'Natijalar' }, { key: 'history', label: 'Tarix' }]} value={tab} onChange={setTab} />
          <Card>
            {tab === 'info' && (
              <div className="space-y-4">
                <div>
                  <div className="text-[12px] font-semibold text-muted mb-1">Matn</div>
                  {d.text ? <div className="tgtext text-[14px] leading-relaxed whitespace-pre-wrap break-words" dangerouslySetInnerHTML={{ __html: richHtml(d.text) }} /> : <div className="text-muted text-[13px]">Matn yo'q.</div>}
                </div>
                <div>
                  <div className="text-[12px] font-semibold text-muted mb-1">Qayerga nashr qilinadi</div>
                  {d.targets.length ? (
                    <div className="space-y-1.5">{d.targets.map((t: any, i: number) => (
                      <div key={i} className="flex flex-wrap items-center gap-2 text-[13px] rounded-lg border border-line px-3 py-2">
                        <i className="w-2 h-2 rounded-full" style={{ background: PLAT[t.platform]?.color }} /><b>{t.account}</b><Badge tone={statusTone(t.status)}>{t.status_label}</Badge>
                        {t.published_at && <span className="text-muted text-[12px]">{t.published_at}</span>}
                        {t.url && <a href={t.url} target="_blank" rel="noopener" className="text-info inline-flex items-center gap-1 text-[12px]"><ExternalLink className="w-3 h-3" /> Ochish</a>}
                        {t.error && <span className="text-bad text-[12px] w-full">{t.error}</span>}
                      </div>))}</div>
                  ) : <div className="text-muted text-[13px]">Platforma tanlanmagan — post qoralama bo'lib qoladi. «Tahrirlash» orqali tanlang.</div>}
                </div>
                <div className="divide-y divide-line/70">
                  <KV k="Muallif" v={d.info.author} /><KV k="Mas'ul" v={d.info.assignee !== '—' ? d.info.assignee : ''} /><KV k="Maqsad" v={d.info.goal} /><KV k="Hook" v={d.info.hook} /><KV k="CTA" v={d.info.cta} /><KV k="Topshiriq" v={d.info.brief} /><KV k="Ichki izoh" v={d.info.notes} />
                </div>
              </div>
            )}
            {tab === 'files' && <Files d={d} />}
            {tab === 'task' && <Task d={d} />}
            {tab === 'results' && (
              <div className="space-y-3">
                {d.posts.length > 0 && <div className="flex flex-wrap gap-2">{d.posts.map((p: any) => <A key={p.id} to={`/tahlil/post/${p.id}/`} className="btn btn-primary"><BarChart3 className="w-4 h-4" /> {PLAT[p.platform]?.name || p.platform} statistikasi va AI tahlil</A>)}</div>}
                {d.results.length ? d.results.map((r: any, i: number) => (
                  <div key={i} className="rounded-lg border border-line p-3 text-[13px]"><div className="flex items-center gap-2 mb-1"><b>{r.plat}</b><Badge>{r.win}</Badge><span className="text-muted text-[12px]">{r.at}</span>{r.url && <a className="ml-auto text-info text-[12px]" href={r.url} target="_blank" rel="noopener">Postni ochish</a>}</div><div className="whitespace-pre-wrap">{r.text}</div></div>
                )) : !d.posts.length && <Empty text="Post nashr qilingach, natijalar va statistika shu yerda ko'rinadi." />}
              </div>
            )}
            {tab === 'history' && (d.history.length ? <div className="space-y-2 max-h-[60vh] overflow-y-auto">{d.history.map((h: any, i: number) => <div key={i} className="text-[13px] flex gap-3"><span className="text-muted text-[12px] w-32 shrink-0">{h.at}</span><span><b>{h.who}</b> — {h.what}{h.detail ? <span className="text-muted"> · {h.detail}</span> : null}</span></div>)}</div> : <Empty text="Tarix bo'sh." />)}
          </Card>
        </div>
        <aside className="lg:sticky lg:top-[72px]"><Card title="Oldindan ko'rish"><PostPreview data={pv} only={plats.length ? plats : undefined} /></Card></aside>
      </div>
    </div>
  )
}
