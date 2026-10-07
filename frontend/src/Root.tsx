import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, getJson } from './lib/api'
import { AppProvider, applyBrand, useSessionQuery } from './lib/app'
import { Shell } from './components/Shell'
import { PageSkeleton } from './components/ui'
import { Login } from './pages/Login'
import { renderPage } from './pages/registry'
import { ErrorPage } from './pages/Errors'

function PageHost() {
  const loc = useLocation()
  const nav = useNavigate()
  const qc = useQueryClient()
  const key = loc.pathname + loc.search
  const q = useQuery({ queryKey: ['page', key], queryFn: ({ signal }) => getJson(key, signal), staleTime: 0 })
  const d = q.data
  // Sessiya tugagan bo'lsa server kirish sahifasini qaytaradi
  useEffect(() => { if (d?.kind === 'login') qc.invalidateQueries({ queryKey: ['session'] }) }, [d, qc])
  // Server boshqa manzilga yo'naltirgan bo'lsa (masalan, /kalendar/yangi/zzz -> ...)
  useEffect(() => { document.getElementById('main')?.scrollTo({ top: 0 }) }, [loc.pathname])
  if (q.isError) {
    const e = q.error as ApiError
    return <ErrorPage status={e.status || 0} title={e.data?.title || 'Xato'} detail={e.data?.detail || e.message} onRetry={() => q.refetch()} onHome={() => nav('/')} />
  }
  if (!d) return <PageSkeleton />
  return <div key={loc.pathname} className="pop">{renderPage(d)}</div>
}

export function Root() {
  const s = useSessionQuery()
  const session: any = s.data
  useEffect(() => { if (session?.brand) applyBrand(session.brand) }, [session?.brand])
  if (!session || session.__boot && s.isFetching) {
    return <div className="h-full grid place-items-center"><div className="skeleton w-40 h-10" /></div>
  }
  if (!session.authenticated) return <AppProvider session={session}><Login /></AppProvider>
  return (
    <AppProvider session={session}>
      <Shell><PageHost /></Shell>
    </AppProvider>
  )
}
