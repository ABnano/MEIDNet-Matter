// Lockup generator: 1200x630 MEIDNet Matter full logo (artwork as inline SVG + wordmark).
// usage: node scripts/brand/matter_lockup.mjs <out.html> [jsonOverrides]; capture the page at 1200x630 as frontend/public/og.png
import { writeFileSync } from 'node:fs';

const f = (n) => +n.toFixed(1);
const pt = (p) => `${f(p[0])} ${f(p[1])}`;
const poly = (...ps) => 'M' + ps.map(pt).join('L') + 'Z';
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const mid = (a, b) => lerp(a, b, 0.5);
const bez = (p0, p1, p2, p3, t) => { const u = 1 - t; return [0, 1].map((k) => u * u * u * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t * t * t * p3[k]); };

export function lockup(o = {}) {
  const P = {
    cx: 606, top: 92, h: 318, hx: 0.94,                 // octahedron
    blockC: [1000, 252], A: 99, yaw: 30, pitch: 22,     // 2x2x2 lattice block: centre, half size
    beamEnd: 890, beamSpread: 88,
    lattice: 'glass', atomCols: 'lit', bodies: true, glows: true, rings: true,
    glass: 0.75, lineW: 1.3, bodyR: 8.5, atomR: 10.5,
    word: { size: 150, y: 600, gap: 36, matter: 'cool', weight2: 600, stroke: 4.5 },
    ...o,
  };
  const s = P.h / 443, X = (dx) => P.cx + dx * s * P.hx, Y = (dy) => P.top + dy * s;
  const T = [X(0), Y(0)], B = [X(-3), Y(443)], Lo = [X(-190), Y(193)], Li = [X(-143), Y(219)];
  const K = [X(10), Y(161)], F = [X(10), Y(275)], R = [X(181), Y(220)];

  const ya = (P.yaw * Math.PI) / 180, pa = (P.pitch * Math.PI) / 180;
  const proj = ([x, y, z]) => {
    const x1 = x * Math.cos(ya) + z * Math.sin(ya), z1 = -x * Math.sin(ya) + z * Math.cos(ya);
    const y2 = y * Math.cos(pa) - z1 * Math.sin(pa), z2 = y * Math.sin(pa) + z1 * Math.cos(pa);
    return [P.blockC[0] + x1 * P.A, P.blockC[1] - y2 * P.A, z2];
  };
  const defs = [], out = [];
  const lg = (id, a, b, stops, extra = '') => defs.push(`<linearGradient id="beam-${id}" gradientUnits="userSpaceOnUse" x1="${f(a[0])}" y1="${f(a[1])}" x2="${f(b[0])}" y2="${f(b[1])}"${extra}>${stops.map(([o2, c, op]) => `<stop offset="${o2}" stop-color="${c}"${op != null && op !== 1 ? ` stop-opacity="${op}"` : ''}/>`).join('')}</linearGradient>`);
  const blur = (id, sd) => defs.push(`<filter id="beam-${id}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${sd}"/></filter>`);
  blur('blur10', 10); blur('blur28', 28); blur('blur45', 45); blur('blur4', P.bandBlur ?? 4);

  // ---------- 1. target-property streams (dots on curved lines), Prism's composition
  const streams = [
    { c: '#2f7cf6', y0: 52, bend: 0.62 },
    { c: '#10b981', y0: 138, bend: 0.5 },
    { c: '#8b5cf6', y0: 222, bend: 0.3 },
    { c: '#f97316', y0: 318, bend: 0.5 },
    { c: '#f5b70b', y0: 404, bend: 0.62 },
  ];
  const dotsT = [[0.17, 17], [0.37, 13.5], [0.56, 10.5], [0.72, 8]];
  out.push(`<g>`);
  for (const st of streams) {
    const p0 = [-30, st.y0], p1 = [200, st.y0 + (Li[1] - st.y0) * 0.04], p2 = [Li[0] - 190, Li[1] + (st.y0 - Li[1]) * (1 - st.bend) * 0.5], p3 = Li;
    const d = `M${pt(p0)}C${pt(p1)} ${pt(p2)} ${pt(p3)}`;
    out.push(`<path d="${d}" fill="none" stroke="${st.c}" stroke-width="18" stroke-linecap="round" opacity="${P.trail ?? 0.16}" filter="url(#beam-blur10)"/>`);
    out.push(`<path d="${d}" fill="none" stroke="${st.c}" stroke-width="3.2" stroke-linecap="round" opacity="0.9"/>`);
    dotsT.forEach(([t, r], j) => {
      const q = bez(p0, p1, p2, p3, t);
      if (j === 0 && P.rings) out.push(`<circle cx="${f(q[0])}" cy="${f(q[1])}" r="${f(r + 8)}" fill="none" stroke="${st.c}" stroke-width="2.6" opacity="0.35"/>`);
      out.push(`<circle cx="${f(q[0])}" cy="${f(q[1])}" r="${r}" fill="${st.c}"/>`);
      out.push(`<circle cx="${f(q[0] - r * 0.3)}" cy="${f(q[1] - r * 0.32)}" r="${f(r * 0.38)}" fill="#fff" opacity="0.28"/>`);
    });
  }
  out.push(`</g>`);

  // ---------- 2. spectrum
  const yT = P.blockC[1] - P.beamSpread, yB = P.blockC[1] + P.beamSpread;
  const bandCols = ['#38bdf8', '#10b981', '#facc15', '#f97316', '#c084fc'], n = bandCols.length;
  lg('fade', R, [P.beamEnd, R[1]], [[0, '#fff', 1], [0.55, '#fff', 0.8], [1, '#fff', 0.3]]);
  defs.push(`<mask id="beam-fade-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="1200" height="630"><path d="${poly(R, [P.beamEnd, yT - 10], [P.beamEnd, yB + 10])}" fill="url(#beam-fade)"/></mask>`);
  const bands = bandCols.map((c, i) => {
    const a = yT + ((yB - yT) * (i + 0.09)) / n, b = yT + ((yB - yT) * (i + 0.91)) / n;
    return `<path d="${poly(R, [P.beamEnd, a], [P.beamEnd, b])}" fill="${c}"/>`;
  }).join('');
  out.push(`<g opacity="0.55" filter="url(#beam-blur10)">${bands}</g>`);
  // the crisp bands softened toward Prism's blurred rainbow (the judge's fix): lower, and slightly blurred
  out.push(`<g mask="url(#beam-fade-mask)" opacity="${P.bandOp ?? 0.72}" filter="url(#beam-blur4)">${bands}</g>`);

  // ---------- 3. octahedron
  lg('outer', T, B, [[0, '#2f80ed'], [0.2, '#22c3e6'], [0.46, '#14b88a'], [0.74, '#16b3b0'], [1, '#2563eb']]);
  lg('facet-tl', Li, mid(T, K), [[0, '#d7f7ec'], [0.28, '#6cbcf5'], [0.7, '#2f6fe8'], [1, '#1d4ed8']]);
  lg('facet-tr', mid(T, K), lerp(mid(T, R), R, 0.15), [[0, '#eef5ff'], [0.32, '#a3cbfb'], [1, '#2f7cf6']]);
  lg('facet-bl', Li, mid(F, B), [[0, '#fff1c4'], [0.35, '#fbc54a'], [0.8, '#f8a531'], [1, '#f59e0b']]);
  lg('facet-br', mid(F, B), lerp(mid(R, B), R, 0.1), [[0, '#ebe5ff'], [0.38, '#a48bfa'], [1, '#4f46e5']]);
  lg('girdle-l', Li, mid(K, F), [[0, '#dcefff'], [0.3, '#5d9cf3'], [1, '#1e4fd6']]);
  lg('girdle-r', mid(K, F), R, [[0, '#c9b9fd'], [0.5, '#7c3aed'], [1, '#8f6af5']]);
  defs.push(`<radialGradient id="beam-entry-glow" cx="${f(Li[0])}" cy="${f(Li[1])}" r="${P.entryR ?? 46}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff" stop-opacity="${P.entryOp ?? 0.7}"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>`);
  defs.push(`<clipPath id="beam-octa-clip"><path d="${poly(T, R, B, Lo)}"/></clipPath>`);
  lg('rim', T, B, [[0, '#3b82f6'], [0.5, '#2563eb'], [1, '#4f46e5']]);
  out.push(`<path d="${poly(T, R, B, Lo)}" fill="#7c9cf5" opacity="${P.octGlow ?? 0.3}" filter="url(#beam-blur28)"/>`);
  out.push(`<path d="${poly(T, Lo, B, Li)}" fill="url(#beam-outer)"/>`);
  out.push(`<path d="${poly(T, Li, K)}" fill="url(#beam-facet-tl)"/>`);
  out.push(`<path d="${poly(T, K, R)}" fill="url(#beam-facet-tr)"/>`);
  out.push(`<path d="${poly(Li, K, F)}" fill="url(#beam-girdle-l)"/>`);
  out.push(`<path d="${poly(K, R, F)}" fill="url(#beam-girdle-r)"/>`);
  out.push(`<path d="${poly(Li, F, B)}" fill="url(#beam-facet-bl)"/>`);
  out.push(`<path d="${poly(F, R, B)}" fill="url(#beam-facet-br)"/>`);
  out.push(`<g clip-path="url(#beam-octa-clip)"><circle cx="${f(Li[0])}" cy="${f(Li[1])}" r="${P.entryR ?? 46}" fill="url(#beam-entry-glow)"/></g>`);
  // outer rim on the right silhouette, so the pale ridge zone never dissolves into a white page
  out.push(`<path d="M${pt(T)}L${pt(R)}L${pt(B)}" fill="none" stroke="url(#beam-rim)" stroke-width="${P.rimW ?? 2.2}" stroke-linejoin="round" opacity="0.85"/>`);
  out.push(`<path d="M${pt(T)}L${pt(Li)}L${pt(B)}M${pt(Li)}L${pt(K)}L${pt(R)}M${pt(Li)}L${pt(F)}L${pt(R)}M${pt(T)}L${pt(K)}L${pt(F)}L${pt(B)}" fill="none" stroke="#fff" stroke-width="2.6" stroke-linejoin="round" opacity="0.92"/>`);

  // ---------- 4. the crystal: a 2x2x2 block of cubic cells the spectrum lands on
  const g3 = [-1, 0, 1];
  const L = (x, y, z) => proj([x, y, z]);
  const left = [L(-1, 1, -1), L(-1, 1, 1), L(-1, -1, 1), L(-1, -1, -1)];
  const front = [L(-1, 1, 1), L(1, 1, 1), L(1, -1, 1), L(-1, -1, 1)];
  const topF = [L(-1, 1, -1), L(1, 1, -1), L(1, 1, 1), L(-1, 1, 1)];
  const sil = [L(-1, 1, -1), L(1, 1, -1), L(1, 1, 1), L(1, -1, 1), L(-1, -1, 1), L(-1, -1, -1)];
  if (P.glows) {
    const C = P.blockC, gl = [[-60, -95, 95, '#60a5fa', 0.42], [40, -10, 105, '#a78bfa', 0.42], [120, -70, 80, '#34d399', 0.3], [-30, 105, 85, '#fdba74', 0.42], [95, 95, 80, '#fde047', 0.32], [-120, 10, 70, '#7dd3fc', 0.3]];
    out.push(`<g filter="url(#beam-blur45)">${gl.map(([dx, dy, r, c, op]) => `<circle cx="${C[0] + dx}" cy="${C[1] + dy}" r="${r}" fill="${c}" opacity="${op}"/>`).join('')}</g>`);
  }
  const gk = P.glass ?? 1;
  lg('cell-front', front[0], front[2], [[0, '#8b9bff', 0.34 * gk], [1, '#6a3ff0', 0.42 * gk]]);
  lg('cell-left', left[0], left[2], [[0, '#e0f2fe', 0.55 * gk], [1, '#c7d2fe', 0.55 * gk]]);
  lg('cell-top', topF[0], topF[2], [[0, '#eef1ff', 0.7 * gk], [1, '#b9c3ff', 0.7 * gk]]);
  defs.push(`<clipPath id="beam-cell-left-clip"><path d="${poly(...left)}"/></clipPath>`);
  // lattice lines, back to front
  const lines = [];
  for (const a of g3) for (const b of g3) {
    lines.push([[-1, a, b], [1, a, b]], [[a, -1, b], [a, 1, b]], [[a, b, -1], [a, b, 1]]);
  }
  const depth = (p) => proj(p)[2];
  const lineMid = (l) => depth(l[0].map((q, k) => (q + l[1][k]) / 2));
  lines.sort((p, q) => lineMid(p) - lineMid(q));
  const dmin = -1.8, dmax = 1.8, dn = (d) => (d - dmin) / (dmax - dmin);
  const onSurface = (l) => l[0].every((q, k) => q === l[1][k] ? Math.abs(q) === 1 : true) && l[0].some((q, k) => q === l[1][k] && Math.abs(q) === 1);
  out.push(`<path d="${poly(...left)}" fill="url(#beam-cell-left)"/>`);
  // projected spectrum on the landing face
  {
    const far = Math.max(...left.map((q) => q[0])) + 10, k = (far - R[0]) / (P.beamEnd - R[0]);
    out.push(`<g clip-path="url(#beam-cell-left-clip)" opacity="0.62">` + bandCols.map((c, i) => {
      const a = R[1] + (yT + ((yB - yT) * i) / n - R[1]) * k, b = R[1] + (yT + ((yB - yT) * (i + 1)) / n - R[1]) * k;
      return `<path d="${poly(R, [far, a], [far, b])}" fill="${c}"/>`;
    }).join('') + `</g>`);
  }
  out.push(`<path d="${poly(...topF)}" fill="url(#beam-cell-top)"/>`);
  out.push(`<path d="${poly(...front)}" fill="url(#beam-cell-front)"/>`);
  for (const l of lines) {
    const t = dn(lineMid(l)), surf = onSurface(l);
    const col = surf ? '#ffffff' : '#c7d2fe';
    out.push(`<path d="M${pt(L(...l[0]))}L${pt(L(...l[1]))}" stroke="${col}" stroke-width="${f((P.lineW ?? 1.6) + 1.4 * t)}" opacity="${f(0.45 + 0.5 * t)}" stroke-linecap="round"/>`);
  }
  out.push(`<path d="${poly(...sil)}" fill="none" stroke="#6366f1" stroke-width="2.4" stroke-linejoin="round" opacity="0.75"/>`);
  // atoms
  const radial = (id, c1, c2) => defs.push(`<radialGradient id="beam-${id}" cx="0.36" cy="0.32" r="0.72"><stop offset="0" stop-color="#ffffff"/><stop offset="0.3" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></radialGradient>`);
  radial('atom-violet', '#a78bfa', '#6d28d9'); radial('atom-teal', '#5eead4', '#0f766e');
  if (P.atomCols === 'layers') radial('atom-blue', '#60a5fa', '#1d4ed8');
  radial('atom-orange', '#fdba74', '#ea580c'); radial('atom-yellow', '#fde68a', '#d97706'); radial('atom-green', '#6ee7b7', '#047857'); radial('atom-sky', '#7dd3fc', '#0284c7');
  const atoms = [];
  for (const x of g3) for (const y of g3) for (const z of g3) atoms.push({ p: [x, y, z], kind: 'corner' });
  if (P.bodies) for (const x of [-0.5, 0.5]) for (const y of [-0.5, 0.5]) for (const z of [-0.5, 0.5]) atoms.push({ p: [x, y, z], kind: 'body' });
  atoms.sort((a, b) => depth(a.p) - depth(b.p));
  const litCols = ['atom-sky', 'atom-green', 'atom-yellow', 'atom-orange', 'atom-violet'];
  const colorOf = (a) => {
    if (a.kind === 'body') return 'atom-teal';
    if (P.atomCols === 'lit') {
      if (a.p[0] !== -1) return 'atom-violet';
      // atoms on the landing face take the colour of the spectrum band that falls on them
      const q = proj(a.p), k = (q[0] - R[0]) / (P.beamEnd - R[0]);
      const yAtBeamEnd = R[1] + (q[1] - R[1]) / k, band = Math.floor(((yAtBeamEnd - yT) / (yB - yT)) * n);
      return band >= 0 && band < n ? litCols[band] : 'atom-violet';
    }
    if (P.atomCols === 'violet') return 'atom-violet';
    // spectrum layers: top = sky/blue, middle = violet, bottom = orange/yellow
    const y = a.p[1];
    return y === 1 ? (a.p[0] + a.p[2] > 0 ? 'atom-blue' : 'atom-sky') : y === 0 ? 'atom-violet' : (a.p[0] + a.p[2] > 0 ? 'atom-orange' : 'atom-yellow');
  };
  for (const a of atoms) {
    const q = proj(a.p), t = dn(q[2]);
    const r = (a.kind === 'body' ? (P.bodyR ?? 9.5) : (P.atomR ?? 11)) * (0.78 + 0.32 * t);
    out.push(`<circle cx="${f(q[0])}" cy="${f(q[1])}" r="${f(r)}" fill="url(#beam-${colorOf(a)})" opacity="${f(a.kind === 'body' ? 0.75 : 0.72 + 0.28 * t)}"/>`);
  }

  const W = P.word;
  const matterGrad = W.matter === 'cool'
    ? 'linear-gradient(90deg,#2563eb 0%,#0ea5e9 26%,#14b8a6 46%,#6366f1 72%,#8b5cf6 100%)'
    : W.matter === 'rainbow' ? 'linear-gradient(90deg,#2563eb,#10b981,#8b5cf6,#f97316,#f59e0b)' : W.matter;
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>MEIDNet Matter</title>
<meta name="viewport" content="width=1200">
<style>
  html, body { margin: 0; background: #ffffff; }
  .card { position: relative; width: 1200px; height: 630px; overflow: hidden; background: #ffffff; }
  .art { position: absolute; left: 0; top: 0; width: 1200px; height: 630px; }
  .word { position: absolute; left: 0; right: 0; top: ${W.y - W.size}px; height: ${W.size * 1.25}px; display: flex; justify-content: center; align-items: baseline; gap: ${W.gap}px;
          font-family: 'Segoe UI Variable Display', 'Segoe UI', 'Plus Jakarta Sans', system-ui, sans-serif; font-size: ${W.size}px; line-height: 1; letter-spacing: -0.01em; white-space: nowrap; }
  .meid { font-weight: 700; color: #0f1f3d; -webkit-text-stroke: ${W.stroke}px #0f1f3d; }
  .matter { font-weight: ${W.weight2}; background: ${matterGrad}; -webkit-background-clip: text; background-clip: text; color: transparent; }
</style></head>
<body><div class="card">
<svg class="art" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" aria-hidden="true"><defs>${defs.join('')}</defs>${out.join('')}</svg>
<div class="word"><span class="meid">MEIDNet</span><span class="matter">Matter</span></div>
</div></body></html>
`;
  return html;
}

if (process.argv[2]) {
  const o = process.argv[3] ? JSON.parse(process.argv[3]) : {};
  writeFileSync(process.argv[2], lockup(o));
  console.log('wrote', process.argv[2]);
}
