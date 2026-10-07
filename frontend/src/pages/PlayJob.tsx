import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router';
import { research, type GenCandidate, type GenJob } from '@/api/research';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Meter, Spinner } from '@/components/ui';
import { Num } from '@/components/research';

/** Polls a generation job while it runs (1.5 s), backing off on failures and pausing when the tab is hidden. */
function useJob(id: string | null) {
  const [job, setJob] = useState<GenJob | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const timer = useRef<number | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!id) return;
    let cancelled = false; let failures = 0;
    const ctrl = new AbortController();
    const schedule = (ms: number) => { timer.current = window.setTimeout(poll, ms); };
    async function poll() {
      if (cancelled) return;
      if (document.visibilityState === 'hidden') { schedule(2000); return; }
      try {
        const j = await research.jobFull(id!, ctrl.signal);
        if (cancelled) return;
        failures = 0; setError(null); setJob(j);
        if (j.status === 'queued' || j.status === 'running') schedule(1500);
      } catch (e) {
        if (cancelled || (e as Error).name === 'AbortError') return;
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

function Yes({ v }: { v: boolean | null | undefined }) { return <span>{v === null || v === undefined ? '—' : v ? 'yes' : 'no'}</span>; }

export default function PlayJob() {
  const { jobId = '' } = useParams();
  const { job, error, retry } = useJob(jobId);
  const [open, setOpen] = useState<GenCandidate | null>(null);
  const running = job && (job.status === 'queued' || job.status === 'running');
  const total = job ? job.request.targets.length * job.request.per_target : 1;
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head">
          <div className="micro"><Link to="/play">Generate</Link> · job {jobId}</div>
          <h1>{job ? `${job.request.targets.join(', ')} eV` : 'Generation job'}</h1>
          {job && <p>{job.request.per_target} structures per target · window {job.request.window_eV} eV · {job.request.require_anion ? 'anion required' : 'no anion requirement'} · excluded {job.request.exclude_elements.join(' ') || 'none'} · seed {job.request.seed}</p>}
        </div>
        {error && <ErrorNote error={error} retry={retry} />}
        {!job && !error && <Spinner label="Loading the job" />}
        {job && (
          <>
            <div className="card" aria-live="polite">
              <div className="row" style={{ gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <b>{job.status}</b><span className="small muted">{job.progress.phase} · {job.progress.seconds.toFixed(0)} s · target {Math.min(job.progress.target_index + 1, job.progress.targets)} of {job.progress.targets} · {job.progress.attempts} draws</span>
                {running && <button type="button" className="btn btn-sm" onClick={() => research.stopJob(job.job_id)}>Stop</button>}
                {!running && <a className="btn btn-sm" href={research.zipUrl(job.job_id)}>Download everything (zip)</a>}
              </div>
              <div style={{ marginTop: 8 }}><Meter value={job.n_candidates} max={total} kind="info" /><span className="small muted">{job.n_candidates} of up to {total} structures kept so far</span></div>
              {job.notes.length > 0 && <ul className="small muted" style={{ margin: '8px 0 0 18px' }}>{job.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
              {job.error && <p className="error-text">{job.error}</p>}
              {job.log && job.log.length > 0 && <div className="progress-list" style={{ marginTop: 8 }}>{job.log.slice(-8).map((l, i) => <div key={i}>{l}</div>)}</div>}
            </div>

            {job.judge && (
              <p className="small muted" style={{ marginTop: 12 }}>
                Independent judge: {job.judge.name}{job.judge.qualification ? ` — on the dataset's test split MAE ${Number(job.judge.qualification.mae_eV).toFixed(2)} eV, Spearman ${Number(job.judge.qualification.spearman).toFixed(2)} (n = ${job.judge.qualification.n})` : ''}{!job.judge.available && job.status !== 'running' ? ` · unavailable on this server (${job.judge.error ?? 'not loaded'})` : ''}.
              </p>
            )}

            {job.candidates && job.candidates.length > 0 && (
              <>
                <h2 style={{ marginTop: 20 }}>Structures</h2>
                {job.funnel && <p className="small muted">{job.funnel.attempted} draws → {job.funnel.kept} kept by the structure-read label → {job.funnel.judged} judged → <b>{job.funnel.consensus} accepted by both judges</b>.</p>}
                <div className="table-wrap">
                  <table className="table">
                    <caption className="sr-only">Generated structures</caption>
                    <thead><tr><th scope="col">requested</th><th scope="col">formula</th><th scope="col">label from the structure</th><th scope="col">judge</th><th scope="col">both agree</th><th scope="col">space group</th><th scope="col">atoms</th><th scope="col">charge balance</th><th scope="col">in MP-20</th><th scope="col">AMD</th><th scope="col">cell</th></tr></thead>
                    <tbody>
                      {job.candidates.map((c) => (
                        <tr key={c.candidate_id} aria-selected={open?.candidate_id === c.candidate_id} onClick={() => setOpen(open?.candidate_id === c.candidate_id ? null : c)} style={{ cursor: 'pointer' }}>
                          <td className="num">{c.target_eV.toFixed(1)}</td><td><b>{c.formula}</b></td>
                          <td className="num"><Num v={c.label_structure_eV} /></td><td className="num"><Num v={c.judge_eV} />{c.metal_by_judge ? <span className="small faint"> metal</span> : null}</td>
                          <td><b>{c.consensus ? 'yes' : 'no'}</b></td><td className="num">{c.spacegroup}</td><td className="num">{c.natoms}</td>
                          <td><Yes v={c.charge_balanced} /></td><td className="small">{c.known_formula === null ? '—' : c.known_formula ? `yes (${c.recorded_gaps_eV.map((g) => g.toFixed(2)).join(', ')} eV)` : 'no'}</td>
                          <td className="num"><Num v={c.amd_nearest_reference} d={3} />{c.novel_by_amd ? <span className="small faint"> new</span> : null}</td>
                          <td><a className="small" href={research.cifUrl(job.job_id, c.candidate_id)} download onClick={(e) => e.stopPropagation()}>CIF</a></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {open && (
                  <div className="card" style={{ marginTop: 12 }}>
                    <h3>{open.formula} <span className="small faint mono">{open.candidate_id}</span></h3>
                    <dl className="kv">
                      <dt>lattice</dt><dd className="mono small">a {open.lattice.a} b {open.lattice.b} c {open.lattice.c} Å · α {open.lattice.alpha} β {open.lattice.beta} γ {open.lattice.gamma}° · {open.volume_per_atom} Å³/atom</dd>
                      <dt>formation energy label</dt><dd><Num v={open.label_formation_energy_eV_atom} /> eV/atom</dd>
                      <dt>label</dt><dd className="small">{open.evidence.label}</dd>
                      <dt>judge</dt><dd className="small">{open.evidence.judge}</dd>
                      <dt>novelty</dt><dd className="small">{open.evidence.novelty}</dd>
                      <dt>stability</dt><dd className="small">{open.stability.status}: {open.stability.note}</dd>
                      <dt>sha256</dt><dd className="mono small">{open.sha256}</dd>
                    </dl>
                  </div>
                )}
                <h3 style={{ marginTop: 20 }}>Relax locally</h3>
                <p className="small muted">The server does not relax cells. Download the zip, then from its folder:</p>
                <div className="cmd">{job.relax_command}</div>
                <p className="small muted" style={{ marginTop: 6 }}>Then run both judges again on <code>relaxed_tensornet/</code> before quoting a band gap for the relaxed structure. Measured on MP-20, relaxation lowers the energy by whole electron-volts per atom and moves atoms by bond lengths: the relaxed cell is the product.</p>
              </>
            )}
            {!running && job.candidates && job.candidates.length === 0 && <p className="note" style={{ marginTop: 16 }}>No structure passed the structure-read label window for these targets. Above 3 eV the generator saturates on MP-20; try 1–3 eV, a wider window, or more structures per target.</p>}
            {job.per_target && job.per_target.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 16 }}>
                <table className="table"><thead><tr><th scope="col">requested</th><th scope="col">kept</th><th scope="col">accepted</th><th scope="col">label mean</th><th scope="col">judge mean</th></tr></thead>
                  <tbody>{job.per_target.map((p) => <tr key={p.requested}><td className="num">{p.requested.toFixed(1)}</td><td className="num">{p.kept}</td><td className="num">{p.consensus}</td><td className="num"><Num v={p.label_mean_eV} /></td><td className="num"><Num v={p.judge_mean_eV} /></td></tr>)}</tbody></table>
              </div>
            )}
          </>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
