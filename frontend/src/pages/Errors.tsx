import { AlertCircle } from 'lucide-react'
import { Btn, Card, Empty, PageHeader } from '../components/ui'
import { useApp } from '../lib/app'

export function ErrorPage({ status, title, detail, onRetry, onHome }: { status: number; title: string; detail?: string; onRetry?: () => void; onHome?: () => void }) {
  return (
    <div className="grid place-items-center py-16">
      <div className="text-center max-w-[420px] space-y-3">
        <div className="mx-auto w-14 h-14 rounded-2xl bg-bad/10 text-bad grid place-items-center"><AlertCircle className="w-7 h-7" /></div>
        <div className="text-muted text-[13px] font-semibold">{status || 'Aloqa xatosi'}</div>
        <h1 className="h-title">{title}</h1>
        <p className="text-muted text-[13.5px]">{detail}</p>
        <div className="flex justify-center gap-2 pt-1">{status >= 500 || !status ? <Btn onClick={onRetry}>Qayta urinish</Btn> : null}<Btn variant="primary" onClick={onHome}>Bosh sahifa</Btn></div>
      </div>
    </div>
  )
}

export function NeedBusiness({ d }: { d: any }) {
  const { session, setBusiness } = useApp()
  return (
    <>
      <PageHeader title={d.title || 'Biznesni tanlang'} />
      <Card><Empty text="Bu sahifa uchun yuqoridan bitta biznesni tanlang." action={<div className="flex flex-wrap gap-2 justify-center">{(session.businesses || []).map((b) => <Btn key={b.id} onClick={() => setBusiness(b.id)}>{b.name}</Btn>)}</div>} /></Card>
    </>
  )
}
