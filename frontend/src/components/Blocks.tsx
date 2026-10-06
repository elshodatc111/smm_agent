import { ReactNode, useRef } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useApp } from '../lib/app'
import { isAppPath } from '../lib/api'
import { cx } from '../lib/format'
import { Badge, Btn, Card, Empty, PageHeader, useConfirm } from './ui'
import { SimpleForm } from './Fields'
import { Chart, ChartSpec } from './Charts'

/* ---------- ichki/tashqi havola ---------- */
export function A({ to, children, className, ...rest }: { to: string; children: ReactNode; className?: string; [k: string]: any }) {
  if (isAppPath(to)) return <Link to={to} className={className} {...rest}>{children}</Link>
  return <a href={to} className={className} target={to.startsWith('http') || to.includes('/fayl/') || to.includes('/media/') ? '_blank' : undefined} rel="noopener" {...rest}>{children}</a>
}

/* ---------- Server amali tugmasi (POST / havola) ---------- */
export type ActionSpec = { label?: string; t?: string; post?: string | null; url?: string; href?: string; cls?: string; confirm?: string | null }
export function variantOf(cls = ''): '' | 'primary' | 'blue' | 'danger' {
  if (cls.includes('primary')) return 'primary'
  if (cls.includes('danger')) return 'danger'
  if (cls.includes('blue')) return 'blue'
  return ''
}
export function ActionButton({ a, size }: { a: ActionSpec; size?: 'sm' }) {
  const { submit, busy } = useApp()
  const confirm = useConfirm()
  const label = a.label || a.t || ''
  const v = variantOf(a.cls)
  const sm = size === 'sm' || (a.cls || '').includes('sm') ? 'sm' : undefined
  if (a.post) {
    return <Btn variant={v} size={sm} disabled={busy} onClick={async () => { if (a.confirm && !(await confirm(a.confirm, { danger: v === 'danger' }))) return; await submit(a.post!) }}>{label}</Btn>
  }
  const to = a.url || a.href || '#'
  return <A to={to} className={cx('btn', v && `btn-${v}`, sm && 'btn-sm')}>{label}</A>
}

/* ---------- Server HTML bloki: havolalar SPA ichida ochiladi ---------- */
export function Rich({ html, className }: { html: string; className?: string }) {
  const nav = useNavigate()
  const { submit } = useApp()
  const ref = useRef<HTMLDivElement>(null)
  const onClick = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a') as HTMLAnchorElement | null
    if (!a || e.metaKey || e.ctrlKey || a.target === '_blank') return
    const href = a.getAttribute('href') || ''
    if (href.startsWith('?')) { e.preventDefault(); nav(location.pathname.replace(/^\/app/, '') + href); return }
    if (isAppPath(href)) { e.preventDefault(); nav(href) }
  }
  const onSubmit = (e: React.FormEvent) => {
    const f = e.target as HTMLFormElement
    e.preventDefault()
    const act = f.getAttribute('action') || location.pathname.replace(/^\/app/, '')
    if ((f.method || 'get').toLowerCase() === 'get') { nav(act + '?' + new URLSearchParams(new FormData(f) as any).toString()); return }
    submit(act, new FormData(f))
  }
  return <div ref={ref} className={cx('rich', className)} onClick={onClick} onSubmit={onSubmit} dangerouslySetInnerHTML={{ __html: html }} />
}

/* ---------- Jadval ---------- */
type Cell = any
function CellView({ c }: { c: Cell }) {
  if (c === null || c === undefined || c === '') return <span className="text-muted">—</span>
  if (typeof c !== 'object') return <>{String(c)}</>
  if (c.post) return <ActionButton a={{ label: c.label || c.t, post: c.post, cls: `sm ${c.cls || ''}`, confirm: c.confirm }} />
  if (c.u) return <div><A to={c.u} className="font-medium text-info hover:underline">{c.t}</A>{c.sub && <div className="help mt-0">{c.sub}</div>}</div>
  if (c.b !== undefined && c.b !== null) return <div><Badge tone={c.b}>{c.t}</Badge>{c.sub && <div className="help mt-0.5">{c.sub}</div>}</div>
  if (c.t !== undefined) return <>{c.t}</>
  return <>{JSON.stringify(c)}</>
}

export function DataTable({ title, columns, rows, empty }: { title?: string | null; columns: string[]; rows: Cell[][]; empty?: string | null }) {
  const body = !rows.length ? (
    <Empty text={empty || "Ma'lumot yo'q"} />
  ) : (
    <>
      <div className="hidden md:block overflow-x-auto -mx-4">
        <table className="w-full text-[13.5px] min-w-[560px]">
          <thead><tr>{columns.map((c, i) => <th key={i} className="th">{c}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i} className="hover:bg-surface2/50">{r.map((c, j) => <td key={j} className="td"><CellView c={c} /></td>)}</tr>)}</tbody>
        </table>
      </div>
      <div className="md:hidden divide-y divide-line -mx-4">
        {rows.map((r, i) => (
          <div key={i} className="px-4 py-2.5 space-y-1">
            {r.map((c, j) => (columns[j] || (typeof c === 'object' && c?.post)) && c !== '' && c !== null ? (
              <div key={j} className="flex items-start justify-between gap-3 text-[13.5px]">
                {columns[j] && <span className="text-muted text-[12px] shrink-0 pt-px">{columns[j]}</span>}
                <span className={cx('min-w-0 break-words', !columns[j] && 'w-full')}><CellView c={c} /></span>
              </div>
            ) : null)}
          </div>
        ))}
      </div>
    </>
  )
  return title ? <Card title={title}>{body}</Card> : <Card className="overflow-hidden">{body}</Card>
}

/* ---------- Yorliqlar ---------- */
export function TabsBlock({ items }: { items: { label: string; url: string; active: boolean }[] }) {
  const nav = useNavigate()
  const loc = useLocation()
  return (
    <div className="inline-flex max-w-full overflow-x-auto no-scrollbar p-1 rounded-lg bg-surface2 border border-line gap-0.5">
      {items.map((i) => (
        <button key={i.label + i.url} onClick={() => nav(i.url.startsWith('?') ? loc.pathname + i.url : i.url)}
          className={cx('px-3 h-7 rounded-md text-[13px] font-medium whitespace-nowrap transition', i.active ? 'bg-surface shadow-card text-fg' : 'text-muted hover:text-fg')}>{i.label}</button>
      ))}
    </div>
  )
}

/* ---------- Umumiy sahifa (blocks) ---------- */
export function Blocks({ blocks, charts }: { blocks: any[]; charts?: ChartSpec[] }) {
  const byId = Object.fromEntries((charts || []).map((c) => [c.id, c]))
  return (
    <div className="space-y-4">
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'kv':
            return (
              <Card key={i} title={b.title}>
                <dl className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-x-5 gap-y-3">
                  {(b.items as [string, any][]).map(([k, v], j) => <div key={j} className="min-w-0"><dt className="text-muted text-[12px]">{k}</dt><dd className="font-medium break-words">{v === null || v === undefined || v === '' ? '—' : String(v)}</dd></div>)}
                </dl>
              </Card>
            )
          case 'text': return <Card key={i} title={b.title}><div className="whitespace-pre-wrap break-words leading-relaxed">{b.text}</div></Card>
          case 'html': return <Card key={i} title={b.title}><Rich html={b.html} /></Card>
          case 'table': return <DataTable key={i} title={b.title} columns={b.columns} rows={b.rows} empty={b.empty} />
          case 'form': return <Card key={i} title={b.title} className="max-w-[900px]">{b.intro && <p className="text-muted mb-3 text-[13px]" dangerouslySetInnerHTML={{ __html: b.intro }} />}<SimpleForm schema={b.form} action={b.action || location.pathname.replace(/^\/app/, '') + location.search} submitLabel={b.submit} hidden={b.hidden} cols={b.form.fields.length > 5 ? 2 : 1} /></Card>
          case 'chart': return byId[b.id] ? <Card key={i} title={b.title}><Chart spec={byId[b.id]} /></Card> : null
          case 'actions': return <Card key={i} title={b.title}><div className="flex flex-wrap gap-2">{(b.buttons || []).map((x: ActionSpec, j: number) => <ActionButton key={j} a={x} />)}</div></Card>
          case 'tabs': return <TabsBlock key={i} items={b.items} />
          default: return null
        }
      })}
    </div>
  )
}

export function GenericPage({ data }: { data: any }) {
  return (
    <>
      <PageHeader title={data.title} subtitle={data.subtitle} actions={(data.toolbar || []).map((t: ActionSpec, i: number) => <ActionButton key={i} a={t} />)} />
      <Blocks blocks={data.blocks || []} charts={data.charts} />
    </>
  )
}
