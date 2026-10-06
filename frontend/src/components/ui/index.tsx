import type { ReactNode } from 'react';
import { ApiError } from '@/api/client';
import { domainClass, statusClass, statusWord } from '@/lib/format';

export function Badge({ kind, children, title }: { kind: 'ok' | 'warn' | 'bad' | 'info' | 'neutral'; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${kind}`} title={title}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${statusClass[status] ?? 'badge-neutral'}`}>{statusWord[status] ?? status}</span>;
}

export function DomainBadge({ status, word }: { status: string; word: string }) {
  return <span className={`badge ${domainClass[status] ?? 'badge-neutral'}`}>{word}</span>;
}

export function Site({ group, element }: { group: string; element: string }) {
  return <span className={`site site-${group}`}><i aria-hidden="true" />{group} {element}</span>;
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className="row small muted" role="status"><span className="spinner" aria-hidden="true" />{label}…</span>;
}

export function ErrorNote({ error, retry }: { error: Error | ApiError | null; retry?: () => void }) {
  if (!error) return null;
  const e = error as ApiError;
  return (
    <div className="banner banner-bad" role="alert">
      <b>{e.code ? `${e.code}: ` : ''}</b>{error.message}
      {e.fields?.length ? <ul className="small" style={{ margin: '6px 0 0 18px' }}>{e.fields.map((f, i) => <li key={i}><code>{f.loc}</code> — {f.msg}</li>)}</ul> : null}
      {retry && <div style={{ marginTop: 8 }}><button type="button" className="btn btn-sm" onClick={retry}>Retry</button></div>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string }>; onChange: (v: T) => void; label: string }) {
  return (
    <div className="switch" role="group" aria-label={label}>
      {options.map((o) => <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>)}
    </div>
  );
}

export function Meter({ value, max = 1, kind }: { value: number; max?: number; kind: 'ok' | 'warn' | 'bad' | 'info' }) {
  const color = { ok: 'var(--good)', warn: 'var(--warn)', bad: 'var(--bad)', info: 'var(--info)' }[kind];
  return <div className="meter" aria-hidden="true"><i style={{ width: `${Math.max(2, Math.min(100, (100 * value) / max))}%`, background: color }} /></div>;
}
