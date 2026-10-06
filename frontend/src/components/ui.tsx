import { ReactNode, useEffect, useRef, useState, createContext, useContext, useCallback, ButtonHTMLAttributes } from 'react'
import { X, Loader2, ChevronDown, Inbox } from 'lucide-react'
import { cx } from '../lib/format'

export function Spinner({ className = '' }: { className?: string }) {
  return <Loader2 className={cx('w-4 h-4 animate-spin', className)} />
}

export function Btn({ variant = '', size = '', loading, className = '', children, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: '' | 'primary' | 'blue' | 'danger' | 'ghost'; size?: '' | 'sm' | 'icon'; loading?: boolean }) {
  const v = { '': '', primary: 'btn-primary', blue: 'btn-blue', danger: 'btn-danger', ghost: 'btn-ghost' }[variant]
  return (
    <button type="button" {...p} disabled={p.disabled || loading} className={cx('btn', v, size === 'sm' && 'btn-sm', size === 'icon' && 'btn-icon', className)}>
      {loading && <Spinner />}
      {children}
    </button>
  )
}

export function Badge({ tone = '', children, className = '' }: { tone?: string; children: ReactNode; className?: string }) {
  const t = { ok: 'badge-ok', warn: 'badge-warn', bad: 'badge-bad', blue: 'badge-blue' }[tone as 'ok'] || ''
  return <span className={cx('badge', t, className)}>{children}</span>
}

export function Card({ title, actions, children, className = '', pad = true, bodyClass = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean; bodyClass?: string }) {
  return (
    <section className={cx('card', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 px-4 pt-3 pb-2">
          <h2 className="font-semibold text-[14.5px] leading-tight">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={cx(pad && (title || actions ? 'px-4 pb-4' : 'p-4'), bodyClass)}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-4">
      <div className="min-w-0">
        {back}
        <h1 className="h-title truncate">{title}</h1>
        {subtitle && <div className="text-muted text-[13px] mt-0.5">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Empty({ text, icon, action }: { text: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-2 py-8 text-muted">
      {icon || <Inbox className="w-8 h-8 opacity-50" />}
      <div className="text-[13.5px] max-w-[460px]">{text}</div>
      {action}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={cx('skeleton', className)} />
}

export function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-56" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="h-64" />
    </div>
  )
}

/* ---------- Modal / Drawer ---------- */
export function Modal({ open, onClose, title, children, footer, width = 560 }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; footer?: ReactNode; width?: number }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', h)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', h); document.body.style.overflow = prev }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="pop card shadow-pop w-full flex flex-col max-h-[92vh] rounded-b-none sm:rounded-b-xl2" style={{ maxWidth: width }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-line">
          <h3 className="font-semibold">{title}</h3>
          <button className="p-1 rounded-md hover:bg-surface2" onClick={onClose} aria-label="Yopish"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 overflow-auto flex-1">{children}</div>
        {footer && <div className="px-4 py-3 border-t border-line flex justify-end gap-2 safe-b">{footer}</div>}
      </div>
    </div>
  )
}

export function Drawer({ open, onClose, title, children, footer, side = 'right', width = 420 }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; footer?: ReactNode; side?: 'left' | 'right'; width?: number }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[80] bg-black/40" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className={cx('absolute top-0 bottom-0 bg-surface shadow-pop flex flex-col', side === 'right' ? 'right-0 slidein' : 'left-0')} style={{ width: `min(${width}px,100%)` }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-line">
          <div className="font-semibold min-w-0">{title}</div>
          <button className="p-1 rounded-md hover:bg-surface2" onClick={onClose} aria-label="Yopish"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 overflow-auto p-3">{children}</div>
        {footer && <div className="p-3 border-t border-line safe-b">{footer}</div>}
      </aside>
    </div>
  )
}

/* ---------- Tasdiqlash oynasi (window.confirm o'rniga) ---------- */
type ConfirmFn = (text: string, opt?: { title?: string; ok?: string; danger?: boolean }) => Promise<boolean>
const ConfirmCtx = createContext<ConfirmFn>(async () => true)
export const useConfirm = () => useContext(ConfirmCtx)
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [st, setSt] = useState<{ text: string; title?: string; ok?: string; danger?: boolean } | null>(null)
  const res = useRef<(v: boolean) => void>()
  const confirm = useCallback<ConfirmFn>((text, opt) => new Promise<boolean>((r) => { res.current = r; setSt({ text, ...opt }) }), [])
  const close = (v: boolean) => { setSt(null); res.current?.(v) }
  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <Modal open={!!st} onClose={() => close(false)} title={st?.title || 'Tasdiqlang'} width={440}
        footer={<><Btn onClick={() => close(false)}>Bekor qilish</Btn><Btn variant={st?.danger ? 'danger' : 'primary'} onClick={() => close(true)}>{st?.ok || 'Davom etish'}</Btn></>}>
        <p className="text-[14px] leading-relaxed">{st?.text}</p>
      </Modal>
    </ConfirmCtx.Provider>
  )
}

/* ---------- Yorliqlar ---------- */
export function Segmented<T extends string>({ items, value, onChange, className = '' }: { items: { key: T; label: ReactNode; badge?: ReactNode }[]; value: T; onChange: (k: T) => void; className?: string }) {
  return (
    <div className={cx('inline-flex max-w-full overflow-x-auto no-scrollbar p-1 rounded-lg bg-surface2 border border-line gap-0.5', className)} role="tablist">
      {items.map((i) => (
        <button key={i.key} role="tab" aria-selected={i.key === value} onClick={() => onChange(i.key)}
          className={cx('px-3 h-7 rounded-md text-[13px] font-medium whitespace-nowrap transition inline-flex items-center gap-1.5', i.key === value ? 'bg-surface shadow-card text-fg' : 'text-muted hover:text-fg')}>
          {i.label}{i.badge}
        </button>
      ))}
    </div>
  )
}

export function Collapse({ title, children, defaultOpen = false, hint }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean; hint?: ReactNode }) {
  const [o, setO] = useState(defaultOpen)
  return (
    <div className="border border-line rounded-xl bg-surface">
      <button type="button" onClick={() => setO(!o)} className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 text-left">
        <span className="font-semibold text-[13.5px]">{title}</span>
        <span className="flex items-center gap-2 text-muted text-[12px]">{hint}<ChevronDown className={cx('w-4 h-4 transition', o && 'rotate-180')} /></span>
      </button>
      {o && <div className="px-3.5 pb-3.5 pt-0.5">{children}</div>}
    </div>
  )
}

export function Stat({ label, value, sub, tone, icon }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: 'ok' | 'bad' | ''; icon?: ReactNode }) {
  return (
    <div className="card px-3.5 py-3 min-w-0">
      <div className="flex items-center justify-between text-muted text-[12px] font-medium"><span className="truncate">{label}</span>{icon}</div>
      <div className="text-[24px] font-bold leading-tight tracking-tight mt-0.5 truncate">{value}</div>
      {sub !== undefined && <div className={cx('text-[12px] mt-0.5 truncate', tone === 'ok' ? 'text-ok' : tone === 'bad' ? 'text-bad' : 'text-muted')}>{sub}</div>}
    </div>
  )
}

export function Progress({ value, tone }: { value: number; tone?: 'bad' | 'ok' }) {
  return <div className="h-2 rounded-full bg-surface2 overflow-hidden"><div className={cx('h-full rounded-full', tone === 'bad' ? 'bg-bad' : 'bg-brand')} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>
}

export function PlatDot({ p, className = '' }: { p: string; className?: string }) {
  const c = ({ telegram: '#229ED9', instagram: '#D62976', youtube: '#FF0000' } as Record<string, string>)[p] || '#64748b'
  return <span className={cx('inline-block w-2.5 h-2.5 rounded-full shrink-0', className)} style={{ background: c }} />
}
