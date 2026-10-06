import { fmt } from '@/lib/format';

interface Props {
  edges: number[]; counts: number[]; unit: string; label: string;
  target?: number | null; window?: [number | null, number | null] | null; zeroCount?: number | null; zeroShare?: number | null;
  width?: number; height?: number;
}

/** The training distribution of a property with the target and its window; a zero spike is drawn apart. */
export function Histogram({ edges, counts, unit, label, target, window, zeroCount, zeroShare, width = 520, height = 160 }: Props) {
  const m = { l: 40, r: 12, t: 10, b: 28 };
  const zeroCol = zeroCount != null && zeroCount > 0 ? 44 : 0;
  const w = width - m.l - m.r - zeroCol, h = height - m.t - m.b;
  const x0 = edges[0], x1 = edges[edges.length - 1];
  const X = (v: number) => m.l + zeroCol + ((v - x0) / (x1 - x0 || 1)) * w;
  const max = Math.max(1, ...counts);
  const Y = (c: number) => m.t + h - (c / max) * h;
  const tick = (v: number) => <g key={v}><line x1={X(v)} x2={X(v)} y1={m.t + h} y2={m.t + h + 4} stroke="var(--faint)" /><text x={X(v)} y={m.t + h + 16} textAnchor="middle" fontSize={10} fill="var(--muted)">{fmt(v)}</text></g>;
  const ticks = [x0, x0 + (x1 - x0) / 4, x0 + (x1 - x0) / 2, x0 + (3 * (x1 - x0)) / 4, x1];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={`Training distribution of ${label}${target != null ? `, target ${fmt(target, unit)}` : ''}`}>
      {zeroCol > 0 && (
        <g>
          <rect x={m.l + 4} y={m.t} width={zeroCol - 12} height={h} fill="var(--seq-2)" rx={2} />
          <text x={m.l + zeroCol / 2 - 2} y={m.t + h / 2} textAnchor="middle" fontSize={10} fill="var(--muted)" transform={`rotate(-90 ${m.l + zeroCol / 2 - 2} ${m.t + h / 2})`}>= 0 · {zeroShare != null ? `${Math.round(100 * zeroShare)} %` : zeroCount}</text>
        </g>
      )}
      {window && (window[0] != null || window[1] != null) && (
        <rect x={X(window[0] ?? x0)} y={m.t} width={Math.max(1, X(window[1] ?? x1) - X(window[0] ?? x0))} height={h} fill="var(--c-targets)" opacity={0.12} />
      )}
      {counts.map((c, i) => <rect key={i} x={X(edges[i]) + 0.5} y={Y(c)} width={Math.max(1, X(edges[i + 1]) - X(edges[i]) - 1)} height={m.t + h - Y(c)} fill="var(--seq-4)"><title>{fmt(edges[i])}–{fmt(edges[i + 1], unit)}: {c} training materials</title></rect>)}
      {target != null && <line x1={X(target)} x2={X(target)} y1={m.t - 4} y2={m.t + h} stroke="var(--c-targets)" strokeWidth={2} />}
      {target != null && <text x={X(target)} y={m.t - 1} textAnchor="middle" fontSize={10} fill="var(--c-targets)" fontWeight={700}>target {fmt(target)}</text>}
      <line x1={m.l + zeroCol} x2={m.l + zeroCol + w} y1={m.t + h} y2={m.t + h} stroke="var(--line)" />
      {ticks.map(tick)}
      <text x={m.l + zeroCol + w} y={height - 2} textAnchor="end" fontSize={10} fill="var(--faint)">{unit}</text>
      <text x={4} y={m.t + 10} fontSize={10} fill="var(--faint)">{max}</text>
      <text x={4} y={m.t + h} fontSize={10} fill="var(--faint)">0</text>
    </svg>
  );
}
