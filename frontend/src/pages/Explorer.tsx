import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { api } from '@/api/endpoints';
import { useResource, useRunPolling } from '@/api/hooks';
import type { DomainStatus, Run } from '@/api/types';
import { ErrorNote, Segmented, Spinner } from '@/components/ui';
import { CandidateDetail } from '@/features/candidates/CandidateDetail';
import { CandidateCard, CandidateMap, CandidateTable, COLUMNS, DEFAULT_COLS, ExportMenu, groupByCluster, SearchFunnel } from '@/features/candidates/components';
import { chips, DEFAULTS, filterCandidates, parseQuery, serializeQuery, sortCandidates, SORTS, type ExplorerQuery } from '@/features/candidates/explorerQuery';
import { useProject } from '@/features/project/useProject';
import { fmt, seconds, shortLabel } from '@/lib/format';

const DOMAINS: Array<{ value: DomainStatus; label: string }> = [
  { value: 'in_distribution', label: 'Interpolating' }, { value: 'near_boundary', label: 'Boundary' }, { value: 'extrapolating', label: 'Extrapolating' }, { value: 'far_outside', label: 'Far outside' },
];

export default function Explorer() {
  const { projectId = 'perov5-demo', runId = '' } = useParams();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const q = useMemo(() => parseQuery(sp), [sp]);
  const setQ = (f: (q: ExplorerQuery) => ExplorerQuery) => setSp(serializeQuery(f(parseQuery(sp))), { replace: true });
  const { data: project } = useProject(projectId);
  const { status, error, retry } = useRunPolling(runId);
  const finished = status && status.status !== 'queued' && status.status !== 'running';
  const { data: full } = useResource(finished ? `run:${runId}:${status?.status}` : null, (signal) => api.run(runId, signal));
  const { data: dataset } = useResource(q.view === 'map' ? `dataset:${projectId}` : null, () => api.dataset(projectId));
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  useEffect(() => { if (window.innerWidth < 900 && q.view === 'table' && !sp.has('view')) setQ((x) => ({ ...x, view: 'cards' })); /* eslint-disable-line react-hooks/exhaustive-deps */ }, []);

  if (error) return <ErrorNote error={error} retry={retry} />;
  if (!status || !project) return <Spinner label="Loading the run" />;
  const all = status.candidates;
  const labels = Object.fromEntries(Object.entries(project.dataset.properties).map(([k, p]) => [k, shortLabel(p.label)]));
  const shown = sortCandidates(filterCandidates(all, q), q.sort);
  const selected = q.c ? all.find((c) => c.candidate_id === q.c) ?? null : null;
  const run = full as Run | null;
  const windows = (run?.readiness.windows ?? {}) as Record<string, [number | null, number | null]>;
  const toggleCmp = (id: string) => setQ((x) => ({ ...x, cmp: x.cmp.includes(id) ? x.cmp.filter((y) => y !== id) : x.cmp.length < 6 ? [...x.cmp, id] : x.cmp }));
  const open = (id: string) => setQ((x) => ({ ...x, c: x.c === id ? null : id }));
  const running = status.status === 'queued' || status.status === 'running';
  const p = status.progress;
  const progressPct = p.targets ? Math.min(100, (100 * ((p.target - 1) * p.rounds * p.steps + (p.round - 1) * p.steps + p.step)) / Math.max(1, p.targets * p.rounds * p.steps)) : 0;
  const activeChips = chips(q, labels);
  const hasClusters = all.some((c) => !!c.cluster);
  const nClusters = run?.clusters?.length ?? new Set(all.map((c) => c.cluster?.id).filter((x) => x != null)).size;
  const stages = all[0]?.stability?.stages ?? [];
  const stageCounts = stages.map((label, i) => [label, all.filter((c) => (c.stability?.stage ?? 0) === i).length, i] as const).filter(([, n_]) => n_ > 0);
  const card = (c: (typeof all)[number]) => <CandidateCard key={c.candidate_id} c={c} projectId={projectId} selected={q.c === c.candidate_id} compared={q.cmp.includes(c.candidate_id)} onOpen={() => open(c.candidate_id)} onCompare={() => toggleCmp(c.candidate_id)} />;

  return (
    <>
      <div className="querybar" data-testid="querybar">
        <span className="micro">Design request</span>
        <span className="q">{status.summary}</span>
        <Link to={`/p/${projectId}/goal`} className="btn btn-sm">Edit goal</Link>
        <ExportMenu runId={runId} candidateCount={all.length} />
      </div>

      {status.mode === 'exploratory' && <div className="banner banner-warn" style={{ marginBottom: 12 }} data-testid="exploratory-banner">Exploratory run — the readiness report did not support this target. Treat the predicted values as unreliable; the chemistry rules still apply.</div>}
      {run?.readiness.search_advice && <div className="banner banner-info small" style={{ marginBottom: 12 }}>One property target, many possible structures: the candidates below are alternatives, not a ranking of one answer.{hasClusters && nClusters > 0 && <> They fall into {nClusters} cluster{nClusters === 1 ? '' : 's'} of similar encoder latents (cosine ≥ 0.9); choose what to prioritise with the control on the right.</>}</div>}

      {running && (
        <div className="card card-tight" style={{ marginBottom: 12 }} role="status" aria-live="polite">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span><span className="spinner" aria-hidden="true" /> Searching — target {p.target || 1} of {p.targets} · round {p.round} of {p.rounds} · step {p.step} of {p.steps}{p.loss != null && <span className="faint num"> · loss {p.loss.toExponential(2)}</span>} · {seconds(p.seconds)} of about {seconds(status.estimated_seconds)}</span>
            <button type="button" className="btn btn-sm btn-danger" disabled={stopping} onClick={async () => { setStopping(true); setStopError(null); try { await api.stop(runId); } catch (e) { setStopping(false); setStopError((e as Error).message); } }}>Stop</button>
          </div>
          {stopError && <p className="error-text small" role="alert">{stopError}</p>}
          <div className="progress" role="progressbar" aria-valuenow={Math.round(progressPct)} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${progressPct}%` }} /></div>
          {status.notes.map((n) => <div key={n} className="small muted" style={{ marginTop: 4 }}>{n}</div>)}
        </div>
      )}
      {status.status === 'error' && <ErrorNote error={new Error(status.error ?? 'the search failed')} />}
      {status.status === 'stopped' && <div className="banner banner-info small" style={{ marginBottom: 12 }}>Stopped early; what was found is kept.</div>}

      <div className="results-head">
        <h2 data-testid="results-count">{shown.length === all.length ? `${all.length} candidate${all.length === 1 ? '' : 's'}` : `${shown.length} of ${all.length} candidates`} {running ? 'so far' : 'passed the search filters'}
          {!running && all.some((c) => c.support) && <span className="muted" style={{ fontWeight: 400 }}> · {all.filter((c) => c.support?.structure_supported).length} supported by the structure-based prediction</span>}</h2>
        {activeChips.map((ch) => <span key={ch.key} className="chip">{ch.text}<button type="button" aria-label={`Remove filter: ${ch.text}`} onClick={() => setQ(ch.remove)}>✕</button></span>)}
        {activeChips.length > 0 && <button type="button" className="btn btn-ghost btn-sm" onClick={() => setQ((x) => ({ ...DEFAULTS, view: x.view, sort: x.sort, c: x.c, cmp: x.cmp, cols: x.cols }))}>Reset filters</button>}
        <span style={{ marginLeft: 'auto' }} className="row">
          <Segmented value={q.view} label="View" options={[{ value: 'table', label: 'Table' }, { value: 'cards', label: 'Cards' }, { value: 'map', label: 'Map' }]} onChange={(v) => setQ((x) => ({ ...x, view: v }))} />
          <label className="row small" style={{ gap: 6 }}><span className="micro">Prioritise</span>
            <select className="select" aria-label="Prioritise" data-testid="prioritise" value={q.sort} onChange={(e) => setQ((x) => ({ ...x, sort: e.target.value as ExplorerQuery['sort'] }))}>{SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
          </label>
          {q.view === 'table' && (
            <details style={{ position: 'relative' }}>
              <summary className="btn btn-sm" style={{ listStyle: 'none', cursor: 'pointer' }}>Columns</summary>
              <div className="card card-tight stack" style={{ position: 'absolute', right: 0, zIndex: 10, minWidth: 220, gap: 4 }}>
                {COLUMNS.filter((c) => !c.always).map((c) => <label key={c.id} className="row small"><input type="checkbox" checked={(q.cols ?? DEFAULT_COLS).includes(c.id)} onChange={(e) => setQ((x) => { const cols = new Set(x.cols ?? DEFAULT_COLS); if (e.target.checked) cols.add(c.id); else cols.delete(c.id); return { ...x, cols: [...cols] }; })} />{c.label}</label>)}
              </div>
            </details>
          )}
        </span>
      </div>

      <div className={`explorer ${selected ? 'with-drawer' : ''}`}>
        <aside className="filters" aria-label="Filters">
          <fieldset><legend>Deviation from the target</legend>
            {Object.entries(project.dataset.properties).map(([k, pr]) => {
              const span = pr.max - pr.min; const max = q.dev[k] ?? span;
              return <label key={k} className="opt" style={{ display: 'block' }}>|Δ {shortLabel(pr.label)}| ≤ <b className="num">{fmt(max, pr.unit)}</b>
                <input type="range" min={0} max={span} step={span / 100} value={max} onChange={(e) => setQ((x) => ({ ...x, dev: { ...x.dev, [k]: Number(Number(e.target.value).toPrecision(3)) } }))} /></label>;
            })}
          </fieldset>
          <fieldset><legend>Domain status</legend>{DOMAINS.map((d) => <label key={d.value} className="opt"><input type="checkbox" checked={q.domain.includes(d.value)} onChange={(e) => setQ((x) => ({ ...x, domain: e.target.checked ? [...x.domain, d.value] : x.domain.filter((y) => y !== d.value) }))} />{d.label}</label>)}</fieldset>
          <fieldset><legend>Elements</legend>
            <ElementInput label="Contains" values={q.el} onChange={(v) => setQ((x) => ({ ...x, el: v }))} />
            <ElementInput label="Excludes" values={q.xel} onChange={(v) => setQ((x) => ({ ...x, xel: v }))} />
          </fieldset>
          <fieldset><legend>Chemistry rules</legend><label className="opt"><input type="radio" name="rules" checked={q.rules === 'any'} onChange={() => setQ((x) => ({ ...x, rules: 'any' }))} />Any</label><label className="opt"><input type="radio" name="rules" checked={q.rules === 'passed'} onChange={() => setQ((x) => ({ ...x, rules: 'passed' }))} />All rules passed</label></fieldset>
          <fieldset><legend>Novelty</legend>
            {([['not_found', 'Not found in the dataset'], ['found', 'Found in the dataset']] as const).map(([v, l]) => <label key={v} className="opt"><input type="checkbox" checked={q.novelty.includes(v)} onChange={(e) => setQ((x) => ({ ...x, novelty: e.target.checked ? [...x.novelty, v] : x.novelty.filter((y) => y !== v) }))} />{l}</label>)}
          </fieldset>
          <fieldset><legend>Validation stage</legend>
            {stageCounts.map(([label, n_, i]) => <div key={label} className="opt small">Stage {i} · {label} <b className="num">{n_}</b></div>)}
            {stageCounts.length === 0 && <div className="opt small faint">—</div>}
            <span className="small faint">Later stages (MLIP, DFT, experiment) are your own steps; the export page says how.</span>
          </fieldset>
        </aside>

        <div className="stack" style={{ gap: 20 }}>
          {all.length === 0 && !running && <div className="card"><p>No candidate was retained. {run?.funnel ? 'The funnel below shows where the attempts were rejected.' : ''}</p><Link to={`/p/${projectId}/goal`} className="btn">Adjust the goal</Link></div>}
          {all.length > 0 && shown.length === 0 && <div className="card"><p>No candidates match the current filters — reset the filters or widen the deviation.</p></div>}
          {shown.length > 0 && q.view === 'table' && <CandidateTable cands={shown} q={q} setQ={setQ} onOpen={open} />}
          {shown.length > 0 && q.view === 'cards' && !hasClusters && <div className="cards-2" data-testid="candidates-cards">{shown.map(card)}</div>}
          {shown.length > 0 && q.view === 'cards' && hasClusters && (
            <div className="stack" data-testid="candidates-cards" style={{ gap: 14 }}>
              {groupByCluster(shown).map((g) => (
                <section key={g.id} data-testid="cluster-group">
                  <div className="small muted" style={{ margin: '0 0 8px' }}><b>Cluster {g.id || '—'}</b> · {g.cands.length} of {g.size || g.cands.length} candidate{g.size === 1 ? '' : 's'} near {g.leaderFormula} <span className="faint">(encoder latents within cosine 0.9; alternatives for the same target)</span></div>
                  <div className="cards-2">{g.cands.map(card)}</div>
                </section>
              ))}
            </div>
          )}
          {shown.length > 0 && q.view === 'map' && <CandidateMap cands={shown} project={project} dataset={dataset ?? null} windows={windows} selected={q.c} onOpen={open} />}
          {run?.funnel && <SearchFunnel funnel={run.funnel} />}
        </div>

        {selected && <CandidateDetail c={selected} projectId={projectId} variant="drawer" onClose={() => setQ((x) => ({ ...x, c: null }))} compared={q.cmp.includes(selected.candidate_id)} onCompare={() => toggleCmp(selected.candidate_id)} />}
      </div>

      {q.cmp.length > 0 && (
        <div className="tray" data-testid="compare-tray">
          <div className="wrap">
            <b>Compare ({q.cmp.length})</b>
            {q.cmp.map((id) => { const c = all.find((x) => x.candidate_id === id); return <span key={id} className="chip">{c?.identity.formula ?? id}<button type="button" aria-label={`Remove ${c?.identity.formula ?? id} from comparison`} onClick={() => toggleCmp(id)}>✕</button></span>; })}
            <button type="button" className="btn btn-primary btn-sm" disabled={q.cmp.length < 2} onClick={() => navigate(`/p/${projectId}/runs/${runId}/compare?ids=${q.cmp.join(',')}`)}>Compare side by side</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setQ((x) => ({ ...x, cmp: [] }))}>Clear</button>
          </div>
        </div>
      )}
    </>
  );
}

function ElementInput({ label, values, onChange }: { label: string; values: string[]; onChange: (v: string[]) => void }) {
  const [text, setText] = useState('');
  return (
    <div className="field" style={{ marginBottom: 6 }}>
      <label>{label}</label>
      <div className="row" style={{ gap: 4 }}>
        {values.map((v) => <span key={v} className="chip">{v}<button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}>✕</button></span>)}
        <input className="input" style={{ width: 70 }} placeholder="Sn" value={text} aria-label={`${label} element`} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && text.trim()) { const el = text.trim()[0].toUpperCase() + text.trim().slice(1).toLowerCase(); if (!values.includes(el)) onChange([...values, el]); setText(''); } }} />
      </div>
    </div>
  );
}
