import { lazy, Suspense } from 'react'
import type { ChartSpec } from './ChartImpl'

export type { ChartSpec }
// Grafik kutubxonasi (recharts) og'ir — faqat grafik chiqadigan sahifada yuklanadi
const Impl = lazy(() => import('./ChartImpl').then((m) => ({ default: m.ChartImpl })))

export function Chart({ spec, height = 230 }: { spec: ChartSpec; height?: number }) {
  return <Suspense fallback={<div className="rounded-lg bg-surface2 animate-pulse" style={{ height }} />}><Impl spec={spec} height={height} /></Suspense>
}
