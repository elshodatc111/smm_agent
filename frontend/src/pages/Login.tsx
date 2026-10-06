import { FormEvent, useState } from 'react'
import { Eye, EyeOff, LogIn } from 'lucide-react'
import { useApp } from '../lib/app'
import { Btn } from '../components/ui'

export function Login() {
  const { session, submit, busy } = useApp()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const b = session.brand
  const next = new URLSearchParams(location.search).get('next') || ''
  const go = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    const r = await submit('/kirish/', { username: u, password: p, next }, { stay: true })
    if (r && r.data?.kind === 'login' && r.data.error) setErr(r.data.error)
  }
  return (
    <div className="min-h-full grid place-items-center p-4" style={{ background: 'radial-gradient(1200px 500px at 50% -10%, var(--brand-soft), transparent), var(--bg)' }}>
      <form onSubmit={go} className="pop card shadow-pop w-full max-w-[400px] p-6 sm:p-7 space-y-4">
        <div className="flex flex-col items-center gap-2 pb-1">
          {b.logo ? <img src={b.logo} alt="" className="w-14 h-14 rounded-xl object-contain" /> : <span className="w-14 h-14 rounded-xl bg-brand text-white grid place-items-center text-2xl font-bold">{(b.name || 'S')[0]}</span>}
          <h1 className="text-[20px] font-bold tracking-tight">{b.name}</h1>
          <p className="text-muted text-[13px]">Hisobingizga kiring</p>
        </div>
        {err && <div className="rounded-lg border border-bad/40 bg-bad/10 text-bad px-3 py-2 text-[13px]" role="alert">{err}</div>}
        <div><label className="label" htmlFor="u">Login</label><input id="u" name="username" className="input h-10" autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></div>
        <div>
          <label className="label" htmlFor="p">Parol</label>
          <div className="relative">
            <input id="p" name="password" className="input h-10 pr-10" type={show ? 'text' : 'password'} autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required />
            <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-fg" onClick={() => setShow(!show)} aria-label="Parolni ko'rsatish">{show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
          </div>
        </div>
        <Btn variant="primary" type="submit" loading={busy} className="w-full h-10"><LogIn className="w-4 h-4" /> Kirish</Btn>
      </form>
    </div>
  )
}
