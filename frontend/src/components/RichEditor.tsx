import { useRef, useState } from 'react'
import { Bold, Code, Eraser, EyeOff, Italic, Link2, Quote, Strikethrough, Underline, SquareCode, Hash } from 'lucide-react'
import { cx } from '../lib/format'

type Props = { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string; id?: string; className?: string; richOk?: boolean }

/** Matn maydoni + formatlash paneli (qalin, yotiq, tagiga chizilgan, ustiga chizilgan, havola, kod, iqtibos, spoyler).
 *  Teglar Telegram uchun saqlanadi; Instagram/YouTube'da ular olib tashlanadi (ko'rinishda shu ko'rsatiladi). */
export function RichEditor({ value, onChange, rows = 9, placeholder, id, className, richOk = true }: Props) {
  const ta = useRef<HTMLTextAreaElement>(null)
  const [link, setLink] = useState<string | null>(null)

  const apply = (fn: (sel: string) => [string, string, string], keep = false) => {
    const el = ta.current
    if (!el) return
    const s = el.selectionStart, e = el.selectionEnd
    const [pre, mid, post] = fn(value.slice(s, e))
    const next = value.slice(0, s) + pre + mid + post + value.slice(e)
    onChange(next)
    requestAnimationFrame(() => {
      el.focus()
      const a = s + pre.length
      el.setSelectionRange(a, keep ? a + mid.length : a + mid.length)
    })
  }
  const wrap = (tag: string, ph = 'matn', attrs = '') => apply((sel) => [`<${tag}${attrs}>`, sel || ph, `</${tag}>`])
  const clear = () => apply((sel) => ['', sel.replace(/<\/?[a-zA-Z][^>]*>/g, ''), ''])
  const doLink = () => {
    const u = (link || '').trim()
    if (/^(https?:\/\/|tg:\/\/|mailto:)/i.test(u)) { wrap('a', 'havola matni', ` href="${u.replace(/"/g, '&quot;')}"`); setLink(null) }
  }
  const key = (e: React.KeyboardEvent) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return
    const k = e.key.toLowerCase()
    const m: Record<string, () => void> = { b: () => wrap('b'), i: () => wrap('i'), u: () => wrap('u'), k: () => setLink('https://') }
    if (e.shiftKey && k === 's') { e.preventDefault(); wrap('s') } else if (!e.shiftKey && m[k]) { e.preventDefault(); m[k]() }
  }
  const tools: [string, any, () => void, string][] = [
    ['Qalin (Ctrl+B)', Bold, () => wrap('b'), 'b'], ['Yotiq (Ctrl+I)', Italic, () => wrap('i'), 'i'], ['Tagiga chizilgan (Ctrl+U)', Underline, () => wrap('u'), 'u'],
    ['Ustiga chizilgan (Ctrl+Shift+S)', Strikethrough, () => wrap('s'), 's'], ['Havola (Ctrl+K)', Link2, () => setLink('https://'), 'a'], ['Kod', Code, () => wrap('code'), 'c'],
    ['Kod bloki', SquareCode, () => wrap('pre'), 'p'], ['Iqtibos', Quote, () => wrap('blockquote'), 'q'], ['Spoyler (yashirin matn)', EyeOff, () => wrap('tg-spoiler'), 'sp'],
  ]
  return (
    <div className={cx('rounded-lg border border-line bg-surface focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20 transition', className)}>
      <div className="flex flex-wrap items-center gap-0.5 px-1.5 py-1 border-b border-line bg-surface2/60 rounded-t-lg">
        {tools.map(([t, Ic, fn, k]) => (
          <button key={k} type="button" title={t} aria-label={t} onClick={fn} disabled={!richOk} className="w-8 h-8 grid place-items-center rounded-md text-muted hover:text-fg hover:bg-surface transition disabled:opacity-40"><Ic className="w-4 h-4" /></button>
        ))}
        <span className="w-px h-5 bg-line mx-1" />
        <button type="button" title="Hashtag qo'shish" aria-label="Hashtag" onClick={() => apply((s) => ['#', s, ''])} className="w-8 h-8 grid place-items-center rounded-md text-muted hover:text-fg hover:bg-surface"><Hash className="w-4 h-4" /></button>
        <button type="button" title="Formatlashni tozalash" aria-label="Formatlashni tozalash" onClick={clear} className="w-8 h-8 grid place-items-center rounded-md text-muted hover:text-fg hover:bg-surface"><Eraser className="w-4 h-4" /></button>
        <span className="ml-auto text-[11.5px] text-muted pr-1.5 hidden sm:block">{richOk ? 'Telegram: teglar saqlanadi' : "Faqat Telegram formatlashni qo'llaydi"}</span>
      </div>
      {link !== null && (
        <div className="flex items-center gap-2 px-2 py-1.5 border-b border-line">
          <input autoFocus className="input h-8" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…" onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); doLink() } if (e.key === 'Escape') setLink(null) }} />
          <button type="button" className="btn btn-primary btn-sm" onClick={doLink}>Qo'yish</button>
          <button type="button" className="btn btn-sm" onClick={() => setLink(null)}>×</button>
        </div>
      )}
      <textarea ref={ta} id={id} rows={rows} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} onKeyDown={key}
        className="w-full resize-y bg-transparent px-3 py-2.5 text-[14px] leading-relaxed outline-none placeholder:text-muted/70 rounded-b-lg" />
    </div>
  )
}
