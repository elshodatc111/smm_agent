import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from 'lucide-react'
import { onMessages, Msg } from './api'

type T = { id: number; level: string; text: string }
const Ctx = createContext<{ push: (level: string, text: string) => void }>({ push: () => {} })
export const useToast = () => useContext(Ctx)

const ICON: Record<string, any> = { success: CheckCircle2, error: XCircle, warning: AlertTriangle, info: Info, debug: Info }
const TONE: Record<string, string> = { success: 'text-ok', error: 'text-bad', warning: 'text-warn', info: 'text-info', debug: 'text-info' }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<T[]>([])
  const n = useRef(0)
  const push = useCallback((level: string, text: string) => {
    const id = ++n.current
    setItems((x) => [...x.slice(-3), { id, level, text }])
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), level === 'error' ? 9000 : 5000)
  }, [])
  useEffect(() => onMessages((ms: Msg[]) => ms.forEach((m) => push(m.level, m.text))), [push])
  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className="fixed z-[100] left-3 right-3 bottom-[76px] lg:bottom-5 lg:left-auto lg:right-5 lg:w-[380px] flex flex-col gap-2 pointer-events-none">
        {items.map((t) => {
          const I = ICON[t.level] || Info
          return (
            <div key={t.id} className="pop pointer-events-auto card shadow-pop flex items-start gap-2.5 p-3 pr-2">
              <I className={`w-5 h-5 mt-px shrink-0 ${TONE[t.level] || 'text-info'}`} />
              <div className="flex-1 text-[13.5px] leading-snug">{t.text}</div>
              <button className="p-1 text-muted hover:text-fg" onClick={() => setItems((x) => x.filter((i) => i.id !== t.id))}><X className="w-4 h-4" /></button>
            </div>
          )
        })}
      </div>
    </Ctx.Provider>
  )
}
