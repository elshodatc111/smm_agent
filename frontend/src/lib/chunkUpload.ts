import { csrfToken } from './api'

export type UpState = { id: string; name: string; size: number; sent: number; phase: 'wait' | 'run' | 'server' | 'done' | 'err'; msg?: string; speed?: number }

type Opts = { tags?: string; onState: (s: UpState) => void; signal?: AbortSignal }

function post(url: string, fd: FormData, onProg?: (loaded: number) => void, signal?: AbortSignal): Promise<{ status: number; data: any }> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest()
    x.open('POST', url)
    x.setRequestHeader('X-CSRFToken', csrfToken())
    x.setRequestHeader('Accept', 'application/json')
    x.setRequestHeader('X-Requested-With', 'fetch')
    x.timeout = 5 * 60 * 1000
    if (x.upload && onProg) x.upload.onprogress = (e) => onProg(e.loaded)
    x.onload = () => { let data: any = null; try { data = JSON.parse(x.responseText) } catch { /* html */ } resolve({ status: x.status, data }) }
    x.onerror = () => reject(new Error('Tarmoq uzildi'))
    x.ontimeout = () => reject(new Error('Vaqt tugadi'))
    x.onabort = () => reject(new DOMException('Bekor qilindi', 'AbortError'))
    signal?.addEventListener('abort', () => x.abort())
    x.send(fd)
  })
}

/** Faylni 8 MB lik bo'laklarga bo'lib serverga yuboradi (foiz + tezlik, uzilsa o'sha bo'lakni qayta yuboradi).
 *  Server keyin uni Cloudflare R2'ga ko'chiradi (foizi sahifada ko'rinadi). */
export async function uploadChunked(file: File, id: string, o: Opts): Promise<void> {
  const st: UpState = { id, name: file.name, size: file.size, sent: 0, phase: 'run' }
  const emit = (p: Partial<UpState>) => { Object.assign(st, p); o.onState({ ...st }) }
  emit({})
  try {
    const fd0 = new FormData(); fd0.append('name', file.name); fd0.append('size', String(file.size)); if (o.tags) fd0.append('tags', o.tags)
    const s = await post('/cloudflare/yuklash/boshlash/', fd0, undefined, o.signal)
    if (s.status !== 200) throw new Error(s.data?.detail || `Server xatosi (${s.status})`)
    const oid: number = s.data.id, chunk: number = s.data.chunk
    let offset = 0
    const t0 = Date.now()
    while (offset < file.size) {
      const end = Math.min(file.size, offset + chunk)
      const blob = file.slice(offset, end)
      let ok = false, lastErr = ''
      for (let a = 0; a < 4 && !ok; a++) {
        try {
          const fd = new FormData(); fd.append('offset', String(offset)); fd.append('chunk', blob, 'part')
          const r = await post(`/cloudflare/${oid}/bolak/`, fd, (l) => {
            const sent = offset + l
            emit({ sent, speed: sent / Math.max(1, (Date.now() - t0) / 1000) })
          }, o.signal)
          if (r.status === 200) ok = true
          else if (r.status === 409 && typeof r.data?.have === 'number') { offset = r.data.have; lastErr = 'qayta'; break }
          else lastErr = r.data?.detail || `Server xatosi (${r.status})`
        } catch (e: any) {
          if (e?.name === 'AbortError') throw e
          lastErr = e?.message || 'Tarmoq xatosi'
        }
        if (!ok && lastErr !== 'qayta') await new Promise((res) => setTimeout(res, 1000 * (a + 1)))
      }
      if (lastErr === 'qayta') continue
      if (!ok) throw new Error(lastErr || 'Yuklab bo‘lmadi')
      offset = end
      emit({ sent: offset, speed: offset / Math.max(1, (Date.now() - t0) / 1000) })
    }
    const f = await post(`/cloudflare/${oid}/tugatish/`, new FormData(), undefined, o.signal)
    if (f.status !== 200) throw new Error(f.data?.detail || `Server xatosi (${f.status})`)
    emit({ phase: 'done', sent: file.size })
  } catch (e: any) {
    emit({ phase: 'err', msg: e?.name === 'AbortError' ? 'Bekor qilindi' : e?.message || 'Xato' })
  }
}
