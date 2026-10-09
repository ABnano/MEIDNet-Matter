import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router';
import { research, type GenCandidate, type GenJob } from '@/api/research';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { CellViewer } from '@/components/structure/CellViewer';
import { ErrorNote, Meter, Segmented, Spinner } from '@/components/ui';
import { Num } from '@/components/research';
import { explicitStructure } from '@/lib/lattice';

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

/** The three statuses of a live candidate, kept apart: the gap window, the charge balance, the relaxation. */
function statusesOf(c: GenCandidate) {
  if (c.statuses) return c.statuses;
  const both = c.within_window.label && c.within_window.judge;
  return {
    gap_window: both ? 'both models' : c.within_window.label ? 'label only' : c.within_window.judge ? 'judge only' : 'neither',
    charge_balance: c.charge_balanced ? 'yes' : c.charge_balanced === false ? 'no' : 'unknown',
    relaxed: 'not in the live run',
  } as const;
}

function cellOf(c: GenCandidate) {
  if (!c.sites || !c.lattice_matrix) return null;
  return explicitStructure(c.sites, c.lattice_matrix);
}

/** Requested gap against the two readings of every structure, with the identity line and the window band. */
function EvidenceMap({ cands, window, selected, onOpen }: { cands: GenCandidate[]; window: number; selected: string | null; onOpen: (c: GenCandidate) => void }) {
  const [axis, setAxis] = useState<'judge' | 'label'>('judge');
  const pts = cands.map((c) => ({ c, x: c.target_eV, y: axis === 'judge' ? c.judge_eV : c.label_structure_eV })).filter((p): p is { c: GenCandidate; x: number; y: number } => p.y != null);
  const W = 560, H = 320, m = { l: 48, r: 14, t: 14, b: 40 };
  const vals = [0, ...pts.map((p) => p.x), ...pts.map((p) => p.y), ...cands.map((c) => c.target_eV + window)];
  const hi = Math.max(1, ...vals) * 1.06, lo = Math.min(0, ...vals);
  const X = (v: number) => m.l + ((v - lo) / (hi - lo || 1)) * (W - m.l - m.r);
  const Y = (v: number) => m.t + (H - m.t - m.b) - ((v - lo) / (hi - lo || 1)) * (H - m.t - m.b);
  const targets = [...new Set(cands.map((c) => c.target_eV))];
  const ticks = [0, 1, 2, 3, 4, 5, 6].filter((v) => v >= lo && v <= hi);
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <b>Requested in, delivered out</b>
        <Segmented value={axis} label="Vertical axis" options={[{ value: 'judge', label: 'Judge (second model)' }, { value: 'label', label: 'Label from the structure' }]} onChange={setAxis} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Requested band gap against the ${axis === 'judge' ? 'judge (second model)' : 'structure-read label'} for every generated structure`}>
        {targets.map((t) => <rect key={t} x={X(t) - 6} y={Y(t + window)} width={12} height={Math.max(1, Y(t - window) - Y(t + window))} fill="var(--c-targets)" opacity={0.15}><title>window {t - window}–{t + window} eV</title></rect>)}
        <line x1={X(lo)} y1={Y(lo)} x2={X(hi)} y2={Y(hi)} stroke="var(--ink)" strokeWidth={1} />
        {pts.map(({ c, x, y }) => {
          const sel = c.candidate_id === selected;
          return <circle key={c.candidate_id} cx={X(x)} cy={Y(y)} r={sel ? 7 : 5} style={{ cursor: 'pointer' }} onClick={() => onOpen(c)}
            fill={c.consensus ? 'var(--c-candidates)' : 'var(--card)'} stroke="var(--c-candidates)" strokeWidth={2}>
            <title>{c.formula}: requested {x.toFixed(1)} eV, {axis === 'judge' ? 'judge' : 'label'} {y.toFixed(2)} eV{c.consensus ? ' · both models in window' : ''}</title></circle>;
        })}
        <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} stroke="var(--line)" /><line x1={m.l} x2={m.l} y1={m.t} y2={H - m.b} stroke="var(--line)" />
        {ticks.map((v) => <text key={`x${v}`} x={X(v)} y={H - m.b + 14} fontSize={10} textAnchor="middle" fill="var(--faint)">{v}</text>)}
        {ticks.map((v) => <text key={`y${v}`} x={m.l - 5} y={Y(v) + 3} fontSize={10} textAnchor="end" fill="var(--faint)">{v}</text>)}
        <text x={(W + m.l) / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">requested band gap (eV)</text>
        <text x={12} y={H / 2} textAnchor="middle" fontSize={11} fill="var(--muted)" transform={`rotate(-90 12 ${H / 2})`}>{axis === 'judge' ? 'judge (second model)' : 'label from the structure'} (eV), unrelaxed cell</text>
      </svg>
      <p className="small muted">Filled: both models inside the window. Hollow: one or neither. Line: delivered equals requested. Pink: the window around each request. These cells are not relaxed; the MP-20 study shows the same plot on relaxed cells.</p>
    </div>
  );
}

function CandidateCard({ c, selected, onOpen, jobId }: { c: GenCandidate; selected: boolean; onOpen: () => void; jobId: string }) {
  const cell = useMemo(() => cellOf(c), [c]);
  const st = statusesOf(c);
  return (
    <article className="card card-tight ccard" aria-selected={selected} style={selected ? { borderColor: 'var(--p1)' } : undefined}>
      <div className="thumb">{cell ? <CellViewer structure={cell} size={96} title={c.formula} interactive={false} /> : <div className="small faint">no cell</div>}</div>
      <div>
        <h3 style={{ margin: 0 }}><button type="button" className="btn btn-ghost" style={{ padding: 0, fontSize: 17 }} onClick={onOpen}>{c.formula}</button></h3>
        <div className="small muted">asked {c.target_eV.toFixed(1)} eV · label from the structure <b className="num"><Num v={c.label_structure_eV} /></b> · judge <b className="num"><Num v={c.judge_eV} /></b> eV</div>
        <div className="lines small" style={{ marginTop: 6 }}>
          <div>Gap window: <b>{st.gap_window}</b></div>
          <div>Charge balanced: <b>{st.charge_balance}</b></div>
          <div>Relaxed and re-judged: <b>{st.relaxed}</b></div>
          <div className="faint">space group {c.spacegroup} · {c.natoms} atoms · {c.known_formula ? `formula known in MP-20 (${c.recorded_gaps_eV.map((g) => g.toFixed(2)).join(', ')} eV)` : c.known_formula === false ? 'formula not in MP-20' : ''}{c.amd_nearest_reference != null ? ` · AMD ${c.amd_nearest_reference.toFixed(3)}${c.novel_by_amd ? ' (new)' : ''}` : ''}</div>
        </div>
        <div className="foot">
          <button type="button" className="btn btn-sm" onClick={onOpen}>Details</button>
          <a className="btn btn-sm" href={research.cifUrl(jobId, c.candidate_id)} download>CIF ↓</a>
        </div>
      </div>
    </article>
  );
}

export default function PlayJob() {
  const { jobId = '' } = useParams();
  const { job, error, retry } = useJob(jobId);
  const [open, setOpen] = useState<GenCandidate | null>(null);
  const [view, setView] = useState<'cards' | 'table'>('cards');
  const cell = useMemo(() => (open ? cellOf(open) : null), [open]);
  const running = job && (job.status === 'queued' || job.status === 'running');
  const [stopError, setStopError] = useState<string | null>(null);
  const total = job ? job.request.targets.length * job.request.per_target : 1;
  const cands = job?.candidates ?? [];
  const nBoth = cands.filter((c) => statusesOf(c).gap_window === 'both models').length;
  const nBalanced = cands.filter((c) => statusesOf(c).charge_balance === 'yes').length;
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head">
          <div className="micro"><Link to="/play">Generate</Link> · job {jobId}</div>
          <h1>{job ? `${job.request.targets.join(', ')} eV` : 'Generation job'}</h1>
          {job && <p>{job.request.per_target} structures per target · window {job.request.window_eV} eV · {job.request.require_anion ? 'anion required' : 'no anion requirement'} · excluded {job.request.exclude_elements.join(' ') || 'none'} · seed {job.request.seed} · model {job.request.model_id}</p>}
        </div>
        {error && <ErrorNote error={error} retry={retry} />}
        {!job && !error && <Spinner label="Loading the job" />}
        {job && (
          <>
            <div className="card" aria-live="polite">
              <div className="row" style={{ gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <b>{job.status}</b><span className="small muted">{job.progress.phase} · {job.progress.seconds.toFixed(0)} s · target {Math.min(job.progress.target_index + 1, job.progress.targets)} of {job.progress.targets} · {job.progress.attempts} draws · {job.progress.kept} kept</span>
                {running && <button type="button" className="btn btn-sm" onClick={() => { setStopError(null); research.stopJob(job.job_id).catch((e: Error) => setStopError(e.message)); }}>Stop</button>}
                {!running && <a className="btn btn-sm" href={research.zipUrl(job.job_id)}>Download everything (zip)</a>}
              </div>
              <div style={{ marginTop: 8 }}><Meter value={job.n_candidates} max={total} kind="info" /><span className="small muted">{job.n_candidates} of up to {total} structures kept so far</span></div>
              {job.notes.length > 0 && <ul className="small muted" style={{ margin: '8px 0 0 18px' }}>{job.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
              {stopError && <p className="error-text small" role="alert">{stopError}</p>}
              {job.error && <p className="error-text">{job.error}</p>}
              {running && job.log && job.log.length > 0 && <div className="progress-list" style={{ marginTop: 8 }}>{job.log.slice(-8).map((l, i) => <div key={i}>{l}</div>)}</div>}
            </div>

            {job.judge && (
              <p className="small muted" style={{ marginTop: 12 }}>
                Judge, a second model that played no part in generation: {job.judge.name}{job.judge.qualification ? ` — on the dataset's test split MAE ${Number(job.judge.qualification.mae_eV).toFixed(2)} eV, Spearman ${Number(job.judge.qualification.spearman).toFixed(2)} (n = ${job.judge.qualification.n})` : ''}. Both readings estimate the PBE band gap MP-20 records; PBE gaps are usually smaller than measured ones.
              </p>
            )}

            {cands.length > 0 && (
              <>
                <h2 style={{ marginTop: 20 }}>Structures</h2>
                <p className="small muted">
                  <b>{cands.length} kept</b> by the label read from the structure · <b>{nBoth}</b> with both models inside the window · <b>{nBalanced}</b> charge balanced · <b>0</b> relaxed and re-judged (not in the live run).
                  {job.funnel && <> {job.funnel.attempted} draws were made in all.</>} The three statuses are separate: a structure can pass the gap window and still be charge-unbalanced, and nothing here is relaxed.
                </p>
                <div className="cards-2" style={{ alignItems: 'start' }}>
                  <EvidenceMap cands={cands} window={job.request.window_eV} selected={open?.candidate_id ?? null} onOpen={(c) => setOpen(open?.candidate_id === c.candidate_id ? null : c)} />
                  {open ? (
                    <div className="card" role="dialog" aria-labelledby="gen-detail">
                      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <h3 id="gen-detail" style={{ margin: 0 }}>{open.formula} <span className="small faint mono">{open.candidate_id}</span></h3>
                        <button type="button" className="btn btn-ghost btn-sm" aria-label="Close" onClick={() => setOpen(null)}>✕</button>
                      </div>
                      {cell && <div style={{ maxWidth: 280, margin: '8px 0' }}><CellViewer structure={cell} size={280} title={open.formula} labels /></div>}
                      <dl className="kv small">
                        <dt>requested</dt><dd>{open.target_eV.toFixed(1)} eV</dd>
                        <dt>label from the structure</dt><dd><Num v={open.label_structure_eV} /> eV · {open.within_window.label ? 'inside' : 'outside'} the window</dd>
                        <dt>judge (second model)</dt><dd><Num v={open.judge_eV} /> eV · {open.within_window.judge ? 'inside' : 'outside'} the window{open.metal_by_judge ? ' · judged a metal' : ''}</dd>
                        <dt>gap window</dt><dd>{statusesOf(open).gap_window}</dd>
                        <dt>charge balanced</dt><dd>{statusesOf(open).charge_balance}</dd>
                        <dt>relaxed and re-judged</dt><dd>{statusesOf(open).relaxed}</dd>
                        <dt>formation energy label</dt><dd><Num v={open.label_formation_energy_eV_atom} /> eV/atom (model estimate, unrelaxed)</dd>
                        <dt>lattice</dt><dd className="mono">a {open.lattice.a} b {open.lattice.b} c {open.lattice.c} Å · α {open.lattice.alpha} β {open.lattice.beta} γ {open.lattice.gamma}° · {open.volume_per_atom} Å³/atom · space group {open.spacegroup}</dd>
                        {open.geometry && <><dt>geometry</dt><dd>closest atoms at <Num v={open.geometry.contact_ratio} /> of their radii (a sound crystal is near 1) · thickest empty layer <Num v={open.geometry.empty_layer_A} d={1} /> Å · packing <Num v={open.geometry.packing} />{open.geometry.contact_ratio < 0.6 && <span className="small" style={{ color: 'var(--warn)' }}> · under 0.6: relax before any use; in the MP-20 study two of three such cells collapsed when relaxed</span>}</dd></>}
                        <dt>known formula</dt><dd>{open.known_formula === null ? '—' : open.known_formula ? `yes, recorded ${open.recorded_gaps_eV.map((g) => g.toFixed(2)).join(', ')} eV` : 'not in MP-20'}{open.known_formula && open.recorded_gaps_eV.length > 0 && !open.recorded_gaps_eV.some((g) => Math.abs(g - open.target_eV) <= job.request.window_eV) && <span className="small" style={{ color: 'var(--warn)' }}> · every recorded gap of this formula lies outside your window: this cell is a different polymorph or the models disagree with the record</span>}</dd>
                        <dt>novelty</dt><dd><Num v={open.amd_nearest_reference} d={3} /> AMD to the nearest of the sampled MP-20 reference structures, of any composition{open.novel_by_amd ? ' · new above 0.3' : ''}</dd>
                        <dt>stability</dt><dd>{open.stability.status}: {open.stability.note}</dd>
                        <dt>sha256</dt><dd className="mono">{open.sha256}</dd>
                      </dl>
                      <a className="btn btn-sm btn-primary" href={research.cifUrl(job.job_id, open.candidate_id)} download>Download CIF</a>
                    </div>
                  ) : (
                    <div className="card"><h3>Pick a structure</h3><p className="small muted">Click a point on the plot or a card to see its cell, both readings and the three statuses. The evidence of every structure says what it is: a model's label read from the returned cell, a second model's reading, a charge-balance check, whether the formula exists in MP-20, and the distance to the nearest known structure.</p></div>
                  )}
                </div>

                <div className="row" style={{ justifyContent: 'space-between', marginTop: 16 }}>
                  <h3 style={{ margin: 0 }}>All structures</h3>
                  <Segmented value={view} label="View" options={[{ value: 'cards', label: 'Cards' }, { value: 'table', label: 'Table' }]} onChange={setView} />
                </div>
                {view === 'cards' ? (
                  <div className="ccards" style={{ marginTop: 8 }}>
                    {cands.map((c) => <CandidateCard key={c.candidate_id} c={c} selected={open?.candidate_id === c.candidate_id} onOpen={() => setOpen(open?.candidate_id === c.candidate_id ? null : c)} jobId={job.job_id} />)}
                  </div>
                ) : (
                  <div className="table-wrap" style={{ marginTop: 8 }}>
                    <table className="table">
                      <caption className="sr-only">Generated structures</caption>
                      <thead><tr><th scope="col">requested</th><th scope="col">formula</th><th scope="col">label from the structure</th><th scope="col">judge</th><th scope="col">gap window</th><th scope="col">charge balanced</th><th scope="col">relaxed</th><th scope="col">space group</th><th scope="col">atoms</th><th scope="col">formula in MP-20</th><th scope="col">AMD</th><th scope="col">cell</th></tr></thead>
                      <tbody>
                        {cands.map((c) => {
                          const st = statusesOf(c);
                          return (
                            <tr key={c.candidate_id} aria-selected={open?.candidate_id === c.candidate_id} onClick={() => setOpen(open?.candidate_id === c.candidate_id ? null : c)} style={{ cursor: 'pointer' }}>
                              <td className="num">{c.target_eV.toFixed(1)}</td><td><b>{c.formula}</b></td>
                              <td className="num"><Num v={c.label_structure_eV} /></td><td className="num"><Num v={c.judge_eV} />{c.metal_by_judge ? <span className="small faint"> metal</span> : null}</td>
                              <td>{st.gap_window}</td><td>{st.charge_balance}</td><td className="small">{st.relaxed}</td>
                              <td className="num">{c.spacegroup}</td><td className="num">{c.natoms}</td>
                              <td className="small">{c.known_formula === null ? '—' : c.known_formula ? `yes (${c.recorded_gaps_eV.map((g) => g.toFixed(2)).join(', ')} eV)` : 'no'}</td>
                              <td className="num"><Num v={c.amd_nearest_reference} d={3} />{c.novel_by_amd ? <span className="small faint"> new</span> : null}</td>
                              <td><a className="small" href={research.cifUrl(job.job_id, c.candidate_id)} download onClick={(e) => e.stopPropagation()}>CIF</a></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                <h3 style={{ marginTop: 20 }}>Relax locally, then judge again</h3>
                <p className="small muted">The server does not relax cells. Download the zip, then from its folder:</p>
                <div className="cmd">{job.relax_command}</div>
                <p className="small muted" style={{ marginTop: 6 }}>Then run both judges again on <code>relaxed_tensornet/</code> before quoting a band gap for the relaxed structure. Measured on MP-20, relaxation lowers the energy by whole electron-volts per atom and moves atoms by bond lengths; the relaxed cell is the product.</p>
              </>
            )}
            {!running && job.candidates && job.candidates.length === 0 && <p className="note" style={{ marginTop: 16 }}>No structure passed the structure-read label window for these targets. Above 3 eV the generator saturates on MP-20; try 1–3 eV, a wider window, or more structures per target.</p>}
            {job.per_target && job.per_target.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 16 }}>
                <table className="table"><thead><tr><th scope="col">requested</th><th scope="col">kept</th><th scope="col">both models in window</th><th scope="col">label mean</th><th scope="col">judge mean</th></tr></thead>
                  <tbody>{job.per_target.map((p) => <tr key={p.requested}><td className="num">{p.requested.toFixed(1)}</td><td className="num">{p.kept}</td><td className="num">{p.consensus}</td><td className="num"><Num v={p.label_mean_eV} /></td><td className="num"><Num v={p.judge_mean_eV} /></td></tr>)}</tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
