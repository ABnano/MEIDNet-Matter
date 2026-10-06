import { useState } from 'react';
import { Link } from 'react-router';
import { api } from '@/api/endpoints';
import type { Candidate } from '@/api/types';
import { ExternalLink, PRISM_METHOD } from '@/components/shell';
import { CellViewer } from '@/components/structure/CellViewer';
import { DomainBadge, Site } from '@/components/ui';
import { fmt, shortLabel, signed } from '@/lib/format';
import { candidateStructure } from './components';

export function CandidateDetail({ c, projectId, variant, onClose, compared, onCompare }: { c: Candidate; projectId: string; variant: 'drawer' | 'page'; onClose?: () => void; compared?: boolean; onCompare?: () => void }) {
  const [supercell, setSupercell] = useState(1);
  const [labels, setLabels] = useState(true);
  const [viewKey, setViewKey] = useState(0);
  const run = c.run_id;
  if (!c.properties) return <div className="card"><p>This candidate could not be enriched: {c.enrichment_error}</p></div>;
  const props = Object.entries(c.properties);
  const ev = c.model_evidence;
  return (
    <div className={variant === 'drawer' ? 'card drawer' : 'stack'} role={variant === 'drawer' ? 'dialog' : undefined} aria-labelledby={`cand-${c.candidate_id}`} data-testid="candidate-detail">
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 id={`cand-${c.candidate_id}`} style={{ margin: 0 }}>{c.identity.formula}</h2>
          <div className="row" style={{ gap: 6, marginTop: 4 }}>{Object.entries(c.identity.elements).map(([g, e]) => <Site key={g} group={g} element={e} />)}<span className="small num faint">a = {fmt(c.structure.lattice_a)} Å</span></div>
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            <DomainBadge status={c.domain.status} word={c.domain.word} />
            <span className={`badge ${c.novelty.dataset.found ? 'badge-neutral' : 'badge-info'}`}>{c.novelty.dataset.found ? 'Found in the dataset' : 'Not found in the dataset'}</span>
            <span className="badge badge-neutral">{c.stability.status}</span>
            {c.mode === 'exploratory' && <span className="badge badge-warn">Exploratory run</span>}
          </div>
        </div>
        {variant === 'drawer' && onClose && <button type="button" className="btn btn-ghost btn-sm" aria-label="Close" onClick={onClose}>✕</button>}
      </header>

      <div className="row" style={{ gap: 6, margin: '12px 0' }}>
        <a className="btn btn-sm btn-primary" href={api.urls.cif(run, c.candidate_id)} download data-testid="download-cif">Download CIF</a>
        {onCompare && <button type="button" className="btn btn-sm" aria-pressed={compared} onClick={onCompare}>{compared ? 'Remove from comparison' : 'Add to comparison'}</button>}
        <a className="btn btn-sm" href={api.urls.record(run, c.candidate_id)} download>Export candidate record</a>
        <Link className="btn btn-sm" to={`/p/${projectId}/runs/${run}/export`}>Prepare validation</Link>
        <ExternalLink className="btn btn-sm btn-ghost" href={PRISM_METHOD}>Open method in Prism ↗</ExternalLink>
        {variant === 'drawer' && <Link className="btn btn-sm btn-ghost" to={`/p/${projectId}/runs/${run}/c/${c.candidate_id}`}>Full page</Link>}
      </div>

      <section>
        <div style={{ maxWidth: variant === 'page' ? 360 : 300 }}><CellViewer key={viewKey} structure={candidateStructure(c)} size={300} title={c.identity.formula} labels={labels} supercell={supercell} /></div>
        <div className="row small" style={{ gap: 6, marginTop: 6 }}>
          <button type="button" className="btn btn-sm" onClick={() => setViewKey((k) => k + 1)}>Reset view</button>
          <span className="muted">Supercell</span>
          {[1, 2, 3].map((n) => <button key={n} type="button" className="btn btn-sm" aria-pressed={supercell === n} style={supercell === n ? { borderColor: 'var(--p1)' } : undefined} onClick={() => setSupercell(n)}>{n}×{n}×{n}</button>)}
          <button type="button" className="btn btn-sm" aria-pressed={labels} onClick={() => setLabels((l) => !l)}>Labels</button>
          <span className="faint">drag to rotate · double-click to spin · arrow keys</span>
        </div>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>Properties</h3>
        <table className="table small">
          <thead><tr><th>Property</th><th className="num">Target</th><th className="num">Predicted</th><th className="num">Difference</th><th>Uncertainty</th><th>Training range</th><th>Status</th></tr></thead>
          <tbody>{props.map(([k, p]) => (
            <tr key={k}>
              <td>{p.label} <span className="faint">({p.unit})</span></td><td className="num">{p.target != null ? fmt(p.target) : '—'}</td><td className="num"><b>{fmt(p.predicted)}</b> <span className="faint">{p.evidence_label}</span></td>
              <td className="num">{signed(p.difference)}</td><td className="faint">{p.uncertainty != null ? fmt(p.uncertainty) : p.uncertainty_note}</td><td className="num">{fmt(p.training_range[0])}–{fmt(p.training_range[1])}</td>
              <td><DomainBadge status={p.domain.status} word={p.domain.word} /></td>
            </tr>
          ))}</tbody>
        </table>
        {props.map(([k, p]) => <p key={k} className="small muted" style={{ margin: '4px 0' }}>{p.label}: {p.domain.reason}{p.dft_value != null && <> {p.dft_label}: <b className="num">{fmt(p.dft_value, p.unit)}</b>.</>}</p>)}
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>Chemistry rules <span className="muted small">{c.rules_passed} of {c.rules_total} passed</span></h3>
        <ul className="checklist">
          {c.constraints.map((r) => (
            <li key={r.id} className={r.passed ? 'ok' : 'fail'}>
              <span className="mark" aria-hidden="true">{r.passed ? '✓' : '✗'}</span>
              <span><b>{r.evidence_label}</b> · {r.title}{r.value != null && <span className="num"> = {fmt(r.value)}</span>}{r.window && (r.window[0] != null || r.window[1] != null) && <span className="muted num"> · window {r.window[0] != null ? fmt(r.window[0]) : '…'}–{r.window[1] != null ? fmt(r.window[1]) : '…'}</span>}{r.detail && r.rule === 'charge_neutrality' && <span className="muted"> — {r.detail}</span>}
                <div className="faint small">{r.text}</div></span>
            </li>
          ))}
        </ul>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>Model evidence</h3>
        <dl className="kv small">
          {Object.entries(ev.agreement).map(([k, a]) => <><dt key={`${k}-t`}>Encoder vs search, {shortLabel(c.properties[k].label)}</dt><dd key={`${k}-d`}>encoder {fmt(a.encoder, c.properties[k].unit)} · search {fmt(a.decoder, c.properties[k].unit)} · <b>{a.label}</b>{a.in_std != null && <span className="faint"> ({a.in_std.toFixed(2)} spreads apart)</span>}</dd></>)}
          <dt>Nearest training materials</dt>
          <dd>{ev.nearest_training.length ? ev.nearest_training.map((n) => <div key={n.material_id}><b>{n.formula}</b> <span className="num">cos {n.cosine.toFixed(3)}</span> · {Object.entries(n.properties).map(([k, v]) => `${shortLabel(c.properties[k]?.label ?? k)} ${fmt(v)}`).join(', ')} <span className="faint">{n.evidence_label}</span></div>) : 'not available for this model'}</dd>
          <dt>Latent distance to the nearest</dt><dd className="num">{ev.latent_distance != null ? ev.latent_distance.toFixed(3) : '—'}</dd>
          <dt>Latent norm</dt><dd className="num">{fmt(ev.latent_norm)}{ev.latent_hit_clip && <span className="badge badge-warn" style={{ marginLeft: 6 }}>hit the search limit</span>}</dd>
          <dt>Training data around the prediction</dt><dd><b className="num">{ev.local_density.n_within}</b> training materials within the window ({(100 * ev.local_density.fraction).toFixed(2)} %)</dd>
          <dt>Search score</dt><dd className="num">{ev.score?.toExponential(3)}</dd>
        </dl>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>Novelty</h3>
        <p className="small">{c.novelty.dataset.label}. {c.novelty.training_split.label}. <span className="faint">Method: {c.novelty.method}.</span></p>
        <h3>Stability</h3>
        <div className="row small" style={{ gap: 4 }}>{c.stability.stages.map((s) => <span key={s} className={`badge ${s === c.stability.status ? 'badge-info' : 'badge-neutral'}`}>{s}</span>)}</div>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>Why this candidate?</h3>
        <p className="small">{c.why}</p>
        {c.flags.length > 0 && <div className="banner banner-warn small">{c.flags.join(' · ')}</div>}
      </section>
    </div>
  );
}
