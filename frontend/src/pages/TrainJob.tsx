import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router';
import { isGone } from '@/api/client';
import { lab, type TrainJob as TrainJobT } from '@/api/lab';
import { LineChart } from '@/components/charts/LineChart';
import { Scatter } from '@/components/charts/Scatter';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Meter, Segmented, Spinner } from '@/components/ui';
import { JobGone } from '@/features/lifecycle/Gone';

/** Polls a training job while it runs (1 s), backing off on failures; stops at once when the job is gone. */
function useTraining(id: string) {
  const [job, setJob] = useState<TrainJobT | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState(0);
  const timer = useRef<number | null>(null);
  useEffect(() => {
    let cancelled = false; let failures = 0;
    const ctrl = new AbortController();
    const schedule = (ms: number) => { timer.current = window.setTimeout(poll, ms); };
    async function poll() {
      if (cancelled) return;
      try {
        const j = await lab.training(id, ctrl.signal);
        if (cancelled) return;
        failures = 0; setError(null); setJob(j);
        if (j.status === 'queued' || j.status === 'running') schedule(1000);
      } catch (e) {
        if (cancelled || (e as Error).name === 'AbortError') return;
        if (isGone(e)) { setJob(null); setError(e as Error); return; }
        failures += 1;
        if (failures >= 6) { setError(e as Error); return; }
        schedule(Math.min(15000, 1000 * 2 ** failures));
      }
    }
    poll();
    return () => { cancelled = true; ctrl.abort(); if (timer.current) clearTimeout(timer.current); };
  }, [id, tick]);
  const retry = useCallback(() => { setError(null); setTick((t) => t + 1); }, []);
  return { job, error, retry };
}

const WORD = (r: number | null) => (r == null ? '—' : r < 0.25 ? 'good' : r < 0.5 ? 'fair' : 'weak');
const PROP: Record<string, [string, string]> = { dir_gap: ['direct band gap', 'eV'], heat_all: ['formation enthalpy', 'eV/atom'] };

export default function TrainJob() {
  const { jobId = '' } = useParams();
  const { job, error, retry } = useTraining(jobId);
  const [prop, setProp] = useState<'dir_gap' | 'heat_all'>('dir_gap');
  const [stopError, setStopError] = useState<string | null>(null);
  const running = job && (job.status === 'queued' || job.status === 'running');
  const hist = job?.history ?? [];
  const x = hist.map((h) => h.epoch);
  const res = job?.result ?? null;
  const predPoints = useMemo(() => {
    if (!res) return [];
    const i = res.predictions.columns.indexOf(prop);
    const k = res.predictions.columns.length;
    return res.predictions.rows.map((r) => ({ id: r[0], label: r[1], x: Number(r[2 + i]), y: Number(r[2 + k + i]), v: Number(r[2 + i]) }));
  }, [res, prop]);
  const mapPoints = useMemo(() => (res ? res.map.points.map(([id, px, py, gap]) => ({ id, x: px, y: py, v: gap, label: id })) : []), [res]);
  const full = job?.result?.full_model;
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head">
          <div className="micro"><Link to="/train">Train</Link> · job {jobId}</div>
          <h1>{job ? `${job.request.epochs} epochs, seed ${job.request.seed}` : 'Training job'}</h1>
          <p>A MEIDNet model trained from scratch on 1,500 Perov-5 materials; measured on 500 it never saw.</p>
        </div>
        {error && (isGone(error) ? <JobGone error={error} /> : <ErrorNote error={error} retry={retry} />)}
        {!job && !error && <Spinner label="Loading the job" />}
        {job && (
          <>
            <div className="card" aria-live="polite">
              <div className="row" style={{ gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <b>{job.status}</b><span className="small muted">{job.progress.phase} · epoch {job.progress.epoch} of {job.progress.epochs} · {job.progress.seconds.toFixed(0)} s</span>
                {running && <button type="button" className="btn btn-sm" onClick={() => { setStopError(null); lab.stopTraining(job.job_id).catch((e: Error) => setStopError(e.message)); }}>Stop after this epoch</button>}
              </div>
              <div style={{ marginTop: 8 }}><Meter value={job.progress.epoch} max={job.progress.epochs} kind="info" /></div>
              {stopError && <p className="error-text small" role="alert">{stopError}</p>}
              {job.error && <p className="error-text">{job.error}</p>}
            </div>

            {hist.length > 0 && (
              <div className="cards-2" style={{ marginTop: 16, alignItems: 'start' }}>
                <div className="card">
                  <h3>Training loss</h3>
                  <LineChart x={x} xLabel="epoch" yLabel="loss" series={[{ name: 'total', values: hist.map((h) => h.loss) }, { name: 'property from structure', values: hist.map((h) => h.parts.prop_from_struct ?? null), dashed: true }, { name: 'reconstruction', values: hist.map((h) => h.parts.recon_joint ?? null), dashed: true }]} />
                  <p className="small muted">The sum the optimiser lowers: rebuilding the cell, predicting the properties, and aligning the two encodings. The alignment term is switched on gradually over the first epochs, so the total can rise while its parts fall. Alignment cosine now <span className="num">{hist[hist.length - 1].alignment_cosine.toFixed(2)}</span>.</p>
                </div>
                <div className="card">
                  <h3>Validation error, epoch by epoch</h3>
                  <LineChart x={x} xLabel="epoch" yLabel="MAE" yMin={0}
                    series={[{ name: 'band gap (eV)', values: hist.map((h) => h.val_mae.dir_gap ?? null) }, { name: 'formation enthalpy (eV/atom)', values: hist.map((h) => h.val_mae.heat_all ?? null) }]}
                    reference={full ? { value: full.val_mae.dir_gap, label: `full model, band gap ${full.val_mae.dir_gap.toFixed(3)}` } : null} />
                  <p className="small muted">Measured on all 500 validation materials after every epoch, zero gaps included, in physical units. The dashed line is the demo's full model on the same materials. The band-gap error in the summary below counts only the materials with a non-zero gap, so it is larger.</p>
                </div>
              </div>
            )}

            {res && (
              <>
                <div className="stat-tiles" style={{ marginTop: 16 }}>
                  {Object.entries(res.against_spread).map(([c, a]) => (
                    <div className="card" key={c}><div className="k">{PROP[c]?.[0] ?? c}{c === 'dir_gap' ? ' · non-zero gaps only' : ''}</div><div className="v">{a.mae.toFixed(c === 'dir_gap' ? 2 : 3)} {PROP[c]?.[1]}</div>
                      <div className="n">{WORD(a.ratio)}: {a.ratio == null ? '—' : a.ratio.toFixed(2)} of the spread ({a.basis}); the full model: {a.full_model_mae.toFixed(c === 'dir_gap' ? 2 : 3)} {PROP[c]?.[1]}</div></div>
                  ))}
                  <div className="card"><div className="k">Structure ↔ property retrieval</div><div className="v">{Math.round(100 * res.val.retrieval_top1)}%</div><div className="n">top-1 among the {res.n_val} validation materials: how often a property vector finds its own structure in the shared space</div></div>
                </div>
                <div className="cards-2" style={{ marginTop: 16, alignItems: 'start' }}>
                  <div className="card">
                    <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}><h3 style={{ margin: 0 }}>Predicted against reference</h3>
                      <Segmented value={prop} label="Property" options={[{ value: 'dir_gap', label: 'Band gap' }, { value: 'heat_all', label: 'Formation enthalpy' }]} onChange={setProp} /></div>
                    <Scatter points={predPoints} identity colour={{ min: Math.min(...predPoints.map((p) => p.v)), max: Math.max(...predPoints.map((p) => p.v)), label: `reference ${PROP[prop][0]}`, unit: PROP[prop][1] }}
                      xLabel={`reference (DFT, ${PROP[prop][1]})`} yLabel={`predicted (${PROP[prop][1]})`} width={520} height={400} />
                    <p className="small muted">Each point is one validation material; the dashed line is perfect agreement. The model's reading of the structure, read from the structure's own encoding.</p>
                  </div>
                  <div className="card">
                    <h3>The learned space, after training</h3>
                    <Scatter points={mapPoints} colour={{ min: 0, max: Math.max(0.5, ...mapPoints.map((p) => p.v)), label: 'reference band gap', unit: 'eV' }} xLabel="first principal component" yLabel="second principal component" width={520} height={400} />
                    <p className="small muted">The 500 validation materials placed by this model's structure encoder (two principal components, {Math.round(100 * (res.map.explained_variance[0] + res.map.explained_variance[1]))}% of the variance). Compare with the map of the full model on the Explore page.</p>
                  </div>
                </div>
                <div className="card" style={{ marginTop: 16 }}>
                  <h3>What this is</h3>
                  <p className="small muted">{res.what_this_is}</p>
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <a className="btn btn-sm" href={lab.modelUrl(job.job_id)}>Download the model (.pt)</a>
                    <a className="btn btn-sm" href={lab.configUrl(job.job_id)}>The recipe (config.yaml)</a>
                    <a className="btn btn-sm" href={lab.predictionsUrl(job.job_id)}>Predictions (CSV)</a>
                  </div>
                  <h3 style={{ marginTop: 16 }}>Then, at full size, on your computer</h3>
                  <pre className="mono small" style={{ background: 'var(--tint)', border: '1px solid var(--line)', padding: 10, overflowX: 'auto' }}>{`pip install --extra-index-url https://download.pytorch.org/whl/cpu "meidnet-matter[judge]"\nmeidnet download-data                     # the Perov-5 CSVs\n${res.full_training_command}`}</pre>
                  <p className="small muted">The same recipe on all 11,356 training materials for 200 epochs is the demo's default model. On your own data: the same configuration with your table (Method › Run it on your data). {job.provenance ? `Engine ${job.provenance.meidnet_version}, Matter ${job.provenance.matter_version}.` : ''}</p>
                  <div className="row" style={{ gap: 12, marginTop: 12 }}><Link to="/generate" className="btn btn-primary">Next: generate structures →</Link><Link to="/train" className="btn">Train again</Link></div>
                </div>
              </>
            )}
          </>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
