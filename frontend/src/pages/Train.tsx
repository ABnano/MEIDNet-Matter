import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useResource } from '@/api/hooks';
import { lab, type TrainJob, type TrainOptions } from '@/api/lab';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { train as C } from '@/copy/research';
import { seconds } from '@/lib/format';

/** Stage 2: start a small, fixed MEIDNet training; the page of the job shows it learning. */
export default function Train() {
  const navigate = useNavigate();
  const options = useResource<TrainOptions>('train/options', (s) => lab.trainOptions(s));
  const jobs = useResource<TrainJob[]>('train/jobs', () => lab.trainings());
  const [epochs, setEpochs] = useState(20);
  const [seed, setSeed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const o = options.data;
  const start = async () => {
    setBusy(true); setError(null);
    try { const job = await lab.train(epochs, seed); navigate(`/train/${job.job_id}`); } catch (e) { setError(e as Error); setBusy(false); }
  };
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head"><div className="micro">Stage 2 of 3 · Train</div><h1>{C.h1}</h1><p>{C.lead}</p></div>
        {options.error && <ErrorNote error={options.error} retry={options.reload} />}
        {options.loading && <Spinner label="Loading the experiment" />}
        {o && !o.available && <div className="banner banner-warn">Train Lite is not available on this server: it ships no featurised subset.</div>}
        {o?.available && o.subset && o.full_model && (
          <div className="cards-2" style={{ alignItems: 'start' }}>
            <div className="card stack" style={{ gap: 16 }}>
              <div>
                <h3 style={{ marginTop: 0 }}>The experiment</h3>
                <dl className="kv small">
                  <dt>data</dt><dd>{o.subset.train.toLocaleString()} Perov-5 materials to learn from, {o.subset.val} to measure on ({o.subset.nonzero_gap_train} and {o.subset.nonzero_gap_val} with a non-zero band gap)</dd>
                  <dt>recipe</dt><dd>{o.recipe}</dd>
                  <dt>model</dt><dd>MEIDNet: a graph encoder of the structure, a property encoder, one shared latent space, decoders for both; trained from scratch</dd>
                  <dt>budget</dt><dd>up to {o.limits?.epochs} epochs and {Math.round((o.limits?.seconds ?? 0) / 60)} minutes per job; about {o.seconds_per_epoch_estimate} s per epoch on the public server's two CPU cores, several times less on a workstation</dd>
                </dl>
              </div>
              <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
                <legend className="small muted">Epochs (passes over the 1,500 materials)</legend>
                <div className="row" style={{ gap: 8, marginTop: 6 }}>
                  {(o.epochs ?? [10, 20, 50]).map((e) => <button key={e} type="button" className={`btn btn-sm ${epochs === e ? 'btn-primary' : ''}`} aria-pressed={epochs === e} onClick={() => setEpochs(e)}>{e}</button>)}
                </div>
              </fieldset>
              <div className="field"><label htmlFor="train-seed">Seed</label><input id="train-seed" className="input input-num" type="number" min={0} max={9999} value={seed} onChange={(e) => setSeed(Math.max(0, Math.min(9999, Number(e.target.value))))} /><span className="small muted">the same seed gives the same model</span></div>
              {error && <ErrorNote error={error} />}
              <div className="row" style={{ gap: 12 }}>
                <button type="button" className="btn btn-primary btn-lg" onClick={start} disabled={busy} data-testid="train-start">{busy ? 'Starting…' : `Train for ${epochs} epochs`}</button>
                {o.estimated_seconds?.[String(epochs)] != null && <span className="small muted">about {seconds(o.estimated_seconds[String(epochs)])} on the public server</span>}
              </div>
            </div>
            <div className="stack" style={{ gap: 16 }}>
              <div className="card">
                <h3>What this is, and is not</h3>
                <p className="small muted">{C.what}</p>
                <p className="small muted">{C.sampling}</p>
                <p className="small muted">The full model for comparison: {o.full_model.model_id}, {o.full_model.training_rows?.toLocaleString()} materials, {o.full_model.epochs} epochs; on the same {o.subset.val} validation materials its error is {o.full_model.val_mae.heat_all.toFixed(3)} eV/atom for the formation enthalpy and {o.full_model.val_mae_dir_gap_nonzero.toFixed(2)} eV for the band gap of the materials that have one.</p>
              </div>
              {jobs.data && jobs.data.length > 0 && (
                <div className="card">
                  <h3>Your trainings</h3>
                  <ul className="small">{jobs.data.map((j) => <li key={j.job_id}><Link to={`/train/${j.job_id}`}>{j.job_id}</Link> · {j.status} · {j.request.epochs} epochs, seed {j.request.seed}</li>)}</ul>
                </div>
              )}
              <div className="card"><h3>Then, at full size</h3><p className="small muted">{C.after}</p><Link to="/method#run" className="btn btn-sm">The commands, step by step</Link></div>
            </div>
          </div>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
