import { Link } from 'react-router';
import { api } from '@/api/endpoints';
import type { Candidate, DatasetSummary, Funnel, Project } from '@/api/types';
import { CellViewer } from '@/components/structure/CellViewer';
import { DomainBadge, Site } from '@/components/ui';
import { fmt, int, shortLabel, signed } from '@/lib/format';
import { explicitStructure, type CellStructure } from '@/lib/lattice';
import type { ExplorerQuery } from './explorerQuery';

export function candidateStructure(c: Candidate): CellStructure {
  const groupOf = Object.fromEntries(Object.entries(c.identity.elements).map(([g, el]) => [el, g]));
  return explicitStructure(c.structure.sites, c.structure.lattice, c.structure.sites.map((s) => groupOf[s.element] ?? null));
}

export function CandidateCard({ c, selected, compared, onOpen, onCompare, projectId }: { c: Candidate; selected: boolean; compared: boolean; onOpen: () => void; onCompare: () => void; projectId: string }) {
  const props = Object.entries(c.properties);
  return (
    <article className={`card card-tight ccard`} aria-selected={selected} data-testid="candidate-card" style={selected ? { borderColor: 'var(--p1)' } : undefined}>
      <div className="thumb"><CellViewer structure={candidateStructure(c)} size={96} title={c.identity.formula} interactive={false} /></div>
      <div>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}><button type="button" className="btn btn-ghost" style={{ padding: 0, fontSize: 17 }} onClick={onOpen}>{c.identity.formula}</button></h3>
          <DomainBadge status={c.domain.status} word={c.domain.word} />
        </div>
        <div className="row" style={{ gap: 6 }}>{Object.entries(c.identity.elements).map(([g, e]) => <Site key={g} group={g} element={e} />)} <span className="small faint num">a = {fmt(c.structure.lattice_a)} Å</span></div>
        <div className="lines" style={{ marginTop: 6 }}>
          {props.map(([k, p]) => <div key={k}>{shortLabel(p.label)} <b className="num">{fmt(p.predicted, p.unit)}</b>{p.target != null && <span className="muted"> · target {fmt(p.target)} ({signed(p.difference)})</span>} <span className="faint">{p.evidence_label}</span></div>)}
          <div>Rule passed {c.rules_passed}/{c.rules_total} · {c.novelty.dataset.found ? 'Found in the dataset' : 'Not found in the dataset'} · {c.stability.status}</div>
          {c.flags.map((f) => <div key={f} className="small" style={{ color: 'var(--warn)' }}>{f}</div>)}
        </div>
        <div className="foot">
          <button type="button" className="btn btn-sm" onClick={onOpen}>Details</button>
          <button type="button" className="btn btn-sm" aria-pressed={compared} onClick={onCompare}>{compared ? '− Compare' : '+ Compare'}</button>
          <a className="btn btn-sm" href={api.urls.cif(c.run_id, c.candidate_id)} download>CIF ↓</a>
          <Link className="btn btn-ghost btn-sm" to={`/p/${projectId}/runs/${c.run_id}/c/${c.candidate_id}`}>Open page</Link>
        </div>
      </div>
    </article>
  );
}

export const COLUMNS: Array<{ id: string; label: string; always?: boolean }> = [
  { id: 'formula', label: 'Formula', always: true }, { id: 'predicted', label: 'Predicted', always: true }, { id: 'domain', label: 'Domain' }, { id: 'rules', label: 'Rules' },
  { id: 'novelty', label: 'Novelty' }, { id: 'agreement', label: 'Encoder vs search' }, { id: 'nearest', label: 'Nearest training material' }, { id: 'a', label: 'a (Å)' },
  { id: 'sites', label: 'Sites' }, { id: 'score', label: 'Score' }, { id: 'latent', label: 'Latent norm' }, { id: 'round', label: 'Round' }, { id: 'stability', label: 'Stability' },
];
export const DEFAULT_COLS = ['formula', 'predicted', 'domain', 'rules', 'novelty', 'agreement', 'score'];

export function CandidateTable({ cands, q, setQ, onOpen }: { cands: Candidate[]; q: ExplorerQuery; setQ: (f: (q: ExplorerQuery) => ExplorerQuery) => void; onOpen: (id: string) => void }) {
  const cols = q.cols ?? DEFAULT_COLS;
  const show = (id: string) => cols.includes(id) || COLUMNS.find((c) => c.id === id)?.always;
  const props = cands[0] ? Object.entries(cands[0].properties) : [];
  const toggleCmp = (id: string) => setQ((x) => ({ ...x, cmp: x.cmp.includes(id) ? x.cmp.filter((y) => y !== id) : x.cmp.length < 6 ? [...x.cmp, id] : x.cmp }));
  return (
    <div className="card" style={{ padding: 0, overflow: 'auto' }}>
      <table className="table" data-testid="candidates-table">
        <caption className="sr-only">Candidates matching the design request</caption>
        <thead><tr>
          <th><span className="sr-only">Compare</span></th>
          {show('formula') && <th scope="col">Formula</th>}
          {show('predicted') && props.map(([k, p]) => <th key={k} scope="col" className="num">{shortLabel(p.label)} ({p.unit})</th>)}
          {show('domain') && <th scope="col">Domain</th>}
          {show('rules') && <th scope="col">Rules</th>}
          {show('novelty') && <th scope="col">Novelty</th>}
          {show('agreement') && <th scope="col">Encoder vs search</th>}
          {show('nearest') && <th scope="col">Nearest training</th>}
          {show('a') && <th scope="col" className="num">a (Å)</th>}
          {show('sites') && <th scope="col">Sites</th>}
          {show('score') && <th scope="col" className="num">Score</th>}
          {show('latent') && <th scope="col" className="num">Latent norm</th>}
          {show('round') && <th scope="col" className="num">Round</th>}
          {show('stability') && <th scope="col">Stability</th>}
          <th scope="col"><span className="sr-only">Actions</span></th>
        </tr></thead>
        <tbody>
          {cands.map((c) => (
            <tr key={c.candidate_id} aria-selected={q.c === c.candidate_id} onClick={() => onOpen(c.candidate_id)} style={{ cursor: 'pointer' }} data-testid="candidate-row">
              <td onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label={`Select ${c.identity.formula} for comparison`} checked={q.cmp.includes(c.candidate_id)} onChange={() => toggleCmp(c.candidate_id)} /></td>
              {show('formula') && <td><b>{c.identity.formula}</b>{c.flags.length > 0 && <span className="badge badge-warn" style={{ marginLeft: 6 }} title={c.flags.join(' | ')}>flag</span>}</td>}
              {show('predicted') && Object.entries(c.properties).map(([k, p]) => <td key={k} className="num">{fmt(p.predicted)}{p.difference != null && <span className="small muted"> {signed(p.difference)}</span>}</td>)}
              {show('domain') && <td><DomainBadge status={c.domain.status} word={c.domain.word} /></td>}
              {show('rules') && <td>{c.rules_passed}/{c.rules_total} passed</td>}
              {show('novelty') && <td className="small">{c.novelty.dataset.found ? `Found (${c.novelty.dataset.match?.material_id})` : 'Not found'}</td>}
              {show('agreement') && <td className="small">{Object.entries(c.model_evidence.agreement).map(([k, a]) => <span key={k}>{shortLabel(c.properties[k].label)} {a.label}; </span>)}</td>}
              {show('nearest') && <td className="small">{c.model_evidence.nearest_training[0] ? `${c.model_evidence.nearest_training[0].formula} (${c.model_evidence.nearest_training[0].cosine.toFixed(2)})` : '—'}</td>}
              {show('a') && <td className="num">{fmt(c.structure.lattice_a)}</td>}
              {show('sites') && <td className="small">{Object.entries(c.identity.elements).map(([g, e]) => `${g}=${e}`).join(' ')}</td>}
              {show('score') && <td className="num">{c.model_evidence.score?.toExponential(2)}</td>}
              {show('latent') && <td className="num">{fmt(c.model_evidence.latent_norm)}</td>}
              {show('round') && <td className="num">{c.round}</td>}
              {show('stability') && <td className="small">{c.stability.status}</td>}
              <td onClick={(e) => e.stopPropagation()}><a className="btn btn-sm" href={api.urls.cif(c.run_id, c.candidate_id)} download>CIF ↓</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CandidateMap({ cands, project, dataset, windows, selected, onOpen }: { cands: Candidate[]; project: Project; dataset: DatasetSummary | null; windows: Record<string, [number | null, number | null]>; selected: string | null; onOpen: (id: string) => void }) {
  const cols = Object.keys(project.dataset.properties);
  if (cols.length < 2) return <p className="muted">The map needs two properties.</p>;
  const [px, py] = cols;
  const sx = project.dataset.properties[px], sy = project.dataset.properties[py];
  const W = 640, H = 420, m = { l: 50, r: 14, t: 14, b: 36 };
  const X = (v: number) => m.l + ((v - sx.min) / (sx.max - sx.min || 1)) * (W - m.l - m.r);
  const Y = (v: number) => m.t + (H - m.t - m.b) - ((v - sy.min) / (sy.max - sy.min || 1)) * (H - m.t - m.b);
  const grid = dataset?.ambiguity_grid;
  const maxBox = grid ? Math.max(1, ...grid.n_box.flat()) : 1;
  const wx = windows[px], wy = windows[py];
  return (
    <div className="card">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Candidates on the ${sx.label} versus ${sy.label} map over the training density`}>
        {grid && grid.columns[0] === px && grid.axes[px].map((ax, i) => grid.axes[py].map((ay, j) => {
          const n = grid.n_box[i][j]; if (!n) return null;
          const cw = (W - m.l - m.r) / (grid.axes[px].length - 1), ch = (H - m.t - m.b) / (grid.axes[py].length - 1);
          const level = Math.min(5, 1 + Math.floor((4 * Math.log1p(n)) / Math.log1p(maxBox)));
          return <rect key={`${i}-${j}`} x={X(ax) - cw / 2} y={Y(ay) - ch / 2} width={cw} height={ch} fill={`var(--dens-${level})`}><title>{n} training materials near {fmt(ax)} / {fmt(ay)}</title></rect>;
        }))}
        {(wx || wy) && <rect x={X(wx?.[0] ?? sx.min)} y={Y(wy?.[1] ?? sy.max)} width={X(wx?.[1] ?? sx.max) - X(wx?.[0] ?? sx.min)} height={Y(wy?.[0] ?? sy.min) - Y(wy?.[1] ?? sy.max)} fill="var(--c-targets)" opacity={0.12} stroke="var(--c-targets)" strokeDasharray="4 3" />}
        {cands.map((c) => {
          const x = X(c.properties[px].predicted), y = Y(c.properties[py].predicted);
          const sel = c.candidate_id === selected;
          return <g key={c.candidate_id} style={{ cursor: 'pointer' }} onClick={() => onOpen(c.candidate_id)}>
            <circle cx={x} cy={y} r={sel ? 7 : 5} fill="var(--c-candidates)" stroke="var(--card)" strokeWidth={2}><title>{c.identity.formula}: {fmt(c.properties[px].predicted, sx.unit)}, {fmt(c.properties[py].predicted, sy.unit)}</title></circle>
            {sel && <text x={x + 9} y={y + 4} fontSize={11} fontWeight={700} fill="var(--ink)">{c.identity.formula}</text>}
          </g>;
        })}
        <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} stroke="var(--line)" /><line x1={m.l} x2={m.l} y1={m.t} y2={H - m.b} stroke="var(--line)" />
        <text x={(W + m.l) / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">{sx.label} ({sx.unit}), predicted</text>
        <text x={12} y={H / 2} textAnchor="middle" fontSize={11} fill="var(--muted)" transform={`rotate(-90 12 ${H / 2})`}>{sy.label} ({sy.unit}), predicted</text>
        {[sx.min, sx.max].map((v) => <text key={`x${v}`} x={X(v)} y={H - m.b + 14} fontSize={10} textAnchor="middle" fill="var(--faint)">{fmt(v)}</text>)}
        {[sy.min, sy.max].map((v) => <text key={`y${v}`} x={m.l - 4} y={Y(v) + 3} fontSize={10} textAnchor="end" fill="var(--faint)">{fmt(v)}</text>)}
      </svg>
      <p className="small muted">Grey cells: training materials per window of the training split (darker = more). Pink: the target window. Purple: candidates by their predicted values; click one to open it.</p>
    </div>
  );
}

export function SearchFunnel({ funnel }: { funnel: Funnel[] }) {
  return (
    <section className="card" data-testid="funnel">
      <h2>Search funnel</h2>
      {funnel.map((f) => (
        <div key={f.target_index} style={{ marginBottom: 16 }}>
          <div className="small muted" style={{ marginBottom: 6 }}>Target {f.target_index}: {Object.entries(f.target).map(([k, v]) => `${k} ${fmt(v)}`).join(', ')} · {f.rounds_used} round{f.rounds_used === 1 ? '' : 's'}</div>
          <div className="row small" style={{ gap: 14, marginBottom: 8 }}>
            <span>Proposed <b className="num">{int(f.latents.proposed)}</b></span><span>→ decoded <b className="num">{int(f.latents.decoded)}</b></span>
            <span>→ passing rules and windows <b className="num">{int(f.latents.passing)}</b></span><span>→ retained unique <b className="num">{int(f.latents.retained)}</b></span>
            {f.latents.skipped_duplicate > 0 && <span className="faint">duplicates {f.latents.skipped_duplicate}</span>}{f.latents.skipped_similar > 0 && <span className="faint">too similar {f.latents.skipped_similar}</span>}
          </div>
          <div className="stack" style={{ gap: 4 }}>
            <div className="funnel-stage"><span>Element choices tried</span><div className="bar" style={{ width: '100%' }} /><span className="num">{int(f.attempts.tried)}</span></div>
            {f.attempts.stages.filter((s) => s.lost > 0).map((s) => (
              <div key={s.id} className="funnel-stage" title={`${s.lost} rejected by: ${s.title}`}>
                <span className="small">after {s.title}{s.is_window ? ' (target window)' : ''}</span>
                <div className="bar" style={{ width: `${Math.max(1, (100 * s.left) / Math.max(1, f.attempts.tried))}%`, background: s.is_window ? 'var(--c-targets)' : 'var(--seq-4)' }} />
                <span className="num">{int(s.left)} <span className="faint">−{int(s.lost)}</span></span>
              </div>
            ))}
          </div>
          {Object.keys(f.rejections.first_failure).length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary className="small" style={{ cursor: 'pointer' }}>Representative rejection reasons</summary>
              <ul className="small muted" style={{ margin: '6px 0 0 18px' }}>
                {f.attempts.stages.filter((s) => s.lost > 0).map((s) => <li key={s.id}>{s.title} — {int(s.lost)}</li>)}
                {f.rejections.examples.slice(0, 8).map((e, i) => <li key={i}>{e.formula}: {e.title}</li>)}
              </ul>
            </details>
          )}
        </div>
      ))}
      <p className="small faint">Chemistry rules are evaluated before the target windows, so "after … (target window)" counts attempts that passed every chemistry rule.</p>
    </section>
  );
}

export function ExportMenu({ runId, candidateCount }: { runId: string; candidateCount: number }) {
  return (
    <details className="card card-tight" style={{ padding: '6px 12px' }}>
      <summary className="btn btn-sm" style={{ display: 'inline-flex', cursor: 'pointer', listStyle: 'none' }}>Export ▾</summary>
      <div className="stack small" style={{ marginTop: 8 }}>
        <a href={api.urls.csv(runId)} download>candidates.csv ({candidateCount})</a>
        <a href={api.urls.json(runId)} download>candidates.json</a>
        <a href={api.urls.bundle(runId)} download>Run bundle (.zip)</a>
        <a href={api.urls.manifest(runId)} target="_blank" rel="noopener">Manifest (.json)</a>
      </div>
    </details>
  );
}
