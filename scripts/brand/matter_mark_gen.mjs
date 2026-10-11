// The geometry of the MEIDNet Matter mark ("beam" design of the 2026-10-11 logo study; built by matter_mark.mjs):
//   target-property streams -> glassy MEIDNet octahedron (Prism's) -> dispersed spectrum -> cubic unit cell.
// usage: node scripts/brand/matter_mark_gen.mjs <out.svg> [jsonOverrides]   (matter_mark.mjs sets the final values)
import { writeFileSync } from 'node:fs';

const f = (n) => +n.toFixed(2);
const pt = (p) => `${f(p[0])} ${f(p[1])}`;
const poly = (...ps) => 'M' + ps.map(pt).join('L') + 'Z';
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const mid = (a, b) => lerp(a, b, 0.5);

export const DEFAULTS = {
  // octahedron: axis x, top y, height, horizontal squeeze relative to Prism's proportions
  cx: 20, top: 9, h: 46, hx: 0.78, rimW: 0.5,
  // unit cell: centre, half edge, yaw (turns its left face to the beam), pitch (seen from above)
  cubeC: [51.7, 32.4], cubeA: 7.6, yaw: 30, pitch: 22, bodyInside: true, frontOp: 0.8, lit: false,
  beamEnd: 45.5, beamSpread: 8.5, bandGap: 0.18, stripes: 0.6,
  atomR: 1.75, bodyR: 2.1, edgeW: 0.42,
  streamSpread: 3.0, streamW: 1.0, streamFrom: -16,
  small: 24,          // at or below this rendered width (CSS px) the favicon simplifications apply; 0 = off
  glow: true,
  topOp: 0.97,        // opacity of the cell's top face (glass: ~0.6)
  bandBlur: 0,        // softness of the spectrum bands, in viewBox units (Prism's beam is soft: ~0.6)
  prefix: 'beam-',    // id/class prefix of the output
};

export function build(o = {}) {
  const P = { ...DEFAULTS, ...o };
  // Prism's octahedron, measured on its 512 px mark relative to the top vertex (see work/grid.png)
  const s = P.h / 443, X = (dx) => P.cx + dx * s * P.hx, Y = (dy) => P.top + dy * s;
  const T = [X(0), Y(0)], B = [X(-3), Y(443)], Lo = [X(-190), Y(193)], Li = [X(-143), Y(219)];
  const K = [X(10), Y(161)], F = [X(10), Y(275)], R = [X(181), Y(220)];

  // unit cell, orthographic
  const ya = (P.yaw * Math.PI) / 180, pa = (P.pitch * Math.PI) / 180;
  const proj = ([x, y, z]) => {
    const x1 = x * Math.cos(ya) + z * Math.sin(ya), z1 = -x * Math.sin(ya) + z * Math.cos(ya);
    const y2 = y * Math.cos(pa) - z1 * Math.sin(pa), z2 = y * Math.sin(pa) + z1 * Math.cos(pa);
    return [P.cubeC[0] + x1 * P.cubeA, P.cubeC[1] - y2 * P.cubeA, z2];
  };
  const v = (x, y, z) => proj([x, y, z]);
  const corners = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) corners.push([x, y, z]);
  const isHidden = (c) => c[0] === 1 && c[1] === -1 && c[2] === -1;     // the one corner behind the cell
  const edges = [];
  for (let i = 0; i < 8; i++) for (let j = i + 1; j < 8; j++) {
    const a = corners[i], b = corners[j];
    if (a.filter((q, k) => q !== b[k]).length === 1) edges.push([a, b]);
  }
  const front = [v(-1, 1, 1), v(1, 1, 1), v(1, -1, 1), v(-1, -1, 1)];
  const left = [v(-1, 1, -1), v(-1, 1, 1), v(-1, -1, 1), v(-1, -1, -1)];
  const top = [v(-1, 1, -1), v(1, 1, -1), v(1, 1, 1), v(-1, 1, 1)];
  const sil = [v(-1, 1, -1), v(1, 1, -1), v(1, 1, 1), v(1, -1, 1), v(-1, -1, 1), v(-1, -1, -1)];
  const C0 = proj([0, 0, 0]);

  // ---- defs
  const defs = [];
  const stopsOf = (stops) => stops.map(([o, c, op, cls]) => `<stop offset="${o}" stop-color="${c}"${op != null && op !== 1 ? ` stop-opacity="${op}"` : ''}${cls ? ` class="beam-${cls}"` : ''}/>`).join('');
  const lg = (id, a, b, stops) => defs.push(`<linearGradient id="beam-${id}" gradientUnits="userSpaceOnUse" x1="${f(a[0])}" y1="${f(a[1])}" x2="${f(b[0])}" y2="${f(b[1])}">${stopsOf(stops)}</linearGradient>`);
  const yT = P.cubeC[1] - P.beamSpread, yB = P.cubeC[1] + P.beamSpread;

  // facets (pale "glass" stops carry a class so the favicon size can saturate them)
  lg('outer', T, B, [[0, '#2f80ed'], [0.2, '#22c3e6'], [0.46, '#14b88a'], [0.74, '#16b3b0'], [1, '#2563eb']]);
  lg('facet-tl', Li, mid(T, K), [[0, '#c8f2e6', 1, 'p-tl'], [0.28, '#6cbcf5'], [0.7, '#2f6fe8'], [1, '#1d4ed8']]);
  lg('facet-tr', mid(T, K), lerp(mid(T, R), R, 0.15), [[0, '#e3efff', 1, 'p-tr'], [0.32, '#9cc8fb', 1, 'p-tr2'], [1, '#2f7cf6']]);
  lg('facet-bl', Li, mid(F, B), [[0, '#fde7a6', 1, 'p-bl'], [0.35, '#fbc54a'], [0.8, '#f8a531'], [1, '#f59e0b']]);
  lg('facet-br', mid(F, B), lerp(mid(R, B), R, 0.1), [[0, '#e0d8fe', 1, 'p-br'], [0.38, '#a48bfa'], [1, '#4f46e5']]);
  lg('girdle-l', Li, mid(K, F), [[0, '#cfe8ff', 1, 'p-gl'], [0.3, '#5d9cf3'], [1, '#1e4fd6']]);
  lg('girdle-r', mid(K, F), R, [[0, '#c4b2fd', 1, 'p-gr'], [0.5, '#7c3aed'], [1, '#8f6af5']]);
  lg('rim', T, B, [[0, '#3b82f6'], [0.5, '#2563eb'], [1, '#4f46e5']]);
  // beam
  lg('spectrum', [0, yT], [0, yB], [[0, '#38bdf8'], [0.26, '#10b981'], [0.5, '#f5c518'], [0.72, '#f97316'], [1, '#a855f7']]);
  lg('fade', R, [P.beamEnd, R[1]], [[0, '#fff', 1], [0.6, '#fff', 0.75], [1, '#fff', 0.25]]);
  defs.push(`<mask id="beam-fade-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64"><path d="${poly(R, [P.beamEnd, yT], [P.beamEnd, yB])}" fill="url(#beam-fade)"/></mask>`);
  // cell faces
  lg('cell-front', front[0], front[2], [[0, '#7383ff', 0.95], [1, '#6a3ff0', 0.95]]);
  lg('cell-left', left[0], left[2], [[0, '#e8f4ff', 0.9, 'p-cl'], [1, '#c7d2fe', 0.9, 'p-cl2']]);
  lg('cell-top', top[0], top[2], [[0, '#dfe5ff', P.topOp, 'p-ct'], [1, '#a3b0ff', P.topOp]]);
  if (P.bandBlur) defs.push(`<filter id="beam-bandblur" x="-20%" y="-30%" width="140%" height="160%"><feGaussianBlur stdDeviation="${P.bandBlur}"/></filter>`);
  defs.push(`<clipPath id="beam-cell-left-clip"><path d="${poly(...left)}"/></clipPath>`);
  // atoms
  const radial = (id, c1, c2) => defs.push(`<radialGradient id="beam-${id}" cx="0.36" cy="0.32" r="0.72"><stop offset="0" stop-color="#ffffff"/><stop offset="0.3" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></radialGradient>`);
  radial('atom-violet', '#a78bfa', '#6d28d9');
  radial('atom-teal', '#5eead4', '#0f766e');
  if (P.glow) defs.push(`<filter id="beam-soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="1.8"/></filter>`);

  // ---- art
  const out = [];
  // 1. target-property streams converging on the entry vertex (they start outside the frame, like Prism's)
  const cols5 = ['#3b82f6', '#10b981', '#8b5cf6', '#f97316', '#f5b70b'];
  out.push(`<g class="beam-streams" fill="none" stroke-width="${P.streamW}" stroke-linecap="round">` + cols5.map((c, i) => {
    const y0 = Li[1] + (i - 2) * P.streamSpread * 2.2, p0 = [P.streamFrom, y0];
    const p1 = [Li[0] - 7, y0], p2 = [Li[0] - 3.5, Li[1] + (i - 2) * P.streamSpread * 0.35];
    return `<path d="M${pt(p0)}C${pt(p1)} ${pt(p2)} ${pt(Li)}" stroke="${c}"/>`;
  }).join('') + `</g>`);

  // 2. the spectrum leaving the right vertex
  const beamPath = poly(R, [P.beamEnd, yT], [P.beamEnd, yB]);
  if (P.glow) out.push(`<path class="beam-glow" d="${beamPath}" fill="url(#beam-spectrum)" opacity="0.5" filter="url(#beam-soft)"/>`);
  const bandCols = ['#38bdf8', '#10b981', '#facc15', '#f97316', '#c084fc'], n = bandCols.length;
  out.push(`<g mask="url(#beam-fade-mask)"${P.bandBlur ? ' filter="url(#beam-bandblur)"' : ''}>` + bandCols.map((c, i) => {
    const a = yT + ((yB - yT) * (i + P.bandGap / 2)) / n, b = yT + ((yB - yT) * (i + 1 - P.bandGap / 2)) / n;
    return `<path d="${poly(R, [P.beamEnd, a], [P.beamEnd, b])}" fill="${c}"/>`;
  }).join('') + `</g>`);
  if (P.glow) out.push(`<ellipse class="beam-glow" cx="${f(P.cubeC[0])}" cy="${f(P.cubeC[1])}" rx="${f(P.cubeA * 1.3)}" ry="${f(P.cubeA * 1.3)}" fill="url(#beam-spectrum)" opacity="0.28" filter="url(#beam-soft)"/>`);

  // 3. the octahedron (Prism's facet plan)
  out.push(`<g class="beam-octa">`);
  out.push(`<path d="${poly(T, Lo, B, Li)}" fill="url(#beam-outer)"/>`);
  out.push(`<path d="${poly(T, Li, K)}" fill="url(#beam-facet-tl)"/>`);
  out.push(`<path d="${poly(T, K, R)}" fill="url(#beam-facet-tr)"/>`);
  out.push(`<path d="${poly(Li, K, F)}" fill="url(#beam-girdle-l)"/>`);
  out.push(`<path d="${poly(K, R, F)}" fill="url(#beam-girdle-r)"/>`);
  out.push(`<path d="${poly(Li, F, B)}" fill="url(#beam-facet-bl)"/>`);
  out.push(`<path d="${poly(F, R, B)}" fill="url(#beam-facet-br)"/>`);
  if (P.rimW) out.push(`<path d="M${pt(T)}L${pt(R)}L${pt(B)}" fill="none" stroke="url(#beam-rim)" stroke-width="${P.rimW}" stroke-linejoin="round" opacity="0.85"/>`);
  out.push(`<path class="beam-edge" d="M${pt(T)}L${pt(Li)}L${pt(B)}M${pt(Li)}L${pt(K)}L${pt(R)}M${pt(Li)}L${pt(F)}L${pt(R)}M${pt(T)}L${pt(K)}L${pt(F)}L${pt(B)}" fill="none" stroke="#fff" stroke-width="${P.edgeW}" stroke-linejoin="round" opacity="0.9"/>`);
  out.push(`</g>`);

  // 4. the unit cell the spectrum lands on
  out.push(`<g class="beam-cell">`);
  out.push(`<g stroke="#a5b4fc" stroke-width="${P.edgeW}" opacity="0.85">${edges.filter(([a, b]) => isHidden(a) || isHidden(b)).map(([a, b]) => `<path d="M${pt(v(...a))}L${pt(v(...b))}"/>`).join('')}</g>`);
  out.push(`<path d="${poly(...left)}" fill="url(#beam-cell-left)"/>`);
  if (P.stripes) {
    const far = Math.max(...left.map((q) => q[0])) + 2, k = (far - R[0]) / (P.beamEnd - R[0]);
    out.push(`<g class="beam-stripes" clip-path="url(#beam-cell-left-clip)" opacity="${P.stripes}">` + bandCols.map((c, i) => {
      const a = R[1] + (yT + ((yB - yT) * i) / n - R[1]) * k, b = R[1] + (yT + ((yB - yT) * (i + 1)) / n - R[1]) * k;
      return `<path d="${poly(R, [far, a], [far, b])}" fill="${c}"/>`;
    }).join('') + `</g>`);
  }
  if (P.bodyInside) out.push(`<circle class="beam-atoms" cx="${f(C0[0])}" cy="${f(C0[1])}" r="${P.bodyR}" fill="url(#beam-atom-teal)"/>`);
  out.push(`<path class="beam-front" d="${poly(...front)}" fill="url(#beam-cell-front)"${P.frontOp ? ` fill-opacity="${P.frontOp}"` : ''}/>`);
  out.push(`<path d="${poly(...top)}" fill="url(#beam-cell-top)"/>`);
  out.push(`<path d="${poly(...sil)}" fill="none" stroke="#6366f1" stroke-width="${P.edgeW}" stroke-linejoin="round" opacity="0.9"/>`);
  out.push(`<g class="beam-edge" fill="none" stroke="#fff" stroke-width="${P.edgeW}" stroke-linejoin="round" opacity="0.95">${edges.filter(([a, b]) => !isHidden(a) && !isHidden(b)).map(([a, b]) => `<path d="M${pt(v(...a))}L${pt(v(...b))}"/>`).join('')}</g>`);
  out.push(`<g class="beam-atoms">`);
  if (!P.bodyInside) out.push(`<circle cx="${f(C0[0])}" cy="${f(C0[1])}" r="${P.bodyR}" fill="url(#beam-atom-teal)"/>`);
  const litIds = ['atom-sky', 'atom-green', 'atom-yellow', 'atom-orange', 'atom-violet'];
  if (P.lit) { radial('atom-sky', '#7dd3fc', '#0284c7'); radial('atom-green', '#6ee7b7', '#047857'); radial('atom-yellow', '#fde68a', '#d97706'); radial('atom-orange', '#fdba74', '#ea580c'); }
  for (const c of corners.filter((c) => !isHidden(c)).sort((a, b) => proj(a)[2] - proj(b)[2])) {
    const p = proj(c);
    let id = 'atom-violet';
    if (P.lit && c[0] === -1) {   // corners on the landing face take the colour of the band that reaches them
      const k = (p[0] - R[0]) / (P.beamEnd - R[0]), y = R[1] + (p[1] - R[1]) / k;
      const band = Math.floor(((y - yT) / (yB - yT)) * 5);
      id = litIds[Math.min(4, Math.max(0, band))];
    }
    out.push(`<circle cx="${f(p[0])}" cy="${f(p[1])}" r="${f(c[2] === -1 ? P.atomR * 0.85 : P.atomR)}" fill="url(#beam-${id})"/>`);
  }
  out.push(`</g></g>`);

  // favicon-size simplifications (an SVG used as <img> evaluates media queries against its own rendered size;
  // inlined or in tools without media-query support, the full version below always applies)
  const style = P.small ? `<style>@media (max-width:${P.small}px){` +
    `.beam-streams,.beam-glow,.beam-atoms,.beam-stripes{display:none}.beam-edge{opacity:.55}.beam-front{fill-opacity:1}` +
    `.beam-p-tl{stop-color:#5fb2f2}.beam-p-tr{stop-color:#8dbdfa}.beam-p-tr2{stop-color:#5a9cf7}.beam-p-bl{stop-color:#fbc54a}` +
    `.beam-p-br{stop-color:#a48bfa}.beam-p-gl{stop-color:#5d9cf3}.beam-p-gr{stop-color:#9b7cf8}` +
    `.beam-p-cl{stop-color:#7dd3fc}.beam-p-cl2{stop-color:#818cf8}.beam-p-ct{stop-color:#b8c2ff}}</style>` : '';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="MEIDNet Matter">${style}<defs>${defs.join('')}</defs>${out.join('')}</svg>\n`;
  return { P, T, B, Lo, Li, K, F, R, svg: P.prefix === 'beam-' ? svg : svg.replace(/beam-/g, P.prefix) };
}

if (process.argv[2]) {
  const o = process.argv[3] ? JSON.parse(process.argv[3]) : {};
  writeFileSync(process.argv[2], build(o).svg);
  console.log('wrote', process.argv[2]);
}
