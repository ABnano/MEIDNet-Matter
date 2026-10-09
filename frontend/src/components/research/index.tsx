import { useEffect, useState, type ReactNode } from 'react';
import type { Grade } from '@/api/research';
import { research } from '@/api/research';
import { Spinner } from '@/components/ui';

/** A block verdict as plain text. Verdicts are results, not status badges, so they are never rendered as coloured pills. */
export function VerdictText({ grade, title }: { grade: Grade | string; title?: string }) {
  return <span className="mono verdict-text" title={title}>{grade}</span>;
}

export function Num({ v, d = 2, unit }: { v: number | null | undefined; d?: number; unit?: string }) {
  if (v === null || v === undefined || Number.isNaN(v)) return <span className="faint">—</span>;
  return <span className="num">{v.toFixed(d)}{unit ? ` ${unit}` : ''}</span>;
}

/** A read-only source view with line numbers, a download link and the checksum of what is shown. */
export function CodeViewer({ file }: { file: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    setText(null); setError(null);
    research.component(file, ctrl.signal).then(setText).catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => ctrl.abort();
  }, [file]);
  if (error) return <p className="error-text">The source could not be loaded: {error}</p>;
  if (text === null) return <Spinner label={`Loading ${file}`} />;
  const lines = text.split('\n');
  return (
    <div className="code-viewer">
      <div className="code-head">
        <span className="mono">{file}</span>
        <span className="small muted">{lines.length} lines</span>
        <a className="btn btn-sm" href={research.componentUrl(file)} download={file}>Download</a>
      </div>
      <pre tabIndex={0}><code>{lines.map((l, i) => <span className="code-line" key={i}><span className="ln" aria-hidden="true">{i + 1}</span>{l}{'\n'}</span>)}</code></pre>
    </div>
  );
}

/** The stages of a funnel as bars drawn to one scale. */
export function Funnel({ stages, unit = 'structures' }: { stages: Array<[string, number]>; unit?: string }) {
  const max = Math.max(1, ...stages.map((s) => s[1]));
  return (
    <div className="stack" style={{ gap: 6 }} role="list" aria-label="Funnel">
      {stages.map(([label, n]) => (
        <div className="funnel-stage" key={label} role="listitem">
          <span>{label}</span>
          <div className="bar" style={{ width: `${Math.max(1, (100 * n) / max)}%` }} aria-hidden="true" />
          <span className="num">{n}</span>
        </div>
      ))}
      <div className="small faint">{unit}</div>
    </div>
  );
}

interface Point { requested: number; delivered: number; accepted: boolean; label: string }
interface Band { requested: number; mean: number; sd: number | null }

/** Delivered against requested band gap: every relaxed cell as a point, the per-request mean ± sd, the identity line and the fit. */
export function ResponseCurve({ points, bands, fit, width = 560, height = 360, compact = false }: { points: Point[]; bands: Band[]; fit: { slope: number; intercept: number }; width?: number; height?: number; compact?: boolean }) {
  const m = compact ? { l: 40, r: 12, t: 10, b: 36 } : { l: 52, r: 16, t: 14, b: 44 };
  const max = 4.6;
  const X = (v: number) => m.l + (v / max) * (width - m.l - m.r);
  const Y = (v: number) => height - m.b - (Math.min(v, max) / max) * (height - m.t - m.b);
  const ticks = [0, 1, 2, 3, 4];
  return (
    <figure className="response-curve">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-labelledby="rc-title rc-desc">
        <title id="rc-title">Delivered band gap against requested band gap</title>
        <desc id="rc-desc">Each point is one relaxed structure as the judge reads it; bars are the mean and one standard deviation per request; the solid line is the identity and the dashed line the fitted response.</desc>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={X(v)} x2={X(v)} y1={Y(0)} y2={Y(max)} stroke="var(--line)" />
            <line x1={X(0)} x2={X(max)} y1={Y(v)} y2={Y(v)} stroke="var(--line)" />
            <text x={X(v)} y={Y(0) + 16} textAnchor="middle" fontSize={11} fill="var(--muted)">{v}</text>
            <text x={X(0) - 8} y={Y(v) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">{v}</text>
          </g>
        ))}
        <line x1={X(0)} y1={Y(0)} x2={X(max)} y2={Y(max)} stroke="var(--ink)" strokeWidth={1.5} />
        <line x1={X(0.5)} y1={Y(fit.intercept + fit.slope * 0.5)} x2={X(4)} y2={Y(fit.intercept + fit.slope * 4)} stroke="var(--c-targets)" strokeWidth={1.5} strokeDasharray="6 4" />
        {bands.map((b) => (
          <g key={b.requested}>
            {b.sd !== null && <line x1={X(b.requested)} x2={X(b.requested)} y1={Y(Math.max(0, b.mean - b.sd))} y2={Y(Math.min(max, b.mean + b.sd))} stroke="var(--c-targets)" strokeWidth={2} opacity={0.8} />}
            <line x1={X(b.requested) - 9} x2={X(b.requested) + 9} y1={Y(b.mean)} y2={Y(b.mean)} stroke="var(--c-targets)" strokeWidth={3} />
          </g>
        ))}
        {points.map((p, i) => (
          <circle key={i} cx={X(p.requested) + (((i % 5) - 2) * 4)} cy={Y(p.delivered)} r={p.accepted ? 5 : 3.5} fill={p.accepted ? 'var(--c-candidates)' : 'var(--faint)'} opacity={p.accepted ? 1 : 0.6}>
            <title>{p.label}: requested {p.requested.toFixed(1)}, delivered {p.delivered.toFixed(2)} eV</title>
          </circle>
        ))}
        <text x={(X(0) + X(max)) / 2} y={height - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">{compact ? 'requested (eV)' : 'requested band gap (eV)'}</text>
        <text transform={`translate(${compact ? 12 : 14} ${(Y(0) + Y(max)) / 2}) rotate(-90)`} textAnchor="middle" fontSize={11} fill="var(--muted)">{compact ? 'delivered (eV)' : 'delivered band gap, judge on the relaxed cell (eV)'}</text>
      </svg>
      {!compact && <figcaption className="small muted">Points: relaxed structures (filled when both judges accept them); bars: mean ± one standard deviation per request; solid line: identity; dashed: the fitted response.</figcaption>}
    </figure>
  );
}

export function KV({ rows }: { rows: Array<[string, ReactNode]> }) {
  return <dl className="kv">{rows.map(([k, v]) => <><dt key={`k${k}`}>{k}</dt><dd key={`v${k}`}>{v}</dd></>)}</dl>;
}
