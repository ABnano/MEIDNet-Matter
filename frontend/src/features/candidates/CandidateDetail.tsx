import { useState } from 'react';
import { Link } from 'react-router';
import { api } from '@/api/endpoints';
import { shownDomain, type Candidate } from '@/api/types';
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
            <span className="badge badge-neutral">{c.stability.label ?? c.stability.status}</span>
            {c.cluster && <span className="badge badge-neutral" title={`${c.cluster.size} candidates share this cluster (encoder latents within cosine 0.9 of ${c.cluster.leader})`}>Cluster {c.cluster.id} · {c.cluster.rank}/{c.cluster.size}</span>}
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
        {c.support && <p className="small" style={{ margin: '0 0 8px', color: c.support.structure_supported === false ? 'var(--warn)' : 'var(--muted)' }}><b>{c.support.label}.</b> The search value is what kept the candidate; only the structure-based prediction, and a DFT value where the dataset has one, can support the target.</p>}
        <table className="table small">
          <thead><tr><th>Property</th><th className="num">Target</th><th className="num" title="The decoded structure, encoded again and read by the model">Structure-based</th><th className="num">Difference</th><th className="num" title="The property head read at the search point">Search value</th><th className="num">DFT (dataset)</th><th>Training range</th><th>Status</th></tr></thead>
          <tbody>{props.map(([k, p]) => (
            <tr key={k}>
              <td>{p.label} <span className="faint">({p.unit})</span></td><td className="num">{p.target != null ? fmt(p.target) : '—'}</td>
              <td className="num"><b>{p.structure_predicted != null ? fmt(p.structure_predicted) : '—'}</b>{p.structure_in_window != null && <span className="faint small"> {p.structure_in_window ? 'in window' : 'outside'}</span>}</td>
              <td className="num">{signed(p.structure_predicted != null ? p.structure_difference ?? null : p.difference)}</td>
              <td className="num muted">{fmt(p.predicted)}{p.in_window != null && <span className="faint small"> {p.in_window ? 'in window' : 'outside'}</span>}</td>
              <td className="num">{p.dft_value != null ? fmt(p.dft_value) : '—'}</td>
              <td className="num">{fmt(p.training_range[0])}–{fmt(p.training_range[1])}</td>
              <td><DomainBadge status={shownDomain(p).status} word={shownDomain(p).word} /></td>
            </tr>
          ))}</tbody>
        </table>
        {props.map(([k, p]) => <p key={k} className="small muted" style={{ margin: '4px 0' }}>{p.label}, {p.structure_predicted != null ? 'structure-based prediction' : 'search value'}: {shownDomain(p).reason}{p.dft_value != null && <> {p.dft_label}: <b className="num">{fmt(p.dft_value, p.unit)}</b>.</>}</p>)}
        <p className="small faint" style={{ margin: '4px 0' }}>Uncertainty: {props[0]?.[1].uncertainty_note ?? 'not available for this model'}.</p>
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
        <h3>Validation ladder</h3>
        <div className="row small" style={{ gap: 4 }} data-testid="ladder">{c.stability.stages.map((s, i) => <span key={s} className={`badge ${i <= c.stability.stage ? 'badge-info' : 'badge-neutral'}`} title={i <= c.stability.stage ? 'reached' : 'not reached'}>{i} · {s}</span>)}</div>
        <ul className="small muted" style={{ margin: '6px 0 0 18px' }}>
          {c.stability.records.map((r) => <li key={r.stage}>Stage {r.stage} · {r.label}: {r.outcome} ({r.method}){r.passed === false ? ' — not passed' : ''}</li>)}
          {c.stability.next && <li>Next: {c.stability.next} — your own screening, DFT or experiment; the run bundle has the CIFs and targets.csv.</li>}
        </ul>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>Why this candidate?</h3>
        <p className="small">{c.why}</p>
        {c.flags.length > 0 && <div className="banner banner-warn small">{c.flags.join(' · ')}</div>}
      </section>
    </div>
  );
}
