import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis, Line, LineChart } from 'recharts'

export type ChartSpec = { id?: string; kind: 'line' | 'bar'; labels: string[]; series: { name: string; data: number[] }[]; colors?: string[] }
const COLORS = ['#e11d2e', '#2563eb', '#16a34a', '#d97706', '#7c3aed']

const axis = { fontSize: 11, fill: 'var(--muted)' }
const tip = { contentStyle: { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, fontSize: 12.5, boxShadow: '0 8px 24px rgba(0,0,0,.15)' }, labelStyle: { color: 'var(--muted)' } }

export function Chart({ spec, height = 230 }: { spec: ChartSpec; height?: number }) {
  const colors = spec.colors?.length ? spec.colors : COLORS
  const data = spec.labels.map((l, i) => { const r: Record<string, any> = { x: l }; spec.series.forEach((s) => { r[s.name] = s.data[i] }); return r })
  const many = spec.series.length > 1
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        {spec.kind === 'bar' ? (
          <BarChart data={data} margin={{ top: 6, right: 6, left: -14, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="x" tick={axis} tickLine={false} axisLine={false} minTickGap={14} />
            <YAxis tick={axis} tickLine={false} axisLine={false} width={46} />
            <Tooltip {...tip} cursor={{ fill: 'var(--surface-2)' }} />
            {many && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {spec.series.map((s, i) => <Bar key={s.name} dataKey={s.name} fill={colors[i % colors.length]} radius={[5, 5, 0, 0]} maxBarSize={36} />)}
          </BarChart>
        ) : many ? (
          <LineChart data={data} margin={{ top: 6, right: 6, left: -14, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="x" tick={axis} tickLine={false} axisLine={false} minTickGap={18} />
            <YAxis tick={axis} tickLine={false} axisLine={false} width={46} />
            <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
            {spec.series.map((s, i) => <Line key={s.name} type="monotone" dataKey={s.name} stroke={colors[i % colors.length]} strokeWidth={2.4} dot={false} />)}
          </LineChart>
        ) : (
          <AreaChart data={data} margin={{ top: 6, right: 6, left: -14, bottom: 0 }}>
            <defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors[0]} stopOpacity={0.3} /><stop offset="100%" stopColor={colors[0]} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="x" tick={axis} tickLine={false} axisLine={false} minTickGap={18} />
            <YAxis tick={axis} tickLine={false} axisLine={false} width={46} domain={['auto', 'auto']} />
            <Tooltip {...tip} />
            {spec.series.map((s) => <Area key={s.name} type="monotone" dataKey={s.name} stroke={colors[0]} strokeWidth={2.4} fill="url(#g1)" />)}
          </AreaChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
