import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { api } from '@/api/endpoints';
import type { Family, Goal, GoalValidation, Kind, Objective, Project } from '@/api/types';
import { Histogram } from '@/components/charts/Histogram';
import { ErrorNote, Segmented, Site, Spinner } from '@/components/ui';
import { useFamily } from '@/features/project/useProject';
import { fmt, seconds, shortLabel } from '@/lib/format';
import { saveGoal } from '@/lib/goalStore';
import { PERIODIC_CELLS } from '@/lib/periodic';

const KINDS: Array<{ value: Kind | 'none'; label: string }> = [
  { value: 'value', label: 'Target value' }, { value: 'range', label: 'Range' }, { value: 'at_least', label: 'At least' }, { value: 'at_most', label: 'At most' },
  { value: 'maximize', label: 'Maximize' }, { value: 'minimize', label: 'Minimize' }, { value: 'none', label: 'Not targeted' },
];

function withDefaults(g: Goal): Required<Pick<Goal, 'elements' | 'budget' | 'rule_overrides' | 'disabled_rules' | 'novelty'>> & Goal {
  return {
    ...g,
    elements: g.elements ?? { exclude: [], only: {}, presets: [] },
    budget: g.budget ?? { per_target: 3, population: 24, rounds: 3, steps: 300, seed: 937, min_cosine_sep: 0.98 },
    rule_overrides: g.rule_overrides ?? {}, disabled_rules: g.disabled_rules ?? [], novelty: g.novelty ?? { require_not_in_dataset: false },
  };
}

export function GoalEditor({ project, initial }: { project: Project; initial: Goal }) {
  const navigate = useNavigate();
  const [goal, setGoal] = useState(() => withDefaults(initial));
  const [mode, setMode] = useState<'researcher' | 'advanced'>('researcher');
  const [validation, setValidation] = useState<GoalValidation | null>(null);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { data: family, error: famError } = useFamily(goal.family, goal.variant);
  const model = project.models.find((m) => m.model_id === (goal.model_id ?? project.default_model)) ?? project.models[0];
  const properties = project.dataset.properties;
  const timer = useRef<number | null>(null);

  useEffect(() => { saveGoal(project.project_id, goal); }, [goal, project.project_id]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const ctrl = new AbortController();
    setValidating(true);
    timer.current = window.setTimeout(() => {
      api.validate(goal, ctrl.signal).then((v) => { setValidation(v); setError(null); }).catch((e: Error) => { if (e.name !== 'AbortError') setError(e); }).finally(() => setValidating(false));
    }, 300);
    return () => { ctrl.abort(); if (timer.current) clearTimeout(timer.current); };
  }, [goal]);

  const errorsByLoc = useMemo(() => Object.fromEntries((validation?.errors ?? []).map((e) => [e.loc, e.msg])), [validation]);
  const update = (patch: Partial<Goal>) => setGoal((g) => withDefaults({ ...g, ...patch }));
  const objectiveOf = (p: string) => goal.objectives.find((o) => o.property === p);
  const setObjective = (p: string, next: Objective | null) => {
    const others = goal.objectives.filter((o) => o.property !== p);
    update({ objectives: next ? [...others, next].sort((a, b) => Object.keys(properties).indexOf(a.property) - Object.keys(properties).indexOf(b.property)) : others });
  };
  const toggleElement = (el: string) => {
    const ex = goal.elements.exclude.includes(el) ? goal.elements.exclude.filter((e) => e !== el) : [...goal.elements.exclude, el];
    update({ elements: { ...goal.elements, exclude: ex } });
  };
  const applyPreset = (k: string) => update({ elements: { ...goal.elements, presets: goal.elements.presets.includes(k) ? goal.elements.presets.filter((p) => p !== k) : [...goal.elements.presets, k] } });
  const presetElements = new Set((goal.elements.presets).flatMap((k) => family?.presets[k]?.elements ?? []));
  const ok = validation?.ok === true && !validating;

  return (
    <div className="goal-layout">
      <div className="stack" style={{ gap: 24 }}>
        <section className="card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}>Properties</h2>
            <Segmented value={mode} label="Editor mode" options={[{ value: 'researcher', label: 'Researcher' }, { value: 'advanced', label: 'Advanced' }]} onChange={setMode} />
          </div>
          <p className="muted small">What the candidate should satisfy. Each property of the model can be targeted, bounded, pushed to an extreme, or left out.</p>
          {Object.entries(properties).map(([pid, p]) => {
            const o = objectiveOf(pid);
            const idx = goal.objectives.findIndex((x) => x.property === pid);
            const span = p.max - p.min;
            const lo = Math.max(pid.includes('gap') ? 0 : -Infinity, p.min - 0.2 * span), hi = p.max + 0.2 * span;
            return (
              <div key={pid} className="rule-row" style={{ gridTemplateColumns: '1fr' }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <div><b>{p.label}</b> <span className="muted small">({p.unit})</span> <span className="faint small">training range {fmt(p.min)}–{fmt(p.max, p.unit)}{p.zero_share > 0.5 ? ` · ${Math.round(100 * p.zero_share)} % of training values are exactly 0` : ''}</span></div>
                  <select className="select" aria-label={`${p.label}: kind of target`} data-testid={`kind-${pid}`} value={o?.kind ?? 'none'}
                    onChange={(e) => {
                      const k = e.target.value as Kind | 'none';
                      if (k === 'none') { if (goal.objectives.length > 1) setObjective(pid, null); return; }
                      const base: Objective = { property: pid, kind: k, priority: o?.priority ?? (goal.objectives.length ? 'secondary' : 'primary') };
                      const mid = Number(((p.min + p.max) / 2).toPrecision(3));
                      if (k === 'value') setObjective(pid, { ...base, value: o?.value ?? mid, tolerance: o?.tolerance ?? Number((0.05 * span).toPrecision(2)) });
                      else if (k === 'range') setObjective(pid, { ...base, low: o?.low ?? Number((mid - 0.1 * span).toPrecision(3)), high: o?.high ?? Number((mid + 0.1 * span).toPrecision(3)) });
                      else if (k === 'at_least' || k === 'at_most') setObjective(pid, { ...base, value: o?.value ?? mid });
                      else setObjective(pid, base);
                    }}>
                    {KINDS.map((k) => <option key={k.value} value={k.value} disabled={k.value === 'none' && goal.objectives.length <= 1 && !!o}>{k.label}</option>)}
                  </select>
                </div>
                {o && (o.kind === 'value' || o.kind === 'at_least' || o.kind === 'at_most') && (
                  <div className="row" style={{ marginTop: 8 }}>
                    <label className="field"><span className="small muted">{o.kind === 'value' ? 'target' : o.kind === 'at_least' ? 'at least' : 'at most'}</span>
                      <input className="input input-num" type="number" step="any" data-testid={`target-${pid}`} value={o.value ?? ''} onChange={(e) => setObjective(pid, { ...o, value: Number(e.target.value) })} /></label>
                    {o.kind === 'value' && <label className="field"><span className="small muted">± tolerance</span>
                      <input className="input input-num" type="number" step="any" min={0} value={o.tolerance ?? ''} onChange={(e) => setObjective(pid, { ...o, tolerance: Number(e.target.value) })} /></label>}
                    <div style={{ flex: 1, minWidth: 180 }}>
                      <input type="range" aria-label={`${p.label} slider`} min={lo} max={hi} step={span / 200} value={o.value ?? p.mean} onChange={(e) => setObjective(pid, { ...o, value: Number(Number(e.target.value).toPrecision(3)) })} />
                      <div className="row small faint" style={{ justifyContent: 'space-between' }}><span>{fmt(lo)}</span><span>training range {fmt(p.min)}–{fmt(p.max)}</span><span>{fmt(hi)}</span></div>
                    </div>
                  </div>
                )}
                {o && o.kind === 'value' && o.value != null && p.histogram && (() => {
                  // the training distribution with the requested window, before anything runs: is there support where you are asking?
                  const zero = p.zero_share > 0.5 ? Math.round(p.zero_share * p.n) : null;
                  const hist = zero && p.nonzero ? p.nonzero.histogram : p.histogram;
                  const tol = o.tolerance ?? 0;
                  const inWindow = hist.counts.reduce((s, cnt, i) => (hist.edges[i + 1] >= o.value! - tol && hist.edges[i] <= o.value! + tol ? s + cnt : s), 0);
                  return (
                    <div style={{ marginTop: 8 }}>
                      <Histogram edges={hist.edges} counts={hist.counts} unit={p.unit} label={p.label} target={o.value} window={[o.value - tol, o.value + tol]} zeroCount={zero} zeroShare={zero ? p.zero_share : null} height={110} />
                      <div className="small muted">About {inWindow.toLocaleString()} training materials{zero ? ` with a non-zero ${p.label.toLowerCase()}` : ''} fall inside the requested window{zero ? `; ${Math.round(p.zero_share * 100)} % of all training values are exactly zero and are drawn apart` : ''}.</div>
                    </div>
                  );
                })()}
                {o && o.kind === 'range' && (
                  <div className="row" style={{ marginTop: 8 }}>
                    <label className="field"><span className="small muted">from</span><input className="input input-num" type="number" step="any" value={o.low ?? ''} onChange={(e) => setObjective(pid, { ...o, low: Number(e.target.value) })} /></label>
                    <label className="field"><span className="small muted">to</span><input className="input input-num" type="number" step="any" value={o.high ?? ''} onChange={(e) => setObjective(pid, { ...o, high: Number(e.target.value) })} /></label>
                  </div>
                )}
                {o && (o.kind === 'maximize' || o.kind === 'minimize') && <p className="small muted" style={{ marginTop: 6 }}>Run as a bound at the {o.kind === 'maximize' ? '99th' : '1st'} percentile of the training values; the readiness report shows the number.</p>}
                {o && mode === 'advanced' && (
                  <div className="row" style={{ marginTop: 8 }}>
                    <label className="field"><span className="small muted">priority</span>
                      <select className="select" value={o.priority ?? 'primary'} onChange={(e) => setObjective(pid, { ...o, priority: e.target.value as Objective['priority'] })}><option value="primary">primary</option><option value="secondary">secondary</option><option value="tertiary">tertiary</option></select></label>
                  </div>
                )}
                {idx >= 0 && errorsByLoc[`objectives.${idx}`] && <div className="error-text">{errorsByLoc[`objectives.${idx}`]}</div>}
                {Object.entries(errorsByLoc).filter(([k]) => k.startsWith(`objectives.${idx}.`)).map(([k, m]) => <div className="error-text" key={k}>{m}</div>)}
              </div>
            );
          })}
        </section>

        <section className="card">
          <h2>Family and elements</h2>
          <div className="row">
            <label className="field"><span className="small muted">family</span>
              <select className="select" value={goal.family} onChange={(e) => update({ family: e.target.value, variant: null, elements: { exclude: [], only: {}, presets: [] }, rule_overrides: {}, disabled_rules: [] })}>
                <option value="perovskite_abx3">Cubic ABX₃ perovskite</option><option value="double_perovskite_a2bbx6">Double perovskite A₂BB′X₆</option>
              </select></label>
            <label className="field"><span className="small muted">variant</span>
              <select className="select" value={goal.variant ?? family?.variant ?? ''} onChange={(e) => update({ variant: e.target.value, rule_overrides: {} })}>
                {Object.entries(family?.variants ?? {}).map(([v, d]) => <option key={v} value={v}>{v} — {d}</option>)}
              </select></label>
            {errorsByLoc.variant && <span className="error-text">{errorsByLoc.variant}</span>}
          </div>
          {famError && <ErrorNote error={famError} />}
          {family && (
            <>
              <p className="muted small" style={{ marginTop: 10 }}>{family.description} Click an element to exclude it. Site letters: {Object.entries(family.groups).map(([g, grp]) => <span key={g}><Site group={g} element={''} /> {grp.description}; </span>)}</p>
              <ElementGrid family={family} excluded={new Set(goal.elements.exclude)} presetExcluded={presetElements} onToggle={toggleElement} />
              <div className="row" style={{ marginTop: 10 }}>
                <span className="small muted">Presets:</span>
                {Object.entries(family.presets).map(([k, p]) => <button key={k} type="button" className="chip" aria-pressed={goal.elements.presets.includes(k)} style={goal.elements.presets.includes(k) ? { background: 'var(--bad-bg)', color: 'var(--bad)' } : undefined} onClick={() => applyPreset(k)} title={p.text}>{p.title}</button>)}
                {(goal.elements.exclude.length > 0 || goal.elements.presets.length > 0) && <button type="button" className="btn btn-ghost btn-sm" onClick={() => update({ elements: { exclude: [], only: {}, presets: [] } })}>Clear</button>}
              </div>
              {errorsByLoc['elements.exclude'] && <div className="error-text">{errorsByLoc['elements.exclude']}</div>}
            </>
          )}
        </section>

        {family && (
          <section className="card">
            <h2>Chemistry rules</h2>
            <p className="muted small">Each rule is evaluated on every decoded structure; a candidate must pass all of them. Limits can be changed; a rule can be switched off.</p>
            {family.constraints.filter((r) => r.rule !== 'symmetry_refinement').map((r) => {
              const off = goal.disabled_rules.includes(r.id);
              const ov = goal.rule_overrides[r.id] ?? {};
              return (
                <div key={r.id} className="rule-row">
                  <input type="checkbox" checked={!off} aria-label={`${r.title} enabled`} onChange={(e) => update({ disabled_rules: e.target.checked ? goal.disabled_rules.filter((x) => x !== r.id) : [...goal.disabled_rules, r.id] })} />
                  <div>
                    <b>{r.title}</b> <span className="muted small">{r.text}</span>
                    {Object.keys(r.numeric).length > 0 && !off && (
                      <div className="params">
                        {Object.entries(r.numeric).filter(([k]) => k !== 'cutoff').map(([k, v]) => (
                          <label className="field" key={k}><span className="small muted">{k}</span>
                            <input className="input input-num" type="number" step="any" value={ov[k] ?? v} onChange={(e) => {
                              const n = Number(e.target.value);
                              const next = { ...goal.rule_overrides, [r.id]: { ...ov, [k]: n } };
                              if (n === v) { delete next[r.id][k]; if (!Object.keys(next[r.id]).length) delete next[r.id]; }
                              update({ rule_overrides: next });
                            }} /></label>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div className="rule-row">
              <input type="checkbox" checked={goal.novelty.require_not_in_dataset} onChange={(e) => update({ novelty: { require_not_in_dataset: e.target.checked } })} aria-label="Flag candidates found in the dataset" />
              <div><b>Novelty check</b> <span className="muted small">Every candidate is checked against the dataset by reduced formula and by A|B|X site assignment; with this on, those found are kept and marked.</span></div>
            </div>
            <div className="rule-row">
              <input type="checkbox" disabled aria-label="Stability screen (not available in this version)" />
              <div><b>Stability screen</b> <span className="muted small">Relaxation with a machine-learned potential. Not available in this version; every candidate carries the stage "Not screened".</span></div>
            </div>
          </section>
        )}

        <section className="card">
          <h2>Model</h2>
          {project.models.map((m) => (
            <label key={m.model_id} className="row" style={{ alignItems: 'flex-start', gap: 10, padding: '8px 0' }}>
              <input type="radio" name="model" checked={(goal.model_id ?? project.default_model) === m.model_id} onChange={() => update({ model_id: m.model_id })} disabled={!m.available} />
              <div>
                <b>{m.description}</b>
                <div className="small muted">Trained on {m.training_rows.toLocaleString()} materials ({m.trained_on === 'all' ? 'the whole dataset' : 'the training split'}); properties {m.properties.map((p) => p.label).join(', ')}; latent {m.latent_dim}; up to {m.max_sites} sites.</div>
                {m.caveats.map((c) => <div className="small" key={c} style={{ color: 'var(--warn)' }}>{c}</div>)}
                {!m.available && <div className="small error-text">The model file is not present on this server.</div>}
              </div>
            </label>
          ))}
          {mode === 'advanced' && (
            <div className="row" style={{ marginTop: 10 }}>
              {(['per_target', 'population', 'rounds', 'steps', 'seed', 'min_cosine_sep'] as const).map((k) => (
                <label className="field" key={k}><span className="small muted">{k.replace('_', ' ')}</span>
                  <input className="input input-num" type="number" step={k === 'min_cosine_sep' ? 0.005 : 1} value={goal.budget[k]} onChange={(e) => update({ budget: { ...goal.budget, [k]: Number(e.target.value) } })} /></label>
              ))}
              {project.limits && <span className="small muted">Limits on this shared server: {Object.entries(project.limits).map(([k, v]) => `${k} ≤ ${v}`).join(', ')}.</span>}
            </div>
          )}
          {Object.entries(errorsByLoc).filter(([k]) => k.startsWith('budget')).map(([k, m]) => <div className="error-text" key={k}>{k}: {m}</div>)}
        </section>
      </div>

      <aside className="goal-summary card" aria-label="Goal summary">
        <div className="micro">Design request</div>
        <div className="mono" style={{ margin: '8px 0 12px', fontSize: 15 }} data-testid="goal-summary">{validation?.summary ?? '…'}</div>
        {validating && <Spinner label="Checking" />}
        {validation && !validation.ok && <div className="banner banner-bad small">{validation.message}{validation.errors?.map((e) => <div key={e.loc}><code>{e.loc}</code> — {e.msg}</div>)}</div>}
        {validation?.ok && (
          <div className="stack small">
            {validation.targets_explained?.map((s) => <div key={s} className="muted">{s}</div>)}
            {validation.notes?.map((n) => <div key={n} style={{ color: 'var(--warn)' }}>{n}</div>)}
            <div>Estimated search time: <b className="num">{seconds(validation.estimated_seconds ?? 0)}</b> on this server; {validation.generation?.targets.length} target{(validation.generation?.targets.length ?? 1) > 1 ? 's' : ''}, {model?.description ? 'published model' : ''}.</div>
          </div>
        )}
        <ErrorNote error={error} />
        <div className="row" style={{ marginTop: 14 }}>
          <button type="button" className="btn btn-primary" data-testid="check-readiness" disabled={!ok} onClick={() => { saveGoal(project.project_id, goal); navigate(`/p/${project.project_id}/readiness`); }}>Check readiness →</button>
        </div>
        <p className="faint small" style={{ marginTop: 10 }}>Properties: {Object.values(properties).map((p) => shortLabel(p.label)).join(', ')}. The readiness report comes before any search runs.</p>
      </aside>
    </div>
  );
}

function ElementGrid({ family, excluded, presetExcluded, onToggle }: { family: Family; excluded: Set<string>; presetExcluded: Set<string>; onToggle: (el: string) => void }) {
  const allowed = new Map<string, string[]>();
  for (const [g, grp] of Object.entries(family.groups)) for (const el of grp.elements) allowed.set(el, [...(allowed.get(el) ?? []), g]);
  const present = new Set(Object.values(family.groups).flatMap((g) => g.coverage.present));
  return (
    <div className="ptable" role="group" aria-label="Elements of the family: click to exclude">
      {PERIODIC_CELLS.map(({ symbol, row, col }) => {
        if (!symbol) return <span key={`${row}-${col}`} />;
        const groups = allowed.get(symbol);
        if (!groups) return <button key={symbol} type="button" disabled aria-hidden="true" tabIndex={-1}>{symbol}</button>;
        const ox = family.groups[groups[0]].oxidation_states[symbol] ?? [];
        const off = excluded.has(symbol) || presetExcluded.has(symbol);
        return (
          <button key={symbol} type="button" aria-pressed={off} data-testid={`el-${symbol}`} onClick={() => onToggle(symbol)}
            title={`${symbol}: site ${groups.join('/')}${ox.length ? `, charges ${ox.map((q) => (q > 0 ? `+${q}` : q)).join('/')}` : ''}${present.has(symbol) ? '' : ' — not in the training data'}${off ? ' (excluded)' : ''}`}
            style={present.has(symbol) ? undefined : { borderStyle: 'dashed', opacity: 0.75 }}>
            <span className="dots" aria-hidden="true">{groups.map((g) => <i key={g} style={{ background: `var(--site-${g})` }} />)}</span>
            {symbol}<small>{ox.map((q) => (q > 0 ? `+${q}` : q)).join('/')}</small>
          </button>
        );
      })}
    </div>
  );
}
