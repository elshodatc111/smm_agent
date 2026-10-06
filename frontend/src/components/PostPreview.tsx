import { useEffect, useMemo, useRef, useState } from 'react'
import { Eye, ScanSearch } from 'lucide-react'
import { plain, richHtml, tagify, visLen } from '../lib/richtext'
import { cx, FMT, PLAT } from '../lib/format'
import { Btn } from './ui'

export type PvMedia = { url: string; kind: 'image' | 'video'; id?: number }
export type PvData = {
  text: string
  mt: string
  sel: Record<string, { name: string; handle: string }[]>
  media: PvMedia[]
  ytTitle?: string
  ratio?: number
  fit?: string
  crop?: { x: number; y: number; z: number }
  buttons?: string[][]
}
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
const TALL = ['reel', 'short', 'story']

function useDims() {
  const [d, setD] = useState<Record<string, number>>({})
  const set = (url: string, w: number, h: number) => { if (w && h && d[url] !== w / h) setD((x) => ({ ...x, [url]: w / h })) }
  return [d, set] as const
}

/** Kadr (nisbat) ichida rasm/video: "butun kadr" yoki "qirqish" rejimi, sudrab siljitish va g'ildirak bilan kattalashtirish. */
function Frame({ media, ratio, mt, plat, d, dims, setDim, idx, onIdx, onCrop, safe, label }: {
  media: PvMedia[]; ratio: number; mt: string; plat: string; d: PvData; dims: Record<string, number>; setDim: (u: string, w: number, h: number) => void
  idx: number; onIdx: (i: number) => void; onCrop?: (x: number | null, y: number | null, z: number | null) => void; safe: boolean; label: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const m = media.length ? media[idx % media.length] : null
  const ir = m ? dims[m.url] || ratio : ratio
  const forced = !!d.ratio
  const pad = forced && d.fit === 'pad'
  const c = d.crop || { x: 0.5, y: 0.5, z: 1 }
  // kadr balandligi = 1, kengligi = ratio
  const hImg = !m ? 0 : pad ? Math.min(1, ratio / ir) : Math.max(1, ratio / ir) * (forced ? c.z : 1)
  const wImg = hImg * ir
  const left = wImg >= ratio ? (-(wImg - ratio) * c.x) / ratio : (ratio - wImg) / 2 / ratio
  const top = hImg >= 1 ? -(hImg - 1) * c.y : (1 - hImg) / 2
  const canMove = !!m && forced && !pad && !!onCrop
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !canMove) return
    const w = (e: WheelEvent) => { e.preventDefault(); onCrop!(null, null, clamp(c.z * (e.deltaY < 0 ? 1.06 : 0.94), 1, 4)) }
    el.addEventListener('wheel', w, { passive: false })
    return () => el.removeEventListener('wheel', w)
  })
  const down = (e: React.PointerEvent) => { if (!canMove) return; drag.current = { x: e.clientX, y: e.clientY, cx: c.x, cy: c.y }; (e.target as HTMLElement).setPointerCapture(e.pointerId) }
  const move = (e: React.PointerEvent) => {
    if (!drag.current || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const ox = Math.max(0, wImg - ratio), oy = Math.max(0, hImg - 1)
    const dx = (e.clientX - drag.current.x) / r.height, dy = (e.clientY - drag.current.y) / r.height
    onCrop!(ox > 0.001 ? clamp(drag.current.cx - dx / ox, 0, 1) : null, oy > 0.001 ? clamp(drag.current.cy - dy / oy, 0, 1) : null, null)
  }
  const tall = TALL.includes(mt)
  return (
    <div ref={ref} className={cx('pv-media select-none', canMove && 'cursor-grab touch-none', media.length > 1 && !canMove && 'cursor-pointer')}
      style={{ aspectRatio: String(ratio), width: `min(100%, ${Math.round(560 * ratio)}px)`, margin: '0 auto' }}
      onPointerDown={down} onPointerMove={move} onPointerUp={() => { drag.current = null }}
      onClick={() => { if (!drag.current && media.length > 1 && !canMove) onIdx(idx + 1) }}>
      {m ? (
        <>
          {m.kind === 'image' && pad && <img className="bg" src={m.url} alt="" />}
          {m.kind === 'video' ? (
            <video src={m.url} muted loop autoPlay playsInline preload="metadata" draggable={false}
              onLoadedMetadata={(e) => setDim(m.url, (e.target as HTMLVideoElement).videoWidth, (e.target as HTMLVideoElement).videoHeight)}
              style={{ position: 'absolute', width: `${(wImg / ratio) * 100}%`, height: `${hImg * 100}%`, left: `${left * 100}%`, top: `${top * 100}%` }} />
          ) : (
            <img src={m.url} alt="" draggable={false} onLoad={(e) => setDim(m.url, (e.target as HTMLImageElement).naturalWidth, (e.target as HTMLImageElement).naturalHeight)}
              style={{ position: 'absolute', width: `${(wImg / ratio) * 100}%`, height: `${hImg * 100}%`, left: `${left * 100}%`, top: `${top * 100}%`, maxWidth: 'none' }} />
          )}
          {media.length > 1 && <span className="absolute right-2 top-2 bg-black/60 text-white text-[11px] px-2 py-0.5 rounded-full">{(idx % media.length) + 1}/{media.length}</span>}
          {media.length > 1 && (mt === 'carousel' || mt === 'album') && plat !== 'youtube' && (
            <div className="absolute bottom-2 left-0 right-0 flex justify-center gap-1">{media.map((_, i) => <i key={i} className={cx('w-1.5 h-1.5 rounded-full', i === idx % media.length ? 'bg-white' : 'bg-white/40')} />)}</div>
          )}
        </>
      ) : <span>{label}</span>}
      {tall && safe && (
        <div className="absolute inset-0 pointer-events-none">
          <i className="absolute top-0 inset-x-0 h-[13%] bg-black/35" /><i className="absolute bottom-0 inset-x-0 h-[22%] bg-black/35" />
          <span className="absolute top-1 left-0 right-0 text-center text-[10px] text-white/80">profil / sarlavha</span><span className="absolute bottom-1 left-0 right-0 text-center text-[10px] text-white/80">javob / tugmalar</span>
        </div>
      )}
    </div>
  )
}

function Counter({ n, max, note }: { n: number; max: number; note: string }) {
  return <div className="flex justify-between text-[12px] text-muted mt-2"><span>{note}</span><span><b className={cx(n > max ? 'text-bad' : 'text-fg')}>{n}</b> / {max}</span></div>
}
const Warn = ({ items }: { items: [boolean, string][] }) => <>{items.map(([bad, t], i) => <div key={i} className={cx('mt-1.5 text-[12px] rounded-md px-2 py-1', bad ? 'bg-bad/10 text-bad' : 'bg-warn/10 text-warn')}>{t}</div>)}</>

export function PostPreview({ data, onCrop, onExact, only, className }: { data: PvData; onCrop?: (x: number | null, y: number | null, z: number | null) => void; onExact?: () => void; only?: string[]; className?: string }) {
  const [tab, setTab] = useState<string>('telegram')
  const [safe, setSafe] = useState(true)
  const [idx, setIdx] = useState(0)
  const [dims, setDim] = useDims()
  const { text, mt, sel, media } = data
  const hasMedia = mt !== 'text' || media.length > 0
  const plats = (only && only.length ? only : ['telegram', 'instagram', 'youtube'])
  useEffect(() => {
    const first = plats.find((p) => sel[p]?.length) || plats[0]
    if (!sel[tab]?.length && first && first !== tab) setTab(first)
  }, [Object.keys(sel).join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  const cur = plats.includes(tab) ? tab : plats[0]
  const pl = useMemo(() => plain(text), [text])
  const nat = media.length ? dims[media[idx % media.length].url] || 0 : 0
  const ratioFor = (p: string) => {
    if (data.ratio) return data.ratio
    const tall = TALL.includes(mt)
    if (p === 'instagram') return tall ? 9 / 16 : nat ? clamp(nat, 0.8, 1.91) : 1
    if (p === 'youtube') return tall ? 9 / 16 : 16 / 9
    return nat ? clamp(nat, 0.56, 1.9) : 4 / 3
  }
  const lbl = FMT[mt] || mt
  const rows = (data.buttons || []).filter((r) => r.length)
  const t = sel.telegram?.[0], ig = sel.instagram?.[0], yc = sel.youtube?.[0]
  const hashN = (pl.match(/#[^\s#]+/g) || []).length
  const first = pl.split('\n')[0].trim()
  const ytT = (data.ytTitle || first).slice(0, 100)
  const tgLim = hasMedia ? 1024 : 4096
  const tgLen = visLen(text)
  const tallMedia = TALL.includes(mt)
  return (
    <div className={className}>
      <div className="flex gap-1 p-1 rounded-lg bg-surface2 border border-line mb-3">
        {plats.map((p) => (
          <button key={p} type="button" onClick={() => setTab(p)} className={cx('flex-1 h-7 rounded-md text-[12.5px] font-semibold inline-flex items-center justify-center gap-1.5 transition', cur === p ? 'bg-surface shadow-card' : 'text-muted hover:text-fg')}>
            {PLAT[p].name}{sel[p]?.length ? <i className="w-1.5 h-1.5 rounded-full bg-ok" /> : null}
          </button>
        ))}
      </div>

      {cur === 'telegram' && (
        <div className="rounded-2xl p-3" style={{ background: 'linear-gradient(160deg,#cfe3c6,#a9c9a3)' }}>
          <div className="rounded-xl rounded-bl-sm bg-white text-[#111] shadow-sm overflow-hidden max-w-[520px]">
            <div className="px-3 pt-2 text-[13px] font-bold" style={{ color: '#2a8ee0' }}>{t?.name || 'Kanal'}</div>
            {hasMedia && <div className="px-1.5 pt-1.5"><Frame media={media} ratio={ratioFor('telegram')} mt={mt} plat="telegram" d={data} dims={dims} setDim={setDim} idx={idx} onIdx={setIdx} onCrop={onCrop} safe={safe} label={lbl} /></div>}
            <div className="px-3 pt-1.5 text-[14px] leading-snug tgtext">{text ? <span dangerouslySetInnerHTML={{ __html: richHtml(text) }} /> : <span className="text-gray-400">Matn shu yerda ko'rinadi…</span>}</div>
            <div className="px-3 pb-1.5 text-right text-[11px] text-gray-400">12:00</div>
            {rows.length > 0 && <div className="px-1.5 pb-1.5 space-y-1">{rows.map((r, i) => <div key={i} className="flex gap-1">{r.map((b, j) => <span key={j} className="flex-1 text-center text-[12.5px] font-medium py-1.5 rounded-md truncate px-2" style={{ background: 'rgba(42,142,224,.12)', color: '#2a8ee0' }}>{b}</span>)}</div>)}</div>}
          </div>
          <div className="rounded-lg bg-surface/90 px-3 py-1"><Counter n={tgLen} max={tgLim} note={hasMedia ? 'Rasm/video bilan: caption' : 'Oddiy xabar'} /></div>
          {tgLen > tgLim && <Warn items={[[true, `Matn ${tgLim} belgidan oshdi${hasMedia ? ' (caption chegarasi). Qisqartiring.' : '.'}`]]} />}
        </div>
      )}

      {cur === 'instagram' && (
        <div>
          <div className="rounded-xl border border-line bg-white text-[#111] overflow-hidden max-w-[420px] mx-auto">
            <div className="flex items-center gap-2 px-3 py-2"><span className="w-7 h-7 rounded-full" style={{ background: 'linear-gradient(45deg,#f9ce34,#ee2a7b,#6228d7)' }} /><b className="text-[13px]">{ig?.handle || ig?.name || 'akkaunt'}</b></div>
            <Frame media={media} ratio={ratioFor('instagram')} mt={mt} plat="instagram" d={data} dims={dims} setDim={setDim} idx={idx} onIdx={setIdx} onCrop={onCrop} safe={safe} label={mt === 'text' ? 'Media kerak' : lbl} />
            <div className="px-3 pt-2 text-[18px] tracking-widest">♡ ◯ ➤</div>
            <div className="px-3 pb-3 text-[13px] leading-snug"><b>{ig?.handle || ig?.name || 'akkaunt'}</b>{' '}
              {pl ? (pl.length > 125 ? <><span dangerouslySetInnerHTML={{ __html: tagify(pl.slice(0, 125)) }} />… <span className="text-gray-400">ko'proq</span></> : <span dangerouslySetInnerHTML={{ __html: tagify(pl) }} />) : <span className="text-gray-400">Caption shu yerda…</span>}
            </div>
          </div>
          <Counter n={pl.length} max={2200} note="Birinchi 125 belgi ko'rinadi" />
          <Warn items={[
            ...(mt === 'text' && !media.length ? [[true, "Instagram'da post uchun rasm yoki video shart."] as [boolean, string]] : []),
            ...(pl.length > 2200 ? [[true, 'Caption 2200 belgidan oshdi.'] as [boolean, string]] : []),
            ...(hashN > 30 ? [[true, `Hashtaglar 30 tadan oshdi (${hashN}).`] as [boolean, string]] : hashN > 10 ? [[false, `Hashtag ${hashN} ta — 3–10 ta tavsiya etiladi.`] as [boolean, string]] : []),
          ]} />
          {media.length > 0 && mt !== 'story' && (
            <div className="flex items-center gap-3 mt-3 text-[12px] text-muted"><div style={{ width: 84 }}><Frame media={media} ratio={3 / 4} mt="image" plat="instagram" d={{ ...data, ratio: 0 }} dims={dims} setDim={setDim} idx={0} onIdx={() => {}} safe={false} label="" /></div><span>Profil setkasida shunday ko'rinadi (3:4)</span></div>
          )}
        </div>
      )}

      {cur === 'youtube' && (
        <div>
          <div className="rounded-xl border border-line bg-white text-[#111] overflow-hidden max-w-[460px] mx-auto">
            <Frame media={media} ratio={ratioFor('youtube')} mt={mt} plat="youtube" d={data} dims={dims} setDim={setDim} idx={idx} onIdx={setIdx} onCrop={onCrop} safe={safe} label={mt === 'video' || mt === 'short' ? `▶ ${lbl}` : '▶ Video kerak'} />
            <div className="px-3 pt-2 font-semibold text-[14px] leading-snug">{ytT || 'Sarlavha (matnning birinchi qatoridan olinadi)'}</div>
            <div className="px-3 text-[12px] text-gray-500">{yc?.name || 'Kanal'} · hozirgina</div>
            <div className="px-3 py-2 text-[12.5px] text-gray-700 whitespace-pre-wrap break-words max-h-24 overflow-hidden">{pl ? <span dangerouslySetInnerHTML={{ __html: tagify(pl) }} /> : <span className="text-gray-400">Tavsif shu yerda…</span>}</div>
          </div>
          <Counter n={pl.length} max={5000} note={`Sarlavha: ${ytT.length} / 100`} />
          <Warn items={[
            ...(mt !== 'video' && mt !== 'short' ? [[true, "YouTube uchun post turi «Video» yoki «Shorts» bo'lishi kerak."] as [boolean, string]] : []),
            ...(!ytT ? [[true, 'Sarlavha uchun matnning birinchi qatori kerak.'] as [boolean, string]] : []),
            ...(!data.ytTitle && first.length > 100 ? [[false, 'Sarlavha 100 belgiga qisqartiriladi.'] as [boolean, string]] : []),
            ...(pl.length > 5000 ? [[true, 'Tavsif 5000 belgidan oshdi.'] as [boolean, string]] : []),
          ]} />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
        {tallMedia ? <label className="flex items-center gap-2 text-[12.5px] cursor-pointer"><input type="checkbox" className="accent-[var(--brand)]" checked={safe} onChange={(e) => setSafe(e.target.checked)} /> Xavfsiz zonani ko'rsat</label> : <span />}
        {onExact && media.some((m) => m.kind === 'image') && <Btn size="sm" variant="blue" onClick={onExact}><ScanSearch className="w-3.5 h-3.5" /> Aniq natija</Btn>}
      </div>
      {data.ratio ? <p className="help">{data.fit === 'pad' ? "Butun kadr saqlanadi, chetlari xira fon bilan to'ldiriladi." : "Qirqish rejimi: rasmni sudrab siljiting, g'ildirak bilan kattalashtiring."}</p> : null}
    </div>
  )
}
