import { Link, useParams } from 'react-router';
import { api } from '@/api/endpoints';
import { useResource, useRunPolling } from '@/api/hooks';
import { ErrorNote, Spinner } from '@/components/ui';
import { seconds } from '@/lib/format';

const LEVELS = [
  ['Level 0 · Model prediction', 'Predicted', 'Every candidate of this run: predicted values, domain status, rule results, nearest training materials.'],
  ['Level 1 · ML-potential screening', 'MLFF-screened', 'Relaxation with a machine-learned interatomic potential and a formation-energy check. Not run in this version.'],
  ['Level 2 · DFT relaxation and hull', 'DFT-computed', 'Density-functional relaxation and the energy above the convex hull. Not run in this version.'],
  ['Level 3 · Experiment', 'Experimentally measured', 'Synthesis and measurement. Not run in this version.'],
];

export default function Validate() {
  const { projectId = 'perov5-demo', runId = '' } = useParams();
  const { status } = useRunPolling(runId);
  const finished = status && status.status !== 'queued' && status.status !== 'running';
  const { data: manifest, error } = useResource(finished ? `manifest:${runId}` : null, () => api.manifest(runId));
  if (!status) return <Spinner label="Loading the run" />;
  const n = status.candidates.length;
  return (
    <>
      <div className="page-head"><h1>Validate and export</h1><p>Model predictions prioritize candidates; DFT and experiment determine physical reality.</p></div>
      <section className="card" style={{ marginBottom: 20 }}>
        <h2>Validation funnel</h2>
        <div className="cards-4">
          {LEVELS.map(([title, label, text], i) => (
            <div key={title} className="card card-tight">
              <div className="micro">{label}</div><h3 style={{ marginTop: 6 }}>{title}</h3>
              <div className="num" style={{ fontSize: 22, fontWeight: 600 }}>{i === 0 ? n : '—'}</div>
              <p className="small muted" style={{ margin: 0 }}>{text}</p>
            </div>
          ))}
        </div>
      </section>
      <div className="cards-2">
        <section className="card">
          <h2>Run bundle</h2>
          <p className="muted small">run.json, config.yaml (the engine configuration that reproduces the search), metrics.json, readiness.json, candidates.csv, the engine's own output, one CIF per candidate, environment.json and hashes.json.</p>
          {finished ? <a className="btn btn-primary" href={api.urls.bundle(runId)} download data-testid="download-bundle">Download run bundle (.zip)</a> : <span className="muted small">available when the search has finished ({seconds(status.progress.seconds)} so far)</span>}
          <div className="row" style={{ marginTop: 10 }}>
            <a className="btn btn-sm" href={api.urls.csv(runId)} download>candidates.csv</a>
            <a className="btn btn-sm" href={api.urls.json(runId)} download>candidates.json</a>
            <Link className="btn btn-sm" to={`/p/${projectId}/runs/${runId}`}>← Candidates</Link>
          </div>
        </section>
        <section className="card">
          <h2>Manifest</h2>
          {error && <ErrorNote error={error} />}
          {!manifest ? <span className="muted small">written when the search has finished</span> : (
            <dl className="kv small">
              <dt>Run</dt><dd className="mono">{manifest.run_id} · {manifest.status} · {manifest.mode}</dd>
              <dt>Software</dt><dd>Matter {manifest.software.matter_version} · meidnet {manifest.software.meidnet_version} · commit {String(manifest.software.git_commit ?? '').slice(0, 10)}</dd>
              <dt>Model</dt><dd className="mono">{String((manifest.model as Record<string, unknown>).model_id)} · {String((manifest.model as Record<string, unknown>).sha256).slice(0, 12)}…</dd>
              <dt>Dataset</dt><dd>{String((manifest.dataset as Record<string, unknown>).title)} · fingerprint {String(((manifest.dataset as Record<string, unknown>).fingerprint as Record<string, string>)?.combined ?? '').slice(0, 12)}…</dd>
              <dt>Search</dt><dd>seed {String((manifest.design as Record<string, unknown>).seed)} · {JSON.stringify((manifest.design as Record<string, unknown>).candidate_budget)}</dd>
              <dt>Duration</dt><dd>{seconds(manifest.durations_s.search_s ?? 0)}</dd>
              <dt>Candidates</dt><dd>{manifest.candidates.length} with file hashes</dd>
              <dt>Files</dt><dd>{Object.keys(manifest.exported_files).length} hashed</dd>
            </dl>
          )}
          {manifest && <a className="btn btn-sm" href={api.urls.manifest(runId)} target="_blank" rel="noopener" style={{ marginTop: 10 }}>Open manifest.json</a>}
        </section>
      </div>
    </>
  );
}
