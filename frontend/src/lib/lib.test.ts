import { describe, expect, it } from 'vitest';
import { fmt, pct, seconds, shortLabel, signed } from './format';
import { bondsFor, expandCell, latticeMatrix, prototypeStructure } from './lattice';

describe('format', () => {
  it('prints three significant figures with units', () => {
    expect(fmt(2.0, 'eV')).toBe('2 eV');
    expect(fmt(0.404123, 'eV/atom')).toBe('0.404 eV/atom');
    expect(fmt(18928)).toBe('18,928');
    expect(fmt(null)).toBe('—');
    expect(signed(0.0985)).toBe('+0.0985');
    expect(pct(0.336)).toBe('34 %');
    expect(seconds(53.4)).toBe('53 s');
    expect(seconds(300)).toBe('5 min');
    expect(shortLabel('Direct band gap')).toBe('Eg');
    expect(shortLabel('Formation enthalpy')).toBe('ΔHf');
  });
});

describe('lattice', () => {
  const sites: Array<{ group: string; frac: [number, number, number] }> = [
    { group: 'A', frac: [0, 0, 0] }, { group: 'B', frac: [0.5, 0.5, 0.5] }, { group: 'X', frac: [0.5, 0.5, 0] }, { group: 'X', frac: [0.5, 0, 0.5] }, { group: 'X', frac: [0, 0.5, 0.5] },
  ];
  it('builds a cubic cell and its periodic images', () => {
    const st = prototypeStructure(sites, { A: 'Cs', B: 'Pb', X: 'I' }, { lattice: 'cubic' }, 6.3);
    expect(latticeMatrix({ lattice: 'cubic' }, 6.3)).toEqual([[6.3, 0, 0], [0, 6.3, 0], [0, 0, 6.3]]);
    const atoms = expandCell(st);
    expect(atoms.filter((a) => a.n === 'Cs')).toHaveLength(8);        // the corners
    expect(atoms.filter((a) => a.n === 'Pb')).toHaveLength(1);
    expect(atoms.filter((a) => a.n === 'I')).toHaveLength(6);         // each face centre and its image on the opposite face
    const bonds = bondsFor(atoms);
    expect(bonds.length).toBeGreaterThan(0);
    expect(expandCell(st, 2).filter((a) => a.n === 'Pb')).toHaveLength(8);
  });
});
