import type { Candidate, DomainStatus } from '@/api/types';

export type View = 'table' | 'cards' | 'map';
export type Sort = 'closest' | 'diverse' | 'stable' | 'novel' | 'best' | 'agreement' | 'round';
export interface ExplorerQuery {
  view: View; sort: Sort; dev: Record<string, number>; domain: DomainStatus[]; el: string[]; xel: string[];
  novelty: Array<'not_found' | 'found'>; rules: 'passed' | 'any'; c: string | null; cmp: string[]; cols: string[] | null;
}
export const DEFAULTS: ExplorerQuery = { view: 'table', sort: 'best', dev: {}, domain: [], el: [], xel: [], novelty: [], rules: 'any', c: null, cmp: [], cols: null };
/** The "Prioritise" control: what comes first when one target has many possible structures. */
export const SORTS: Array<{ value: Sort; label: string }> = [
  { value: 'best', label: 'Search score' }, { value: 'closest', label: 'Target accuracy' }, { value: 'diverse', label: 'Diversity (one per cluster first)' },
  { value: 'stable', label: 'Stability (lowest predicted formation enthalpy)' }, { value: 'novel', label: 'Novelty (not in the dataset first)' },
  { value: 'agreement', label: 'Encoder and search agree' }, { value: 'round', label: 'Order found' },
];

const list = (v: string | null) => (v ? v.split(',').filter(Boolean) : []);

export function parseQuery(sp: URLSearchParams): ExplorerQuery {
  const dev: Record<string, number> = {};
  sp.forEach((v, k) => { if (k.startsWith('dev.') && v !== '' && !Number.isNaN(Number(v))) dev[k.slice(4)] = Number(v); });
  const view = sp.get('view'), sort = sp.get('sort'), rules = sp.get('rules');
  return {
    view: view === 'cards' || view === 'map' ? view : 'table',
    sort: (SORTS.some((s) => s.value === sort) ? sort : 'best') as Sort,
    dev, domain: list(sp.get('domain')) as DomainStatus[], el: list(sp.get('el')), xel: list(sp.get('xel')),
    novelty: list(sp.get('novelty')) as Array<'not_found' | 'found'>, rules: rules === 'passed' ? 'passed' : 'any',
    c: sp.get('c'), cmp: list(sp.get('cmp')), cols: sp.has('cols') ? list(sp.get('cols')) : null,
  };
}

export function serializeQuery(q: ExplorerQuery): URLSearchParams {
  const sp = new URLSearchParams();
  if (q.view !== DEFAULTS.view) sp.set('view', q.view);
  if (q.sort !== DEFAULTS.sort) sp.set('sort', q.sort);
  for (const [k, v] of Object.entries(q.dev)) sp.set(`dev.${k}`, String(v));
  if (q.domain.length) sp.set('domain', q.domain.join(','));
  if (q.el.length) sp.set('el', q.el.join(','));
  if (q.xel.length) sp.set('xel', q.xel.join(','));
  if (q.novelty.length) sp.set('novelty', q.novelty.join(','));
  if (q.rules !== 'any') sp.set('rules', q.rules);
  if (q.c) sp.set('c', q.c);
  if (q.cmp.length) sp.set('cmp', q.cmp.join(','));
  if (q.cols) sp.set('cols', q.cols.join(','));
  return sp;
}

export function filterCandidates(cands: Candidate[], q: ExplorerQuery): Candidate[] {
  return cands.filter((c) => {
    if (!c.properties) return true;
    for (const [p, max] of Object.entries(q.dev)) {
      const d = c.properties[p]?.difference;
      if (d != null && Math.abs(d) > max) return false;
    }
    if (q.domain.length && !q.domain.includes(c.domain.status)) return false;
    const els = Object.values(c.identity.elements);
    if (q.el.length && !q.el.every((e) => els.includes(e))) return false;
    if (q.xel.length && q.xel.some((e) => els.includes(e))) return false;
    if (q.novelty.length) {
      const nov = c.novelty.dataset.found ? 'found' : 'not_found';
      if (!q.novelty.includes(nov)) return false;
    }
    if (q.rules === 'passed' && c.rules_passed < c.rules_total) return false;
    return true;
  });
}

export function sortCandidates(cands: Candidate[], sort: Sort): Candidate[] {
  const closeness = (c: Candidate) => Object.values(c.properties).reduce((s, p) => s + (p.difference != null ? Math.abs(p.difference) / Math.max(1e-9, (p.training_range[1] - p.training_range[0]) * 0.05) : 0), 0);
  const agreementRank = { agree: 0, 'partly agree': 1, disagree: 2, 'not judged': 3 } as Record<string, number>;
  const by: Record<Sort, (a: Candidate, b: Candidate) => number> = {
    best: (a, b) => (a.model_evidence.score ?? 0) - (b.model_evidence.score ?? 0),
    closest: (a, b) => closeness(a) - closeness(b),
    diverse: (a, b) => closeness(a) - closeness(b),
    novel: (a, b) => Number(a.novelty.dataset.found) - Number(b.novelty.dataset.found) || (b.model_evidence.latent_distance ?? 0) - (a.model_evidence.latent_distance ?? 0),
    stable: (a, b) => (formation(a) ?? Infinity) - (formation(b) ?? Infinity),
    agreement: (a, b) => Math.max(...Object.values(a.model_evidence.agreement).map((x) => agreementRank[x.label] ?? 3)) - Math.max(...Object.values(b.model_evidence.agreement).map((x) => agreementRank[x.label] ?? 3)),
    round: (a, b) => a.index - b.index,
  };
  const sorted = [...cands].filter((c) => !!c.properties).sort(by[sort]);
  if (sort !== 'diverse') return sorted;
  // one candidate per cluster first (the closest of each), then the second of each cluster, and so on
  const lists = new Map<number | string, Candidate[]>();
  for (const c of sorted) {
    const key = c.cluster?.id ?? c.candidate_id;
    if (!lists.has(key)) lists.set(key, []);
    lists.get(key)!.push(c);
  }
  const out: Candidate[] = [];
  for (let i = 0; out.length < sorted.length; i++) for (const l of lists.values()) if (l[i]) out.push(l[i]);
  return out;
}

function formation(c: Candidate): number | null {
  const p = Object.entries(c.properties).find(([k, v]) => /heat|form|enthalp/i.test(k) || /formation|enthalp/i.test(v.label));
  return p ? p[1].predicted : null;
}

export function chips(q: ExplorerQuery, labels: Record<string, string>): Array<{ key: string; text: string; remove: (q: ExplorerQuery) => ExplorerQuery }> {
  const out: Array<{ key: string; text: string; remove: (q: ExplorerQuery) => ExplorerQuery }> = [];
  for (const [p, max] of Object.entries(q.dev)) out.push({ key: `dev.${p}`, text: `|Δ ${labels[p] ?? p}| ≤ ${max}`, remove: (x) => ({ ...x, dev: Object.fromEntries(Object.entries(x.dev).filter(([k]) => k !== p)) }) });
  for (const d of q.domain) out.push({ key: `domain.${d}`, text: d.replace('_', ' '), remove: (x) => ({ ...x, domain: x.domain.filter((y) => y !== d) }) });
  for (const e of q.el) out.push({ key: `el.${e}`, text: `contains ${e}`, remove: (x) => ({ ...x, el: x.el.filter((y) => y !== e) }) });
  for (const e of q.xel) out.push({ key: `xel.${e}`, text: `no ${e}`, remove: (x) => ({ ...x, xel: x.xel.filter((y) => y !== e) }) });
  for (const n of q.novelty) out.push({ key: `nov.${n}`, text: n === 'found' ? 'in the dataset' : 'not in the dataset', remove: (x) => ({ ...x, novelty: x.novelty.filter((y) => y !== n) }) });
  if (q.rules === 'passed') out.push({ key: 'rules', text: 'all rules passed', remove: (x) => ({ ...x, rules: 'any' }) });
  return out;
}
