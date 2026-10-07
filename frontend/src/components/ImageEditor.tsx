import { useEffect, useMemo, useRef, useState } from 'react'
import { RotateCw, ZoomIn, ZoomOut } from 'lucide-react'
import { Btn, Modal, Spinner } from './ui'
import { cx } from '../lib/format'

const PRESETS: [string, string, number][] = [['orig', 'Asl', 0], ['1x1', '1:1', 1], ['4x5', '4:5', 0.8], ['191', '1.91:1', 1.91], ['9x16', '9:16', 9 / 16], ['16x9', '16:9', 16 / 9]]
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
const MAXPX = 2160

/** Rasmni kadrga moslab kesish: rasmni sudrab siljitish, ikki barmoq/g'ildirak/slayder bilan kattalashtirish, 90° burish.
 *  Telefonda ham ishlaydi (pointer events). Natija — JPEG fayl. */
export function ImageEditor({ file, ratio = 0, onClose, onDone }: { file: File | null; ratio?: number; onClose: () => void; onDone: (f: File) => void }) {
  const [src, setSrc] = useState('')
  const [nat, setNat] = useState<[number, number] | null>(null)
  const [preset, setPreset] = useState('orig')
  const [rot, setRot] = useState(0)
  const [z, setZ] = useState(1)
  const [off, setOff] = useState<[number, number]>([0, 0])
  const [busy, setBusy] = useState(false)
  const imgRef = useRef<HTMLImageElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [boxW, setBoxW] = useState(320)
  const ptrs = useRef(new Map<number, { x: number; y: number }>())
  const lastD = useRef(0)

  useEffect(() => {
    if (!file) return
    const u = URL.createObjectURL(file)
    setSrc(u); setNat(null); setRot(0); setZ(1); setOff([0, 0])
    const p = PRESETS.find((x) => ratio && Math.abs(x[2] - ratio) < 0.01)
    setPreset(p ? p[0] : 'orig')
    return () => URL.revokeObjectURL(u)
  }, [file, ratio])

  const [rw, rh] = nat ? (rot % 180 ? [nat[1], nat[0]] : nat) : [1, 1]
  const r = preset === 'orig' ? rw / rh : PRESETS.find((p) => p[0] === preset)![2]
  const maxH = typeof window !== 'undefined' ? Math.max(220, window.innerHeight * 0.48) : 400
  const W = Math.round(boxW / r) > maxH ? Math.round(maxH * r) : boxW
  const H = Math.round(W / r)
  const minS = nat ? Math.max(W / rw, H / rh) : 1
  const s = minS * z
  const clampOff = (o: [number, number]): [number, number] => {
    const mx = Math.max(0, (rw * s - W) / 2), my = Math.max(0, (rh * s - H) / 2)
    return [clamp(o[0], -mx, mx), clamp(o[1], -my, my)]
  }
  useEffect(() => { setOff((o) => clampOff(o)) }, [preset, rot, z, W, H, nat]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setBoxW(Math.min(480, Math.max(200, el.clientWidth))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [file])

  const down = (e: React.PointerEvent) => { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); ptrs.current.set(e.pointerId, { x: e.clientX, y: e.clientY }); lastD.current = 0 }
  const move = (e: React.PointerEvent) => {
    const m = ptrs.current
    const prev = m.get(e.pointerId)
    if (!prev) return
    m.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (m.size === 1) setOff((o) => clampOff([o[0] + e.clientX - prev.x, o[1] + e.clientY - prev.y]))
    else if (m.size === 2) {
      const [a, b] = Array.from(m.values())
      const d = Math.hypot(a.x - b.x, a.y - b.y)
      if (lastD.current) setZ((v) => clamp(v * (d / lastD.current), 1, 6))
      lastD.current = d
    }
  }
  const up = (e: React.PointerEvent) => { ptrs.current.delete(e.pointerId); lastD.current = 0 }
  const wheel = (e: React.WheelEvent) => setZ((v) => clamp(v * (e.deltaY < 0 ? 1.08 : 0.92), 1, 6))

  const exportFile = () => {
    if (!nat || !imgRef.current) return
    setBusy(true)
    const k = Math.min(1 / s, MAXPX / Math.max(W, H)) // chiqish pikseli / ekran pikseli
    const ow = Math.round(W * k), oh = Math.round(H * k)
    const c = document.createElement('canvas'); c.width = ow; c.height = oh
    const ctx = c.getContext('2d')!
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, ow, oh)
    ctx.translate(ow / 2 + off[0] * k, oh / 2 + off[1] * k)
    ctx.rotate((rot * Math.PI) / 180)
    ctx.scale(s * k, s * k)
    ctx.drawImage(imgRef.current, -nat[0] / 2, -nat[1] / 2)
    c.toBlob((b) => {
      setBusy(false)
      if (!b) return
      const name = (file?.name || 'rasm').replace(/\.[^.]+$/, '') + '-kesilgan.jpg'
      onDone(new File([b], name, { type: 'image/jpeg' }))
      onClose()
    }, 'image/jpeg', 0.92)
  }
  const label = useMemo(() => (nat ? `${Math.round(W / s)} × ${Math.round(H / s)} px` : ''), [nat, W, H, s])

  return (
    <Modal open={!!file} onClose={onClose} title="Rasmni kesish" width={560}
      footer={<><span className="mr-auto text-[12px] text-muted">{label}</span><Btn onClick={onClose}>Bekor qilish</Btn><Btn variant="primary" onClick={exportFile} loading={busy} disabled={!nat}>Tayyor</Btn></>}>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {PRESETS.map(([k, l]) => <button key={k} type="button" onClick={() => { setPreset(k); setZ(1); setOff([0, 0]) }} className={cx('chip h-7 text-[12px] px-2.5', preset === k && 'chip-on')}>{l}</button>)}
        <button type="button" className="chip h-7 text-[12px] px-2.5 ml-auto" onClick={() => { setRot((v) => (v + 90) % 360); setZ(1); setOff([0, 0]) }}><RotateCw className="w-3.5 h-3.5" /> Burish</button>
      </div>
      <div ref={wrapRef} className="flex justify-center">
        <div className="relative overflow-hidden rounded-lg bg-[#222] touch-none select-none cursor-grab active:cursor-grabbing" style={{ width: W, height: H }}
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onWheel={wheel}>
          {!nat && <div className="absolute inset-0 grid place-items-center text-white"><Spinner className="w-6 h-6" /></div>}
          {src && <img ref={imgRef} src={src} alt="" draggable={false} onLoad={(e) => setNat([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])}
            className="absolute left-1/2 top-1/2 max-w-none pointer-events-none" style={{ width: nat?.[0], height: nat?.[1], transform: `translate(-50%,-50%) translate(${off[0]}px,${off[1]}px) rotate(${rot}deg) scale(${s})` }} />}
          <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.25) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.25) 1px,transparent 1px)', backgroundSize: `${W / 3}px ${H / 3}px` }} />
        </div>
      </div>
      <div className="flex items-center gap-3 mt-3">
        <ZoomOut className="w-4 h-4 text-muted" /><input type="range" min={1} max={6} step={0.01} value={z} onChange={(e) => setZ(Number(e.target.value))} className="flex-1 accent-[var(--brand)]" aria-label="Kattalashtirish" /><ZoomIn className="w-4 h-4 text-muted" />
      </div>
      <p className="help text-center">Rasmni sudrab siljiting, ikki barmoq yoki slayder bilan kattalashtiring.</p>
    </Modal>
  )
}
