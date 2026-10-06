import { Link, useParams, useSearchParams } from 'react-router';
import { api } from '@/api/endpoints';
import { useResource } from '@/api/hooks';
import type { Candidate } from '@/api/types';
import { CellViewer } from '@/components/structure/CellViewer';
import { DomainBadge, ErrorNote, Spinner } from '@/components/ui';
import { candidateStructure } from '@/features/candidates/components';
import { fmt, signed } from '@/lib/format';

export default function Compare() {
  const { projectId = 'perov5-demo', runId = '' } = useParams();
  const [sp] = useSearchParams();
  const ids = (sp.get('ids') ?? '').split(',').filter(Boolean);
  const { data, error, loading } = useResource(ids.length >= 2 ? `compare:${runId}:${ids.join(',')}` : null, () => api.compare(runId, ids));
  if (ids.length < 2) return <div className="card"><p>Choose two to six candidates in the explorer to compare them.</p><Link to={`/p/${projectId}/runs/${runId}`} className="btn">Back to the candidates</Link></div>;
  if (loading) return <Spinner label="Comparing" />;
  if (error || !data) return <ErrorNote error={error} />;
  const cs = data.candidates;
  const best = (vals: Array<number | null>, lowerIsBetter = true) => { const v = vals.filter((x): x is number => x != null); if (!v.length) return null; return lowerIsBetter ? Math.min(...v) : Math.max(...v); };
  const Row = ({ label, cells, bestOf }: { label: string; cells: Array<React.ReactNode>; bestOf?: number | null }) => (
    <tr><th scope="row">{label}</th>{cells.map((cell, i) => <td key={i}>{cell}{bestOf != null && typeof cell === 'string' && Number(cell) === bestOf ? ' ◆' : ''}</td>)}</tr>
  );
  const rows: Array<{ label: string; get: (c: Candidate) => React.ReactNode }> = [
    { label: 'Composition by site', get: (c) => Object.entries(c.identity.elements).map(([g, e]) => `${g} ${e}`).join(' · ') },
    { label: 'Lattice a (Å)', get: (c) => fmt(c.structure.lattice_a) },
    ...Object.entries(data.properties).flatMap(([k, p]) => [
      { label: `${p.label}: target (${p.unit})`, get: (c: Candidate) => fmt(c.properties[k].target) },
      { label: `${p.label}: predicted`, get: (c: Candidate) => fmt(c.properties[k].predicted) },
      { label: `${p.label}: difference`, get: (c: Candidate) => signed(c.properties[k].difference) },
      { label: `${p.label}: status`, get: (c: Candidate) => <DomainBadge status={c.properties[k].domain.status} word={c.properties[k].domain.word} /> },
      { label: `${p.label}: encoder vs search`, get: (c: Candidate) => c.model_evidence.agreement[k].label },
    ]),
    { label: 'Rules passed', get: (c) => `${c.rules_passed}/${c.rules_total}` },
    ...['tolerance_factor', 'octahedral_factor', 'min_distance', 'bond_window'].map((id) => ({ label: id.replace('_', ' '), get: (c: Candidate) => { const r = c.constraints.find((x) => x.id === id); return r ? `${r.passed ? '✓' : '✗'} ${r.value != null ? fmt(r.value) : ''}` : '—'; } })),
    { label: 'Charge balance', get: (c) => { const r = c.constraints.find((x) => x.rule === 'charge_neutrality'); return r ? `${r.passed ? '✓' : '✗'} ${r.detail}` : '—'; } },
    { label: 'Nearest training material', get: (c) => c.model_evidence.nearest_training[0] ? `${c.model_evidence.nearest_training[0].formula} (cos ${c.model_evidence.nearest_training[0].cosine.toFixed(3)})` : '—' },
    { label: 'Latent norm', get: (c) => fmt(c.model_evidence.latent_norm) },
    { label: 'Training data around the prediction', get: (c) => `${c.model_evidence.local_density.n_within}` },
    { label: 'Novelty', get: (c) => c.novelty.dataset.label },
    { label: 'Stability', get: (c) => c.stability.status },
    { label: 'Score', get: (c) => c.model_evidence.score?.toExponential(3) ?? '—' },
    { label: 'Round', get: (c) => String(c.round) },
    { label: 'Flags', get: (c) => c.flags.join('; ') || '—' },
  ];
  return (
    <>
      <div className="page-head row" style={{ justifyContent: 'space-between' }}>
        <div><h1>Compare {cs.length} candidates</h1><p>Side by side; ◆ marks the closest to the target among them.</p></div>
        <div className="row">
          <a className="btn btn-sm" href={api.urls.csv(runId)} download>Export CSV (all)</a>
          <a className="btn btn-sm" href={api.urls.json(runId)} download>Export JSON (all)</a>
          <Link to={`/p/${projectId}/runs/${runId}?cmp=${ids.join(',')}`} className="btn btn-sm">← Candidates</Link>
        </div>
      </div>
      <div className="card" style={{ padding: 0, overflow: 'auto' }}>
        <table className="table compare-table">
          <thead><tr><th scope="col">Candidate</th>{cs.map((c) => <th key={c.candidate_id} scope="col"><div style={{ width: 90 }}><CellViewer structure={candidateStructure(c)} size={90} title={c.identity.formula} interactive={false} /></div><b>{c.identity.formula}</b></th>)}</tr></thead>
          <tbody>
            {rows.map((r) => {
              const cells = cs.map((c) => r.get(c));
              const numeric = r.label.includes('difference') ? cells.map((x) => (typeof x === 'string' && x !== '—' ? Math.abs(Number(x)) : null)) : null;
              return <Row key={r.label} label={r.label} cells={cells} bestOf={numeric ? best(numeric) : null} />;
            })}
            <tr><th scope="row">Pairwise latent cosine</th>{cs.map((c, i) => <td key={c.candidate_id} className="num small">{data.pairwise_cosine[i].map((v, j) => (j === i ? '' : `${cs[j].identity.formula} ${v.toFixed(3)}`)).filter(Boolean).join(' · ')}</td>)}</tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
