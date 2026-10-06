/** Telegram HTML teglari: server (apps/content/richtext.py) bilan bir xil qoidalar. */
const ALLOW = new Set(['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre', 'blockquote', 'tg-spoiler', 'a'])
const escT = (s: string) => s.replace(/&(?!(?:amp|lt|gt|quot|#\d{1,7}|#x[0-9a-f]{1,6});)/gi, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const escA = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
export function unent(s: string): string {
  const t = document.createElement('textarea')
  t.innerHTML = s
  return t.value
}
function openTag(nm: string, at: string): [string, string] | null {
  if (nm === 'span') return /tg-spoiler/i.test(at) ? ['tg-spoiler', '<tg-spoiler>'] : null
  if (!ALLOW.has(nm)) return null
  if (nm === 'a') {
    const h = /href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))/i.exec(at)
    const u = h ? unent(h[1] || h[2] || h[3] || '').trim() : ''
    return /^(https?:\/\/|tg:\/\/|mailto:)/i.test(u) ? ['a', `<a href="${escA(u)}">`] : null
  }
  if (nm === 'code') {
    const l = /class\s*=\s*["']?(language-[\w+#.-]{1,30})["']?/i.exec(at)
    return ['code', l ? `<code class="${l[1]}">` : '<code>']
  }
  if (nm === 'blockquote') return ['blockquote', /\bexpandable\b/i.test(at) ? '<blockquote expandable>' : '<blockquote>']
  return [nm, `<${nm}>`]
}
export function sanitizeTg(s: string): string {
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:\s[^<>]*)?)\/?>/g
  const out: string[] = []
  const st: string[] = []
  let pos = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(s))) {
    out.push(escT(s.slice(pos, m.index)))
    pos = re.lastIndex
    const cl = m[1] === '/'
    const nm = m[2].toLowerCase()
    const at = m[3] || ''
    if (cl) {
      const c = nm === 'span' ? (st.includes('tg-spoiler') ? 'tg-spoiler' : null) : nm
      if (!c || !st.includes(c)) continue
      while (st.length) {
        const t = st.pop() as string
        out.push(`</${t}>`)
        if (t === c) break
      }
    } else {
      const o = openTag(nm, at)
      if (!o) out.push(escT(m[0]))
      else { st.push(o[0]); out.push(o[1]) }
    }
  }
  out.push(escT(s.slice(pos)))
  while (st.length) out.push(`</${st.pop()}>`)
  return out.join('')
}
/** Ko'rinish uchun: sanitizatsiya + hashtag + havola. */
export function richHtml(s: string): string {
  return sanitizeTg(s)
    .replace(/(<[^>]+>)|(&#?\w+;)|(#[\wА-Яа-яЁёʻ'’_]+)/g, (m, tg, en, h) => (h ? `<span class="pv-tag">${h}</span>` : m))
    .replace(/<a href=/g, '<a target="_blank" rel="noopener" href=')
}
export function plain(s: string): string {
  if (!s || (!s.includes('<') && !s.includes('&'))) return s || ''
  const h = sanitizeTg(s).replace(/<a href="([^"]*)">([\s\S]*?)<\/a>/g, (_m, u, t) => {
    const tt = t.replace(/<[^>]+>/g, '')
    const uu = unent(u)
    return !tt.trim() || tt.trim() === uu ? tt : `${tt} (${u})`
  })
  const d = document.createElement('div')
  d.innerHTML = h.replace(/<\/?[^>]+>/g, '')
  return d.textContent || ''
}
export function visLen(s: string): number {
  const d = document.createElement('div')
  d.innerHTML = sanitizeTg(s)
  return (d.textContent || '').length
}
export const tagify = (s: string) => escT(s).replace(/(#[\wА-Яа-яЁёʻ'’_]+)/g, '<span class="pv-tag">$1</span>')
