import { describe, expect, it } from 'vitest';
import type { Candidate } from '@/api/types';
import { chips, DEFAULTS, filterCandidates, parseQuery, serializeQuery, sortCandidates } from './explorerQuery';

function cand(over: Partial<Candidate> & { formula: string; gap: number; dhf: number; found?: boolean; score?: number; elements?: Record<string, string> }): Candidate {
  const { formula, gap, dhf, found = false, score = 0.01, elements = { A: 'La', B: 'Mn', X: 'O' }, ...rest } = over;
  const prop = (label: string, predicted: number, target: number, unit: string) => ({
    label, unit, objective: 'value' as const, target, predicted, difference: predicted - target, uncertainty: null, uncertainty_note: '', training_range: [0, 8] as [number, number],
    domain: { status: 'in_distribution' as const, word: 'Interpolating', reason: '' }, in_window: true, window: null, evidence_label: 'Predicted',
  });
  return {
    candidate_id: formula, run_id: 'r', index: 1, target_index: 1, round: 1,
    identity: { formula, reduced_formula: formula, site_key: null, elements, family: 'perovskite_abx3', variant: 'oxide', backend: 'meidnet', model_id: 'm' },
    structure: { file: '', lattice_a: 4, n_sites: 5, chemiscope: { size: 5, names: [], x: [], y: [], z: [], cell: [] }, sites: [], lattice: [] },
    properties: { dir_gap: prop('Direct band gap', gap, 2.0, 'eV'), heat_all: prop('Formation enthalpy', dhf, 1.0, 'eV/atom') },
    domain: { status: 'in_distribution', word: 'Interpolating' }, constraints: [], rules_passed: 8, rules_total: 8,
    model_evidence: { encoder_prediction: {}, agreement: { dir_gap: { decoder: gap, encoder: gap, difference: 0, in_std: 0, word: 'good', label: 'agree' } }, latent_norm: 1, latent_hit_clip: false, score, nearest_training: [], latent_distance: 0.1, local_density: { n_within: 1, fraction: 0, windows: {} }, latent: [] },
    novelty: { method: '', dataset: { checked_against: '', found, match: null, label: found ? 'Found' : 'Not found' }, training_split: { checked_against: '', found, match: null, label: '' } },
    stability: { status: 'Not screened', stages: [], records: [] }, flags: [], mode: 'standard', why: '', engine: {}, ...rest,
  } as Candidate;
}

describe('explorer query', () => {
  it('round-trips through the URL and drops defaults', () => {
    const q = { ...DEFAULTS, view: 'cards' as const, sort: 'novel' as const, dev: { dir_gap: 0.2 }, domain: ['in_distribution' as const], xel: ['Pb'], c: 'r-001', cmp: ['r-001', 'r-002'] };
    const sp = serializeQuery(q);
    expect(sp.toString()).toBe('view=cards&sort=novel&dev.dir_gap=0.2&domain=in_distribution&xel=Pb&c=r-001&cmp=r-001%2Cr-002');
    expect(parseQuery(sp)).toEqual(q);
    expect(serializeQuery(DEFAULTS).toString()).toBe('');
    expect(parseQuery(new URLSearchParams('view=nonsense&sort=what&rules=passed'))).toMatchObject({ view: 'table', sort: 'best', rules: 'passed' });
  });

  it('filters by deviation, domain, elements and novelty', () => {
    const cs = [cand({ formula: 'A', gap: 2.1, dhf: 0.9 }), cand({ formula: 'B', gap: 2.8, dhf: 0.5, found: true, elements: { A: 'Cs', B: 'Pb', X: 'O' } })];
    expect(filterCandidates(cs, { ...DEFAULTS, dev: { dir_gap: 0.3 } }).map((c) => c.identity.formula)).toEqual(['A']);
    expect(filterCandidates(cs, { ...DEFAULTS, xel: ['Pb'] }).map((c) => c.identity.formula)).toEqual(['A']);
    expect(filterCandidates(cs, { ...DEFAULTS, el: ['Cs'] }).map((c) => c.identity.formula)).toEqual(['B']);
    expect(filterCandidates(cs, { ...DEFAULTS, novelty: ['found'] }).map((c) => c.identity.formula)).toEqual(['B']);
    expect(filterCandidates(cs, { ...DEFAULTS, domain: ['extrapolating'] })).toEqual([]);
  });

  it('sorts by score, closeness, novelty and formation enthalpy', () => {
    const cs = [cand({ formula: 'A', gap: 2.5, dhf: 0.9, score: 0.3 }), cand({ formula: 'B', gap: 2.1, dhf: 0.2, score: 0.1, found: true }), cand({ formula: 'C', gap: 1.9, dhf: 0.7, score: 0.2 })];
    expect(sortCandidates(cs, 'best').map((c) => c.identity.formula)).toEqual(['B', 'C', 'A']);
    expect(sortCandidates(cs, 'closest').map((c) => c.identity.formula)).toEqual(['C', 'A', 'B']);   // both properties count, scaled by 5 % of the range
    expect(sortCandidates(cs, 'stable').map((c) => c.identity.formula)).toEqual(['B', 'C', 'A']);
    expect(sortCandidates(cs, 'novel').map((c) => c.identity.formula)[2]).toBe('B');
  });

  it('describes the active filters as chips', () => {
    const list = chips({ ...DEFAULTS, dev: { dir_gap: 0.2 }, xel: ['Pb'], rules: 'passed' }, { dir_gap: 'Eg' });
    expect(list.map((c) => c.text)).toEqual(['|Δ Eg| ≤ 0.2', 'no Pb', 'all rules passed']);
    expect(list[1].remove({ ...DEFAULTS, xel: ['Pb', 'Cd'] }).xel).toEqual(['Cd']);
  });
});
