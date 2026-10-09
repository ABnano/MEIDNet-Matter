export interface Series { name: string; values: Array<number | null>; colour?: string; dashed?: boolean }

interface Props { x: number[]; series: Series[]; xLabel?: string; yLabel?: string; width?: number; height?: number; yMin?: number; reference?: { value: number; label: string } | null }

const PAD = { l: 48, r: 12, t: 10, b: 30 };
const COLOURS = ['var(--p1)', '#d97706', '#0f766e', '#be185d', '#2563eb'];

/** One or more curves over epochs (training loss, validation error), with an optional horizontal reference line
 *  (the full model's error on the same materials). Plain SVG; values are numbers the page already holds. */
export function LineChart({ x, series, xLabel, yLabel, width = 480, height = 220, yMin, reference }: Props) {
  const W = width - PAD.l - PAD.r, H = height - PAD.t - PAD.b;
  const vals = series.flatMap((s) => s.values.filter((v): v is number => v !== null && Number.isFinite(v)));
  if (reference) vals.push(reference.value);
  const y0 = yMin ?? Math.min(0, ...vals), y1 = vals.length ? Math.max(...vals) * 1.05 || 1 : 1;
  const x0 = x.length ? x[0] : 0, x1 = x.length ? x[x.length - 1] : 1;
  const X = (v: number) => PAD.l + ((v - x0) / ((x1 - x0) || 1)) * W;
  const Y = (v: number) => PAD.t + H - ((v - y0) / ((y1 - y0) || 1)) * H;
  const path = (s: Series) => s.values.map((v, i) => (v === null || !Number.isFinite(v) ? null : `${i === 0 || s.values[i - 1] === null ? 'M' : 'L'}${X(x[i]).toFixed(1)},${Y(v).toFixed(1)}`)).filter(Boolean).join(' ');
  const yt = [0, 0.25, 0.5, 0.75, 1].map((f) => y0 + (y1 - y0) * f);
  const xt = x.length > 1 ? [x0, x0 + (x1 - x0) * 0.5, x1] : x;
  return (
    <figure className="linechart" style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={`${series.map((s) => s.name).join(', ')} over ${xLabel ?? 'x'}`}>
        {yt.map((t) => <g key={t}><line x1={PAD.l} x2={PAD.l + W} y1={Y(t)} y2={Y(t)} stroke="var(--line)" /><text x={PAD.l - 6} y={Y(t) + 3} textAnchor="end" fontSize={10} fill="var(--muted)">{t.toFixed(Math.abs(y1 - y0) < 2 ? 2 : 1)}</text></g>)}
        {xt.map((t) => <text key={t} x={X(t)} y={PAD.t + H + 14} textAnchor="middle" fontSize={10} fill="var(--muted)">{Math.round(t)}</text>)}
        {reference && <g><line x1={PAD.l} x2={PAD.l + W} y1={Y(reference.value)} y2={Y(reference.value)} stroke="var(--muted)" strokeDasharray="5 4" /><text x={PAD.l + W - 4} y={Y(reference.value) - 4} textAnchor="end" fontSize={10} fill="var(--muted)">{reference.label}</text></g>}
        {series.map((s, i) => <path key={s.name} d={path(s)} fill="none" stroke={s.colour ?? COLOURS[i % COLOURS.length]} strokeWidth={2} strokeDasharray={s.dashed ? '4 3' : undefined} />)}
        {xLabel && <text x={PAD.l + W / 2} y={height - 2} textAnchor="middle" fontSize={11} fill="var(--muted)">{xLabel}</text>}
        {yLabel && <text transform={`translate(12 ${PAD.t + H / 2}) rotate(-90)`} textAnchor="middle" fontSize={11} fill="var(--muted)">{yLabel}</text>}
      </svg>
      <figcaption className="small muted" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {series.map((s, i) => <span key={s.name}><span style={{ display: 'inline-block', width: 14, height: 3, background: s.colour ?? COLOURS[i % COLOURS.length], verticalAlign: 'middle', marginRight: 4 }} />{s.name}{s.values.length ? <span className="num"> {(() => { const last = [...s.values].reverse().find((v) => v !== null); return last == null ? '' : last.toFixed(3); })()}</span> : null}</span>)}
      </figcaption>
    </figure>
  );
}
