import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { research, type CheckpointInfo, type GenJob } from '@/api/research';
import { useResource } from '@/api/hooks';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { play as P } from '@/copy/research';

const PRESETS: Array<[string, number[]]> = [['1.5 eV', [1.5]], ['1.5 and 2.5 eV', [1.5, 2.5]], ['1, 2 and 3 eV', [1.0, 2.0, 3.0]]];
const RADIOACTIVE = ['Ac', 'Np', 'Pa', 'Pm', 'Pu', 'Tc', 'Th', 'U'];
const TOXIC = ['Tl', 'Pb', 'Hg', 'Cd', 'As', 'Be'];

export default function Play() {
  const navigate = useNavigate();
  const ck = useResource<{ checkpoints: CheckpointInfo[] }>('checkpoints', (s) => research.checkpoints(s));
  const jobs = useResource<GenJob[]>('generate/jobs', () => research.jobs());
  const models = (ck.data?.checkpoints ?? []).filter((c) => c.geometry === 'wyckoff' && c.available);
  const [model, setModel] = useState('mp20-wyck');
  const [targets, setTargets] = useState<number[]>([1.5, 2.5]);
  const [custom, setCustom] = useState('');
  const [perTarget, setPerTarget] = useState(6);
  const [window, setWindow] = useState(0.5);
  const [anion, setAnion] = useState(true);
  const [excluded, setExcluded] = useState<string[]>(RADIOACTIVE);
  const [seed, setSeed] = useState(0);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  const addTarget = () => {
    const v = parseFloat(custom);
    if (!Number.isNaN(v) && v > 0 && v <= 6 && targets.length < 3 && !targets.includes(v)) setTargets([...targets, v].sort((a, b) => a - b));
    setCustom('');
  };
  const toggle = (el: string) => setExcluded(excluded.includes(el) ? excluded.filter((e) => e !== el) : [...excluded, el]);
  const start = async () => {
    setBusy(true); setError(null);
    try {
      const job = await research.generate({ model_id: model, targets, per_target: perTarget, window_eV: window, require_anion: anion, exclude_elements: excluded, seed });
      navigate(`/play/${job.job_id}`);
    } catch (e) { setError(e as Error); setBusy(false); }
  };
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head"><h1>{P.h1}</h1><p>{P.lead}</p></div>
        {ck.error && <ErrorNote error={ck.error} retry={ck.reload} />}
        <div className="cards-2" style={{ alignItems: 'start' }}>
          <div className="card stack" style={{ gap: 16 }}>
            <div className="field">
              <label htmlFor="play-model">Model</label>
              <select id="play-model" className="input" value={model} onChange={(e) => setModel(e.target.value)}>
                {models.map((m) => <option key={m.id} value={m.id}>{m.id} — {m.description}</option>)}
                {models.length === 0 && <option value="mp20-wyck">mp20-wyck</option>}
              </select>
            </div>
            <div className="field">
              <span className="small muted" id="play-targets-label">Requested band gaps (eV), up to three</span>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 6 }} aria-labelledby="play-targets-label">
                {targets.map((t) => <span className="chip" key={t}>{t} eV <button type="button" aria-label={`Remove ${t} eV`} onClick={() => setTargets(targets.filter((x) => x !== t))}>×</button></span>)}
                <input className="input input-num" id="play-target-custom" type="number" step="0.1" min="0.1" max="6" placeholder="add…" value={custom} onChange={(e) => setCustom(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTarget(); } }} aria-label="Add a target in eV" style={{ width: 90 }} />
                <button type="button" className="btn btn-sm" onClick={addTarget} disabled={targets.length >= 3}>Add</button>
              </div>
              <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: 'wrap' }}>{PRESETS.map(([l, v]) => <button key={l} type="button" className="btn btn-sm btn-ghost" onClick={() => setTargets(v)}>{l}</button>)}</div>
              <p className="small muted" style={{ marginTop: 6 }}>{P.rangeNote}</p>
            </div>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
              <div className="field"><label htmlFor="play-n">Structures per target</label><input id="play-n" className="input input-num" type="number" min={1} max={10} value={perTarget} onChange={(e) => setPerTarget(Math.max(1, Math.min(10, Number(e.target.value))))} /></div>
              <div className="field"><label htmlFor="play-w">Window (eV, both judges)</label><input id="play-w" className="input input-num" type="number" step="0.05" min={0.25} max={1} value={window} onChange={(e) => setWindow(Number(e.target.value))} /></div>
              <div className="field"><label htmlFor="play-seed">Seed</label><input id="play-seed" className="input input-num" type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></div>
            </div>
            <div className="field">
              <label><input type="checkbox" checked={anion} onChange={(e) => setAnion(e.target.checked)} /> Require at least one anion (F, O, Cl, N, Br, I, S, Se, Te)</label>
              <p className="small muted" style={{ margin: '4px 0 0' }}>Without it the species head returns the training set's dominant answer, which for MP-20 is a zero-gap intermetallic.</p>
            </div>
            <div className="field">
              <span className="small muted">Excluded elements</span>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                {[...RADIOACTIVE, ...TOXIC].map((el) => <button type="button" key={el} className={`btn btn-sm ${excluded.includes(el) ? 'btn-primary' : ''}`} aria-pressed={excluded.includes(el)} onClick={() => toggle(el)}>{el}</button>)}
              </div>
              <p className="small muted" style={{ margin: '4px 0 0' }}>Radioactive elements are excluded by default; add the toxic ones if the candidates should be practical.</p>
            </div>
            {error && <ErrorNote error={error} />}
            <div className="row" style={{ gap: 12 }}>
              <button type="button" className="btn btn-primary btn-lg" onClick={start} disabled={busy || targets.length === 0}>{busy ? 'Starting…' : 'Generate'}</button>
              <span className="small muted">{P.sharedHost}</span>
            </div>
          </div>
          <div className="stack" style={{ gap: 16 }}>
            <div className="card">
              <h3>What you get back</h3>
              <ul className="small">
                <li>For every structure: the model's label <b>read from the returned cell</b>, the independent judge's value, whether both lie inside your window, the space group, a charge-balance flag, whether the formula exists in MP-20 (with its recorded gaps), and its AMD distance to the nearest training structure.</li>
                <li>The CIF of every cell, a table, the record as JSON, and the command that relaxes the cells locally with two potentials.</li>
              </ul>
              <p className="note small">{P.stabilityNote}</p>
            </div>
            {jobs.data && jobs.data.length > 0 && (
              <div className="card">
                <h3>Your jobs</h3>
                <ul className="small">{jobs.data.map((j) => <li key={j.job_id}><Link to={`/play/${j.job_id}`}>{j.job_id}</Link> · {j.status} · {j.request.targets.join(', ')} eV · {j.n_consensus}/{j.n_candidates} accepted</li>)}</ul>
              </div>
            )}
            {ck.loading && <Spinner label="Loading the models" />}
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
