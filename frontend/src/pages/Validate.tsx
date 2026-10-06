import { Link, useParams } from 'react-router';
import { api } from '@/api/endpoints';
import { useResource, useRunPolling } from '@/api/hooks';
import { ExternalLink, PRISM_SCORE } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { seconds } from '@/lib/format';

/** The six-stage validation ladder. Stages 0 and 1 are recorded by this version; the others are the user's own steps,
 * and their records have their place in the candidate record (`stability.records`). */
const LADDER: Array<[string, string, 'here' | 'yours']> = [
  ['Generated', 'Decoded from the latent search: predicted values with their domain status, nearest training materials, the encoder\'s own prediction.', 'here'],
  ['Chemistry checked', 'Every chemistry rule of the family passed (oxidation states, radii, tolerance factor, electronegativity, …).', 'here'],
  ['MLIP screened', 'Relaxed with a machine-learned interatomic potential and a formation-energy check (meidnet screen, MACE).', 'yours'],
  ['DFT relaxed', 'Density-functional relaxation of the structure.', 'yours'],
  ['DFT property confirmed', 'The targeted properties computed on the relaxed structure; the energy above the convex hull.', 'yours'],
  ['Experimentally tested', 'Synthesis and measurement.', 'yours'],
];

export default function Validate() {
  const { projectId = 'perov5-demo', runId = '' } = useParams();
  const { status } = useRunPolling(runId);
  const finished = status && status.status !== 'queued' && status.status !== 'running';
  const { data: manifest, error } = useResource(finished ? `manifest:${runId}` : null, () => api.manifest(runId));
  if (!status) return <Spinner label="Loading the run" />;
  const cands = status.candidates;
  const n = cands.length;
  const reached = LADDER.map((_, i) => cands.filter((c) => (c.stability?.stage ?? 0) >= i).length);
  return (
    <>
      <div className="page-head"><h1>Validate and export</h1><p>Model predictions prioritize candidates; DFT and experiment determine physical reality.</p></div>
      <section className="card" style={{ marginBottom: 20 }}>
        <h2>Validation ladder</h2>
        <p className="muted small">Six stages. Each candidate records the highest stage it reached and the result of every stage below it; this version records stages 0 and 1, and your own MLIP, DFT and experimental results take the next places in the candidate record.</p>
        <div className="cards-3" data-testid="ladder">
          {LADDER.map(([title, text, who], i) => (
            <div key={title} className="card card-tight" data-stage={i}>
              <div className="micro">Stage {i} · {who === 'here' ? 'recorded by this version' : 'your own step'}</div><h3 style={{ marginTop: 6 }}>{title}</h3>
              <div className="num" style={{ fontSize: 22, fontWeight: 600 }}>{reached[i] > 0 ? reached[i] : '—'}<span className="small muted" style={{ fontWeight: 400 }}> of {n}</span></div>
              <p className="small muted" style={{ margin: 0 }}>{text}{who === 'yours' ? ' Not run here.' : ''}</p>
            </div>
          ))}
        </div>
      </section>
      <div className="cards-2">
        <section className="card">
          <h2>Run bundle</h2>
          <p className="muted small">run.json, config.yaml (the engine configuration that reproduces the search), metrics.json (funnel and clusters), readiness.json, candidates.csv, targets.csv, the candidate-record schema, the engine's own output, one CIF per candidate under cifs/, environment.json and hashes.json.</p>
          {finished ? <a className="btn btn-primary" href={api.urls.bundle(runId)} download data-testid="download-bundle">Download run bundle (.zip)</a> : <span className="muted small">available when the search has finished ({seconds(status.progress.seconds)} so far)</span>}
          <div className="row" style={{ marginTop: 10 }}>
            <a className="btn btn-sm" href={api.urls.csv(runId)} download>candidates.csv</a>
            <a className="btn btn-sm" href={api.urls.json(runId)} download>candidates.json</a>
            <a className="btn btn-sm" href="/api/schema/candidate-record" target="_blank" rel="noopener">Candidate record schema</a>
            <Link className="btn btn-sm" to={`/p/${projectId}/runs/${runId}`}>← Candidates</Link>
          </div>
        </section>
        <section className="card" data-testid="score-in-prism">
          <h2>Benchmark these candidates in Prism</h2>
          <p className="muted small">The bundle's cifs/ and targets.csv are in the layout that MEIDNet's scorer reads. On any machine with the package:</p>
          <pre className="mono small" style={{ background: 'var(--tint)', border: '1px solid var(--line)', borderRadius: 8, padding: '8px 10px', overflow: 'auto', margin: '0 0 8px' }}>{'pip install "meidnet>=2.3.1"\nmeidnet download-data\nmeidnet score cifs/ --targets targets.csv --reference data/perov5'}</pre>
          <p className="muted small">Validity, uniqueness, novelty against Perov-5, diversity and distribution, plus the conditional metrics: target success, target error, multi-property success, constraint success, conditional diversity, target coverage. The values in targets.csv are the search's own predictions in this version, so the conditional metrics measure how closely the predictions follow the targets, not how the structures behave in DFT.</p>
          <ExternalLink href={PRISM_SCORE} className="btn btn-sm">The metrics, defined on Prism ↗</ExternalLink>
        </section>
      </div>
      <section className="card" style={{ marginTop: 20 }}>
        <h2>Manifest</h2>
        {error && <ErrorNote error={error} />}
        {!manifest ? <span className="muted small">written when the search has finished</span> : (
          <dl className="kv small">
            <dt>Run</dt><dd className="mono">{manifest.run_id} · {manifest.status} · {manifest.mode}</dd>
            <dt>Software</dt><dd>Matter {manifest.software.matter_version} · meidnet {manifest.software.meidnet_version} · commit {String(manifest.software.git_commit ?? '').slice(0, 10)}</dd>
            <dt>Model</dt><dd className="mono">{String((manifest.model as Record<string, unknown>).model_id)} · {String((manifest.model as Record<string, unknown>).sha256).slice(0, 12)}…</dd>
            <dt>Dataset</dt><dd>{String((manifest.dataset as Record<string, unknown>).title)} · fingerprint {String(((manifest.dataset as Record<string, unknown>).fingerprint as Record<string, string>)?.combined ?? '').slice(0, 12)}…</dd>
            <dt>Search</dt><dd>seed {String((manifest.design as Record<string, unknown>).seed)} · {JSON.stringify((manifest.design as Record<string, unknown>).candidate_budget)}</dd>
            <dt>Validation</dt><dd>{String((manifest.validation as Record<string, unknown>)?.status ?? '—')}{(manifest.validation as Record<string, unknown>)?.clusters ? ` · ${String((manifest.validation as Record<string, unknown>).clusters)} clusters` : ''}</dd>
            <dt>Duration</dt><dd>{seconds(manifest.durations_s.search_s ?? 0)}</dd>
            <dt>Candidates</dt><dd>{manifest.candidates.length} with file hashes</dd>
            <dt>Files</dt><dd>{Object.keys(manifest.exported_files).length} hashed</dd>
          </dl>
        )}
        {manifest && <a className="btn btn-sm" href={api.urls.manifest(runId)} target="_blank" rel="noopener" style={{ marginTop: 10 }}>Open manifest.json</a>}
      </section>
    </>
  );
}
