import type { Indicator, Project, Readiness } from '@/api/types';
import { Histogram } from '@/components/charts/Histogram';
import { Meter, StatusBadge } from '@/components/ui';
import { fmt, int, pct } from '@/lib/format';

const HEADLINE: Record<Readiness['verdict'], (r: Readiness) => string> = {
  SUPPORTED: (r) => `This target is supported — with ${r.ambiguity} structural ambiguity.`,
  CAUTION: (r) => `This target is partly supported — ${r.reasons[0] ?? 'see the indicators'}.`,
  NOT_RECOMMENDED: (r) => `This target is not supported by the learned representation — ${r.reasons[0] ?? 'see the indicators'}.`,
};
const VERDICT_WORD: Record<Readiness['verdict'], string> = { SUPPORTED: 'Supported', CAUTION: 'Caution', NOT_RECOMMENDED: 'Not recommended' };
const MEANING: Record<string, string> = {
  fidelity: 'How closely the model\'s predictions of the targeted properties match the evaluation split. For a published checkpoint that saw that split in training this is a diagnostic, not held-out performance; the card says which.',
  alignment: 'Whether a structure and its properties map to the same place in the shared space, in both directions.',
  recoverability: 'Whether the decoder recovers the evaluation split\'s structures from their latent codes.',
  target_support: 'Where the target sits in the training distribution and how much training data lies around it.',
  ambiguity: 'How many different structures satisfy the same property target.',
  family_support: 'Whether the chosen family and its elements occur in the training data.',
};

function statusKind(s: string): 'ok' | 'warn' | 'bad' | 'info' { return s === 'ok' ? 'ok' : s === 'caution' ? 'warn' : s === 'not_ok' ? 'bad' : 'info'; }

function headline(ind: Indicator, r: Readiness): string {
  const n = ind.numbers as Record<string, number>;
  switch (ind.id) {
    case 'fidelity': {
      const per = ind.per_property ?? {};
      return Object.values(per).map((p) => `${p.label as string}: MAE ${fmt(p.mae as number, p.unit as string)} · ${p.word as string}`).join(' / ');
    }
    case 'alignment': return `top-1 retrieval ${pct(n.retrieval_top1)} · reverse ${pct(n.reverse_top1)}`;
    case 'recoverability': { const j = (ind.numbers as { from_joint?: Record<string, number> }).from_joint; return j ? `composition ${j.composition_exact_pct.toFixed(0)} % · structure match ${j.structure_match_pct.toFixed(0)} %` : 'not computed'; }
    case 'target_support': return `${int(n.n_box)} training materials in the window (${pct(n.fraction, 1)})`;
    case 'ambiguity': return `${int(n.n_formulas)} distinct compositions share the window · ${r.ambiguity}`;
    case 'family_support': { const sp = ind.space; return sp ? `${int(sp.rule_passing)} of ${int(sp.total)} compositions pass the rules` : ''; }
    default: return '';
  }
}

function meterValue(ind: Indicator): number {
  const n = ind.numbers as Record<string, number>;
  switch (ind.id) {
    case 'fidelity': { const ratios = Object.values(ind.per_property ?? {}).map((p) => (p.ratio as number) ?? 1); return ratios.length ? Math.max(0, 1 - Math.min(1, Math.max(...ratios))) : 0; }
    case 'alignment': return Math.min(1, n.retrieval_top1 ?? 0);
    case 'recoverability': { const j = (ind.numbers as { from_joint?: Record<string, number> }).from_joint; return j ? j.composition_exact_pct / 100 : 0; }
    case 'target_support': return Math.min(1, (n.fraction ?? 0) / 0.05);
    case 'ambiguity': return Math.min(1, (n.n_formulas ?? 0) / 20);
    case 'family_support': return ind.space ? ind.space.rule_passing_fraction : 0;
    default: return 0;
  }
}

export function Verdict({ report, onSearch, onAdjust, starting }: { report: Readiness; onSearch: () => void; onAdjust: () => void; starting: boolean }) {
  const v = report.verdict;
  return (
    <section className={`verdict v-${v}`} data-testid="verdict" data-verdict={v}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className={`badge ${v === 'SUPPORTED' ? 'badge-ok' : v === 'CAUTION' ? 'badge-warn' : 'badge-bad'}`}>{VERDICT_WORD[v]}</span>
        <span className="small faint">computed in {report.computed_in_ms} ms · model {report.model_id}</span>
      </div>
      <h1 style={{ marginTop: 10 }}>{HEADLINE[v](report)}</h1>
      <div className="stack" style={{ gap: 6 }}>{report.summary.map((s, i) => <p key={i} className="muted" style={{ margin: 0 }}>{s}</p>)}</div>
      {report.reasons.length > 1 && <ul className="small muted" style={{ margin: '10px 0 0 18px' }}>{report.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      {report.caveats.map((c) => <div key={c} className="banner banner-warn small" style={{ marginTop: 10 }}>{c[0].toUpperCase() + c.slice(1)}.</div>)}
      {v === 'NOT_RECOMMENDED' && report.limited_by_model && report.limited_by_model_note && <p className="small muted" style={{ margin: '10px 0 0' }} data-testid="model-limited">{report.limited_by_model_note}</p>}
      <div className="row" style={{ marginTop: 16 }}>
        {v === 'NOT_RECOMMENDED' && report.limited_by_model ? (
          <>
            <button type="button" className="btn btn-primary" data-testid="run-search" disabled={starting} onClick={onSearch}>{starting ? 'Starting…' : 'Run exploratory search'}</button>
            <button type="button" className="btn" onClick={onAdjust}>Adjust target</button>
          </>
        ) : v === 'NOT_RECOMMENDED' ? (
          <>
            <button type="button" className="btn btn-primary" onClick={onAdjust}>Adjust target</button>
            <button type="button" className="btn" data-testid="run-search" disabled={starting} onClick={onSearch}>{starting ? 'Starting…' : 'Proceed anyway — exploratory'}</button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-primary" data-testid="run-search" disabled={starting} onClick={onSearch}>{starting ? 'Starting…' : 'Search for candidates'}</button>
            <button type="button" className="btn" onClick={onAdjust}>Adjust target</button>
          </>
        )}
        <span className="small muted">about {Math.round(report.estimated_seconds)} s on this server{report.search_advice ? ' · a diverse set of candidates will be searched' : ''}</span>
      </div>
    </section>
  );
}

export function IndicatorCard({ ind, report }: { ind: Indicator; report: Readiness }) {
  return (
    <div className="card card-tight ind" data-testid={`indicator-${ind.id}`}>
      <div className="row" style={{ justifyContent: 'space-between' }}><h3 style={{ margin: 0 }}>{ind.title}</h3><StatusBadge status={ind.status} /></div>
      <div className="value">{headline(ind, report)}</div>
      <Meter value={meterValue(ind)} kind={statusKind(ind.status)} />
      <div className="meaning">{MEANING[ind.id]}</div>
      <details>
        <summary className="small" style={{ cursor: 'pointer' }}>What was measured</summary>
        <div className="stack small" style={{ marginTop: 6 }}>
          {ind.sentences.map((s, i) => <p key={i} style={{ margin: 0 }}>{s}</p>)}
          {ind.measured && <p className="measured" style={{ margin: 0 }}>{ind.measured}</p>}
        </div>
      </details>
    </div>
  );
}

export function TargetPosition({ report, project }: { report: Readiness; project: Project }) {
  const per = report.indicators.target_support.per_property ?? {};
  return (
    <section className="card">
      <h2>Where the target sits</h2>
      <div className="cards-2">
        {Object.entries(per).map(([pid, e]) => {
          const p = project.dataset.properties[pid];
          const values = (e.values as number[]) ?? [];
          const zero = p.zero_share > 0.5 ? Math.round(p.zero_share * p.n) : null;
          const hist = zero && p.nonzero ? p.nonzero.histogram : p.histogram;
          return (
            <div key={pid}>
              <div className="row" style={{ justifyContent: 'space-between' }}><b>{p.label}</b><span className={`badge ${e.status === 'in_distribution' ? 'badge-ok' : e.status === 'near_boundary' ? 'badge-warn' : 'badge-bad'}`}>{e.word as string}</span></div>
              <Histogram edges={hist.edges} counts={hist.counts} unit={p.unit} label={p.label} target={values[0]} window={report.windows[pid]} zeroCount={zero} zeroShare={zero ? p.zero_share : null} />
              <p className="small muted">{e.reason as string}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function AmbiguityPanel({ report }: { report: Readiness }) {
  const a = report.indicators.ambiguity;
  const n = a.numbers as Record<string, number>;
  return (
    <section className={`card ${a.one_to_many ? '' : ''}`} data-testid="ambiguity">
      <div className="row" style={{ justifyContent: 'space-between' }}><h2 style={{ margin: 0 }}>One property target, many possible structures</h2><span className="badge badge-info">ambiguity {report.ambiguity}</span></div>
      <p className="muted" style={{ marginTop: 10 }}>{a.sentences.join(' ')}</p>
      {a.one_to_many && <p>Candidates in this run are alternatives, not a ranking of one answer — compare them by composition and by their evidence.</p>}
      {a.examples && a.examples.length > 0 && (
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>Training materials nearest the target ({a.examples.length} of {int(n.n_box)})</summary>
          <table className="table small" style={{ marginTop: 8 }}>
            <thead><tr><th>Material</th><th>Site key</th>{Object.keys(a.examples[0].properties).map((k) => <th key={k} className="num">{k}</th>)}<th>Split</th></tr></thead>
            <tbody>{a.examples.map((m) => <tr key={m.material_id}><td>{m.formula}</td><td className="mono">{m.site_key ?? '—'}</td>{Object.values(m.properties).map((v, i) => <td key={i} className="num">{fmt(v)}</td>)}<td>{m.split}</td></tr>)}</tbody>
          </table>
        </details>
      )}
    </section>
  );
}
