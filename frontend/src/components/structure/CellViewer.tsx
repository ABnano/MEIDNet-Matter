import { useEffect, useMemo, useRef, useState } from 'react';
import { bondsFor, expandCell, fracToCart, project3d, type CellStructure, type Vec3 } from '@/lib/lattice';
import { CPK, RADII } from '@/lib/periodic';

interface Props { structure: CellStructure; size?: number; title: string; labels?: boolean; interactive?: boolean; supercell?: number; className?: string }

/** Ball-and-stick SVG of a unit cell: drag or arrow keys rotate, 0 resets, double-click spins. */
export function CellViewer({ structure, size = 150, title, labels = false, interactive = true, supercell = 1, className }: Props) {
  const [view, setView] = useState({ yaw: -0.55, pitch: 0.35 });
  const [spin, setSpin] = useState(false);
  const drag = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (!spin) return;
    const step = () => { setView((v) => ({ ...v, yaw: v.yaw + 0.02 })); raf.current = requestAnimationFrame(step); };
    raf.current = requestAnimationFrame(step);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [spin]);

  const scene = useMemo(() => {
    const atoms = expandCell(structure, supercell);
    const bonds = bondsFor(atoms);
    const n = supercell;
    const corners: Vec3[] = [];
    for (const a of [0, n]) for (const b of [0, n]) for (const c of [0, n]) corners.push(fracToCart([a, b, c], structure.M));
    const edges: Array<[number, number]> = [];
    for (let i = 0; i < 8; i++) for (let j = i + 1; j < 8; j++) { let diff = 0; for (const k of [0, 1, 2]) if (((i >> (2 - k)) & 1) !== ((j >> (2 - k)) & 1)) diff++; if (diff === 1) edges.push([i, j]); }
    const centre: Vec3 = [0, 1, 2].map((k) => corners.reduce((s, c) => s + c[k], 0) / 8) as Vec3;
    return { atoms, bonds, corners, edges, centre };
  }, [structure, supercell]);

  const { yaw, pitch } = view;
  const P = (p: Vec3): Vec3 => project3d([p[0] - scene.centre[0], p[1] - scene.centre[1], p[2] - scene.centre[2]], yaw, pitch);
  const pc = scene.corners.map(P);
  const pa = scene.atoms.map((a) => ({ ...a, q: P(a.p) }));
  const radA = (n: string) => 0.18 + 0.16 * (RADII[n] ?? 1.4);
  const ext = Math.max(...pc.flatMap((q) => [Math.abs(q[0]), Math.abs(q[1])]), ...pa.flatMap((a) => [Math.abs(a.q[0]) + radA(a.n), Math.abs(a.q[1]) + radA(a.n)])) * 1.08 || 1;
  const sc = size / 2 / ext, cx = size / 2, cy = size / 2;
  const X = (q: Vec3) => cx + q[0] * sc, Y = (q: Vec3) => cy - q[1] * sc;
  const col = (n: string) => CPK[n] ?? '#999999';
  const items: Array<{ z: number; el: React.ReactNode }> = [];
  scene.bonds.forEach(([i, j], k) => {
    const a = pa[i], b = pa[j];
    const m: Vec3 = [(a.q[0] + b.q[0]) / 2, (a.q[1] + b.q[1]) / 2, (a.q[2] + b.q[2]) / 2];
    items.push({ z: (a.q[2] + m[2]) / 2, el: <line key={`b${k}a`} x1={X(a.q)} y1={Y(a.q)} x2={X(m)} y2={Y(m)} stroke={col(a.n)} strokeWidth={2.2} strokeLinecap="round" /> });
    items.push({ z: (b.q[2] + m[2]) / 2, el: <line key={`b${k}b`} x1={X(b.q)} y1={Y(b.q)} x2={X(m)} y2={Y(m)} stroke={col(b.n)} strokeWidth={2.2} strokeLinecap="round" /> });
  });
  pa.forEach((a, k) => {
    const r = radA(a.n) * sc;
    items.push({ z: a.q[2], el: (
      <g key={`a${k}`}>
        <circle cx={X(a.q)} cy={Y(a.q)} r={r} fill={col(a.n)} stroke="rgba(0,0,0,.35)" strokeWidth={1}><title>{a.n}{a.g ? ` (site ${a.g})` : ''}</title></circle>
        <circle cx={X(a.q) - r * 0.35} cy={Y(a.q) - r * 0.35} r={r * 0.32} fill="#fff" opacity={0.45} style={{ pointerEvents: 'none' }} />
        {labels && r >= 9 && <text x={X(a.q)} y={Y(a.q) + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} fill="#111" stroke="#fff" strokeWidth={2.5} paintOrder="stroke" style={{ pointerEvents: 'none' }}>{a.n}</text>}
      </g>) });
  });
  items.sort((p, q) => p.z - q.z);
  const composition = Object.entries(structure.names.reduce<Record<string, number>>((m, n) => ((m[n] = (m[n] ?? 0) + 1), m), {})).map(([n, c]) => `${c} ${n}`).join(', ');

  return (
    <div className={`cell-viewer ${className ?? ''}`}>
      <svg
        viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Unit cell of ${title}: ${composition}`} tabIndex={interactive ? 0 : -1}
        onPointerDown={interactive ? (e) => { drag.current = { x: e.clientX, y: e.clientY, yaw, pitch }; (e.target as Element).setPointerCapture?.(e.pointerId); } : undefined}
        onPointerMove={interactive ? (e) => { const d = drag.current; if (!d) return; setView({ yaw: d.yaw + (e.clientX - d.x) * 0.012, pitch: Math.max(-1.4, Math.min(1.4, d.pitch + (e.clientY - d.y) * 0.012)) }); } : undefined}
        onPointerUp={() => (drag.current = null)} onPointerCancel={() => (drag.current = null)}
        onDoubleClick={interactive ? () => setSpin((s) => !s) : undefined}
        onKeyDown={interactive ? (e) => {
          if (e.key === 'ArrowLeft') setView((v) => ({ ...v, yaw: v.yaw - 0.1 }));
          else if (e.key === 'ArrowRight') setView((v) => ({ ...v, yaw: v.yaw + 0.1 }));
          else if (e.key === 'ArrowUp') setView((v) => ({ ...v, pitch: Math.min(1.4, v.pitch + 0.1) }));
          else if (e.key === 'ArrowDown') setView((v) => ({ ...v, pitch: Math.max(-1.4, v.pitch - 0.1) }));
          else if (e.key === '0') setView({ yaw: -0.55, pitch: 0.35 });
          else return;
          e.preventDefault();
        } : undefined}
      >
        {scene.edges.map(([i, j], k) => <line key={`e${k}`} x1={X(pc[i])} y1={Y(pc[i])} x2={X(pc[j])} y2={Y(pc[j])} stroke="var(--faint)" strokeWidth={1} />)}
        {items.map((it) => it.el)}
      </svg>
    </div>
  );
}

export function resetView() { /* exposed for tests of the keyboard handling */ }
