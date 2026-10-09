import { useEffect, useMemo, useRef, useState } from 'react';

export interface ScatterPoint { id: string; x: number; y: number; v: number; label: string }

interface Props {
  points: ScatterPoint[];
  /** The colour scale's domain and its name (e.g. band gap in eV); points at exactly the domain's minimum are drawn faint. */
  colour: { min: number; max: number; label: string; unit?: string };
  selected?: string | null;
  onSelect?: (id: string) => void;
  xLabel?: string; yLabel?: string; width?: number; height?: number;
  /** When set, x and y are the same quantity (a predicted-versus-reference plot) and the identity line is drawn. */
  identity?: boolean;
}

const PAD = { l: 44, r: 12, t: 10, b: 32 };

/** A canvas scatter of up to tens of thousands of points, coloured by one value; hover names a point, click selects it.
 *  Drawn on a canvas (an SVG with 11,000 nodes is slow); the axes and the legend are SVG so they scale with the text. */
export function Scatter({ points, colour, selected, onSelect, xLabel, yLabel, width = 560, height = 420, identity }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<ScatterPoint | null>(null);
  const [dark, setDark] = useState(false);
  const box = useMemo(() => {
    if (!points.length) return { x0: 0, x1: 1, y0: 0, y1: 1 };
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of points) { if (p.x < x0) x0 = p.x; if (p.x > x1) x1 = p.x; if (p.y < y0) y0 = p.y; if (p.y > y1) y1 = p.y; }
    if (identity) { const lo = Math.min(x0, y0), hi = Math.max(x1, y1); x0 = y0 = lo; x1 = y1 = hi; }
    const mx = (x1 - x0 || 1) * 0.04, my = (y1 - y0 || 1) * 0.04;
    return { x0: x0 - mx, x1: x1 + mx, y0: y0 - my, y1: y1 + my };
  }, [points, identity]);
  const W = width - PAD.l - PAD.r, H = height - PAD.t - PAD.b;
  const X = (x: number) => PAD.l + ((x - box.x0) / (box.x1 - box.x0)) * W;
  const Y = (y: number) => PAD.t + H - ((y - box.y0) / (box.y1 - box.y0)) * H;
  const shade = (v: number, faint: boolean) => {
    const t = Math.max(0, Math.min(1, (v - colour.min) / ((colour.max - colour.min) || 1)));
    // one hue ramp (blue → violet → orange) that reads in both themes
    const h = 230 - 200 * t, s = 70, l = dark ? 62 : 46;
    return `hsla(${h} ${s}% ${l}% / ${faint ? 0.25 : 0.85})`;
  };
  useEffect(() => { setDark(document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && window.matchMedia('(prefers-color-scheme: dark)').matches)); }, []);
  useEffect(() => {
    const c = canvas.current; if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = width * dpr; c.height = height * dpr;
    const g = c.getContext('2d'); if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, width, height);
    if (identity) { g.strokeStyle = dark ? '#8f8e87' : '#898781'; g.setLineDash([4, 4]); g.beginPath(); g.moveTo(X(box.x0), Y(box.x0)); g.lineTo(X(box.x1), Y(box.x1)); g.stroke(); g.setLineDash([]); }
    const r = points.length > 4000 ? 2 : points.length > 800 ? 2.6 : 3.4;
    for (const p of points) {
      g.fillStyle = shade(p.v, p.v <= colour.min); g.beginPath(); g.arc(X(p.x), Y(p.y), r, 0, Math.PI * 2); g.fill();
    }
    for (const id of [hover?.id, selected]) {
      const p = points.find((q) => q.id === id); if (!p) continue;
      g.strokeStyle = dark ? '#f4f4f1' : '#0b0b0b'; g.lineWidth = 2; g.beginPath(); g.arc(X(p.x), Y(p.y), r + 3, 0, Math.PI * 2); g.stroke();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, box, width, height, hover, selected, dark, identity, colour.min, colour.max]);
  const nearest = (ev: React.MouseEvent) => {
    const rect = canvas.current!.getBoundingClientRect();
    const mx = ((ev.clientX - rect.left) / rect.width) * width, my = ((ev.clientY - rect.top) / rect.height) * height;
    let best: ScatterPoint | null = null, bd = 100;
    for (const p of points) { const d = (X(p.x) - mx) ** 2 + (Y(p.y) - my) ** 2; if (d < bd) { bd = d; best = p; } }
    return best;
  };
  const ticks = (a: number, b: number) => { const n = 5, out = []; for (let i = 0; i <= n; i++) out.push(a + ((b - a) * i) / n); return out; };
  return (
    <div className="scatter" style={{ position: 'relative', width: '100%', maxWidth: width }}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} aria-hidden="true">
        {ticks(box.x0, box.x1).map((t) => <g key={`x${t}`}><line x1={X(t)} x2={X(t)} y1={PAD.t + H} y2={PAD.t + H + 4} stroke="var(--muted)" /><text x={X(t)} y={PAD.t + H + 16} textAnchor="middle" fontSize={10} fill="var(--muted)">{t.toFixed(Math.abs(box.x1 - box.x0) < 5 ? 2 : 1)}</text></g>)}
        {ticks(box.y0, box.y1).map((t) => <g key={`y${t}`}><line x1={PAD.l - 4} x2={PAD.l} y1={Y(t)} y2={Y(t)} stroke="var(--muted)" /><text x={PAD.l - 6} y={Y(t) + 3} textAnchor="end" fontSize={10} fill="var(--muted)">{t.toFixed(Math.abs(box.y1 - box.y0) < 5 ? 2 : 1)}</text></g>)}
        <rect x={PAD.l} y={PAD.t} width={W} height={H} fill="none" stroke="var(--line)" />
        {xLabel && <text x={PAD.l + W / 2} y={height - 4} textAnchor="middle" fontSize={11} fill="var(--muted)">{xLabel}</text>}
        {yLabel && <text transform={`translate(12 ${PAD.t + H / 2}) rotate(-90)`} textAnchor="middle" fontSize={11} fill="var(--muted)">{yLabel}</text>}
      </svg>
      <canvas ref={canvas} style={{ width: '100%', height: 'auto', display: 'block', cursor: onSelect ? 'pointer' : 'default' }}
        role="img" aria-label={`${points.length} points coloured by ${colour.label}`}
        onMouseMove={(e) => setHover(nearest(e))} onMouseLeave={() => setHover(null)} onClick={(e) => { const p = nearest(e); if (p && onSelect) onSelect(p.id); }} />
      <div className="small muted" style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
        <span>{colour.label}:</span>
        <span style={{ display: 'inline-block', width: 120, height: 8, background: `linear-gradient(90deg, ${shade(colour.min + 1e-9, false)}, ${shade((colour.min + colour.max) / 2, false)}, ${shade(colour.max, false)})`, borderRadius: 4 }} />
        <span className="num">{colour.min.toFixed(1)}–{colour.max.toFixed(1)}{colour.unit ? ` ${colour.unit}` : ''}</span>
        <span style={{ marginLeft: 'auto' }} className="num">{hover ? `${hover.label} · ${hover.v.toFixed(2)}${colour.unit ? ` ${colour.unit}` : ''}` : points.length ? `${points.length.toLocaleString()} points` : ''}</span>
      </div>
    </div>
  );
}
