// Cell geometry for the SVG viewer: a port of the MEIDNet Studio's built-in viewer (no dependency).
export type Vec3 = [number, number, number];
export type Matrix = [Vec3, Vec3, Vec3];
export interface CellStructure { names: string[]; frac: Vec3[]; M: Matrix; groups: Array<string | null> }
export interface Atom { n: string; g: string | null; i: number; p: Vec3 }

export function fromParameters(a: number, b: number, c: number, al: number, be: number, ga: number): Matrix {
  const d = Math.PI / 180, ca = Math.cos(al * d), cb = Math.cos(be * d), cg = Math.cos(ga * d), sg = Math.sin(ga * d);
  const cx = c * cb, cy = (c * (ca - cb * cg)) / sg, cz = Math.sqrt(Math.max(0, c * c - cx * cx - cy * cy));
  return [[a, 0, 0], [b * cg, b * sg, 0], [cx, cy, cz]];
}

export function latticeMatrix(spec: { lattice?: string; a?: number; b?: number; c?: number; alpha?: number; beta?: number; gamma?: number } | null | undefined, a: number): Matrix {
  const kind = spec?.lattice ?? 'cubic';
  if (kind === 'cubic') return [[a, 0, 0], [0, a, 0], [0, 0, a]];
  if (kind === 'fcc_primitive') { const e = a / Math.SQRT2; return fromParameters(e, e, e, 60, 60, 60); }
  if (kind === 'bcc_primitive') { const e = (a * Math.sqrt(3)) / 2; return fromParameters(e, e, e, 109.4712206, 109.4712206, 109.4712206); }
  const sc = a / (Number(spec?.a) || a);
  return fromParameters(Number(spec?.a) * sc, Number(spec?.b) * sc, Number(spec?.c) * sc, Number(spec?.alpha), Number(spec?.beta), Number(spec?.gamma));
}

export const fracToCart = (f: Vec3, M: Matrix): Vec3 => [
  f[0] * M[0][0] + f[1] * M[1][0] + f[2] * M[2][0],
  f[0] * M[0][1] + f[1] * M[1][1] + f[2] * M[2][1],
  f[0] * M[0][2] + f[1] * M[1][2] + f[2] * M[2][2],
];

/** Atoms of the cell with their periodic images on the cell faces, repeated over an n×n×n supercell. */
export function expandCell(st: CellStructure, n = 1): Atom[] {
  const eps = 1e-3, atoms: Atom[] = [];
  st.names.forEach((name, i) => {
    const f = st.frac[i];
    const opts = f.map((x) => { const o = [0]; if (Math.abs(x) < eps) o.push(1); if (Math.abs(x - 1) < eps) o.push(-1); return o; });
    const cart = fracToCart(f, st.M);
    for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) for (let c = 0; c < n; c++)
      for (const sa of opts[0]) for (const sb of opts[1]) for (const sc of opts[2]) {
        const sh = fracToCart([a + sa, b + sb, c + sc], st.M);
        const p: Vec3 = [cart[0] + sh[0], cart[1] + sh[1], cart[2] + sh[2]];
        if (p.some((x, k) => { const lim = fracToCart([n, n, n], st.M)[k]; return x < -eps * 10 - 1e-6 || x > lim + 1e-3 + 1e-6; })) continue;
        atoms.push({ n: name, g: st.groups[i], i, p });
      }
  });
  return atoms;
}

/** Bonds between unlike sites, drawn up to 1.3× the shortest unlike distance. */
export function bondsFor(atoms: Atom[]): Array<[number, number]> {
  const D: Array<[number, number, number]> = [];
  let dmin = Infinity;
  for (let i = 0; i < atoms.length; i++) for (let j = i + 1; j < atoms.length; j++) {
    const a = atoms[i].p, b = atoms[j].p;
    const d = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    if (atoms[i].n !== atoms[j].n || atoms[i].g !== atoms[j].g) { D.push([i, j, d]); if (d < dmin) dmin = d; }
  }
  return D.filter(([, , d]) => d <= 1.3 * dmin + 1e-6).map(([i, j]) => [i, j]);
}

export function project3d(p: Vec3, yaw: number, pitch: number): Vec3 {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const x1 = p[0] * cy + p[2] * sy, z1 = -p[0] * sy + p[2] * cy;
  return [x1, p[1] * cp - z1 * sp, p[1] * sp + z1 * cp];
}

/** A candidate's cell from its family's prototype sites, element per site, and lattice constant. */
export function prototypeStructure(sites: Array<{ group: string; frac: [number, number, number] }>, elements: Record<string, string>, lattice: { lattice?: string } & Record<string, unknown>, a: number): CellStructure {
  return { names: sites.map((s) => elements[s.group]), frac: sites.map((s) => s.frac), M: latticeMatrix(lattice as never, a), groups: sites.map((s) => s.group) };
}

/** A cell from explicit sites and a lattice matrix (what the API returns for a candidate). */
export function explicitStructure(sites: Array<{ element: string; frac: [number, number, number] }>, lattice: number[][], groups?: Array<string | null>): CellStructure {
  return { names: sites.map((s) => s.element), frac: sites.map((s) => s.frac), M: lattice as Matrix, groups: groups ?? sites.map(() => null) };
}
