export const nf = (v: any): string => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1).replace(/\.0$/, '') + ' mln'
  if (Math.abs(n) >= 10_000) return Math.round(n / 1000) + ' ming'
  return n.toLocaleString('ru-RU').replace(/ /g, ' ')
}
export const pct = (v: any, d = 2): string => (v === null || v === undefined ? '—' : (Number(v) * 100).toFixed(d) + '%')
export const delta = (v: number | null | undefined, suffix = '%'): string => (v === null || v === undefined ? '' : `${v >= 0 ? '+' : ''}${Math.round(v)}${suffix}`)
export const bytes = (n: number): string => (n > 1e9 ? (n / 1e9).toFixed(1) + ' GB' : n > 1e6 ? (n / 1e6).toFixed(1) + ' MB' : n > 1e3 ? Math.round(n / 1e3) + ' KB' : n + ' B')
const MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr']
export const monthName = (ym: string): string => {
  const [y, m] = ym.split('-').map(Number)
  return `${MONTHS[m - 1][0].toUpperCase()}${MONTHS[m - 1].slice(1)} ${y}`
}
export const fmtDate = (iso: string): string => {
  const d = new Date(iso)
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
export const fmtShort = (iso: string): string => {
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
export const PLAT: Record<string, { name: string; short: string; color: string }> = {
  telegram: { name: 'Telegram', short: 'TG', color: '#229ED9' },
  instagram: { name: 'Instagram', short: 'IG', color: '#D62976' },
  youtube: { name: 'YouTube', short: 'YT', color: '#FF0000' },
}
export const FMT: Record<string, string> = { text: 'Matn', image: 'Rasm', video: 'Video', album: 'Albom', carousel: 'Karusel', reel: 'Reels', short: 'Shorts', story: 'Stories' }
export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')
export const statusTone = (s?: string): string =>
  ({ active: 'ok', published: 'ok', done: 'ok', ready: 'ok', sent: 'ok', good: 'ok', approved: 'blue', scheduled: 'blue', running: 'blue', pending_approval: 'warn', token_expiring: 'warn', paused: 'warn', cooldown: 'warn', error: 'bad', failed: 'bad', blocked: 'bad' } as Record<string, string>)[s || ''] || ''
