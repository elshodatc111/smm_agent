import { ReactNode, useEffect, useMemo, useState } from 'react'
import { cx } from '../lib/format'
import { Btn } from './ui'
import { useApp } from '../lib/app'

export type FieldSchema = {
  name: string; id: string; label: string; kind: string; required: boolean; help: string; errors: string[]; attrs: Record<string, any>
  disabled: boolean; choices?: [any, string][]; value?: any
}
export type FormSchema = { fields: FieldSchema[]; errors: string[]; multipart: boolean }
export type Values = Record<string, any>

export function initialValues(schema: FormSchema): Values {
  const v: Values = {}
  schema.fields.forEach((f) => {
    if (f.kind === 'file') v[f.name] = []
    else if (f.kind === 'checkbox') v[f.name] = !!f.value
    else if (f.kind === 'checkboxes' || f.kind === 'multiselect') v[f.name] = (Array.isArray(f.value) ? f.value : f.value ? [f.value] : []).map(String)
    else v[f.name] = f.value === null || f.value === undefined ? '' : String(f.value)
  })
  return v
}

export function useFormValues(schema: FormSchema) {
  const [values, setValues] = useState<Values>(() => initialValues(schema))
  // Server yangi sxema qaytarsa (masalan, xatolar bilan) qiymatlar qayta o'rnatiladi
  const sig = useMemo(() => JSON.stringify(schema.fields.map((f) => [f.name, f.value, f.errors])), [schema])
  useEffect(() => { setValues(initialValues(schema)) }, [sig]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (name: string, v: any) => setValues((x) => ({ ...x, [name]: v }))
  return { values, set, setValues }
}

export function toFormData(schema: FormSchema, values: Values, extra?: Record<string, string>): FormData {
  const fd = new FormData()
  schema.fields.forEach((f) => {
    const v = values[f.name]
    if (f.kind === 'file') (v as File[] | undefined)?.forEach((file) => fd.append(f.name, file, file.name))
    else if (f.kind === 'checkbox') { if (v) fd.append(f.name, 'on') }
    else if (f.kind === 'checkboxes' || f.kind === 'multiselect') (v as string[]).forEach((x) => fd.append(f.name, x))
    else if (v !== undefined && v !== null) fd.append(f.name, String(v))
  })
  if (extra) Object.entries(extra).forEach(([k, v]) => fd.append(k, v))
  return fd
}

export function Field({ f, value, onChange, hideLabel, className }: { f: FieldSchema; value: any; onChange: (v: any) => void; hideLabel?: boolean; className?: string }) {
  const err = f.errors?.length ? <div className="text-[12px] text-bad mt-1">{f.errors.join(' ')}</div> : null
  const common = { id: f.id, name: f.name, disabled: f.disabled, required: false, ...(f.attrs || {}) }
  const label = !hideLabel && f.kind !== 'checkbox' && <label htmlFor={f.id} className="label">{f.label}{f.required && <span className="text-bad"> *</span>}</label>
  let ctl: ReactNode
  switch (f.kind) {
    case 'hidden': return null
    case 'textarea':
      ctl = <textarea className="input" rows={Number(f.attrs?.rows) || 4} {...common} value={value} onChange={(e) => onChange(e.target.value)} />
      break
    case 'select':
      ctl = <select className="input" {...common} value={value} onChange={(e) => onChange(e.target.value)}>{f.choices?.map(([v, l]) => <option key={String(v)} value={String(v)}>{l}</option>)}</select>
      break
    case 'multiselect':
      ctl = <select className="input h-auto" multiple size={Math.min(6, f.choices?.length || 3)} {...common} value={value} onChange={(e) => onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}>{f.choices?.map(([v, l]) => <option key={String(v)} value={String(v)}>{l}</option>)}</select>
      break
    case 'radio':
      ctl = <div className="flex flex-wrap gap-2">{f.choices?.map(([v, l]) => <button type="button" key={String(v)} className={cx('chip', String(v) === value && 'chip-on')} onClick={() => onChange(String(v))}>{l}</button>)}</div>
      break
    case 'checkboxes':
      ctl = <div className="flex flex-wrap gap-2">{f.choices?.map(([v, l]) => { const on = (value as string[]).includes(String(v)); return <button type="button" key={String(v)} className={cx('chip', on && 'chip-on')} onClick={() => onChange(on ? (value as string[]).filter((x) => x !== String(v)) : [...value, String(v)])}>{l}</button> })}</div>
      break
    case 'checkbox':
      ctl = (
        <label className="flex items-center gap-2.5 h-9 cursor-pointer select-none">
          <input type="checkbox" className="w-4 h-4 accent-[var(--brand)]" id={f.id} checked={!!value} disabled={f.disabled} onChange={(e) => onChange(e.target.checked)} />
          <span className="text-[13.5px] font-medium">{f.label}</span>
        </label>
      )
      break
    case 'file':
      ctl = <input type="file" className="input h-auto py-1.5" {...common} multiple={!!f.attrs?.multiple} onChange={(e) => onChange(Array.from(e.target.files || []))} />
      break
    case 'color':
      ctl = <div className="flex gap-2"><input type="color" className="h-9 w-12 rounded-lg border border-line bg-surface p-1" value={value || '#e11d2e'} onChange={(e) => onChange(e.target.value)} /><input className="input" value={value} onChange={(e) => onChange(e.target.value)} /></div>
      break
    default:
      ctl = <input className="input" type={f.kind} {...common} value={value} onChange={(e) => onChange(e.target.value)} />
  }
  return (
    <div className={className}>
      {label}
      {ctl}
      {f.help && <div className="help">{f.help}</div>}
      {err}
    </div>
  )
}

/** Oddiy forma: maydonlar grid'da, yuborish tugmasi bilan. Server javobi (xatolar) sahifani qayta chizadi. */
export function SimpleForm({ schema, action, submitLabel = 'Saqlash', hidden, cols = 1 }: { schema: FormSchema; action: string; submitLabel?: string; hidden?: string; cols?: 1 | 2 }) {
  const { submit, busy } = useApp()
  const { values, set } = useFormValues(schema)
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await submit(action, toFormData(schema, values, hidden ? { _form: hidden } : undefined))
  }
  return (
    <form onSubmit={onSubmit} className="space-y-3.5">
      {schema.errors.length > 0 && <div className="rounded-lg border border-bad/40 bg-bad/10 text-bad px-3 py-2 text-[13px]">{schema.errors.join(' ')}</div>}
      <div className={cx('grid gap-3.5', cols === 2 && 'sm:grid-cols-2')}>
        {schema.fields.map((f) => (f.kind === 'textarea' || f.kind === 'checkboxes' || f.kind === 'radio' ? <Field key={f.name} f={f} value={values[f.name]} onChange={(v) => set(f.name, v)} className={cols === 2 ? 'sm:col-span-2' : ''} /> : <Field key={f.name} f={f} value={values[f.name]} onChange={(v) => set(f.name, v)} />))}
      </div>
      <Btn variant="primary" type="submit" loading={busy}>{submitLabel}</Btn>
    </form>
  )
}
