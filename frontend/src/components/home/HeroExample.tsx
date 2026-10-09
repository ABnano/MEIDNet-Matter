import { useMemo } from 'react';
import { Link } from 'react-router';
import { research, type Accepted, type Study } from '@/api/research';
import { CellViewer } from '@/components/structure/CellViewer';
import { ResponseCurve } from '@/components/research';
import { cellOfAccepted, shortClass } from './DiscoveryStrip';

/** A real, clickable result beside the words: one accepted structure with its two readings, and the response of the
 *  generator in one small plot (requested gap in, delivered gap out, on relaxed cells). */
export function HeroExample({ study, example }: { study: Study; example?: Accepted | null }) {
  const accepted = study.accepted ?? [];
  const cal = study.calibration;
  const pick = example ?? accepted.find((a) => a.structure) ?? null;
  const cell = useMemo(() => (pick ? cellOfAccepted(pick) : null), [pick]);
  const points = accepted.map((a) => ({ requested: a.requested, delivered: a.judge_gap, accepted: true, label: a.formula }));
  const bands = (cal?.per_target ?? []).map((p) => ({ requested: p.requested, mean: p.delivered_mean ?? p.generated_judge_mean, sd: p.delivered_sd }));
  return (
    <div className="hero-example">
      {pick && (
        <div className="card card-tight" style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 12, alignItems: 'center' }}>
          <div>{cell && <CellViewer structure={cell} size={150} title={pick.formula} />}</div>
          <div>
            <div className="micro">a result you can open</div>
            <h3 style={{ margin: '2px 0 4px' }}>{pick.formula}</h3>
            <div className="small">asked <b>{pick.requested.toFixed(1)} eV</b> · second model <b className="num">{pick.judge_gap.toFixed(2)}</b> eV · label from the structure <span className="num">{pick.label_structure_gap.toFixed(2)}</span> eV</div>
            <div className="small muted" style={{ marginTop: 4 }}>{shortClass(pick.class)} · charge balanced · space group {pick.spacegroup_relaxed ?? pick.spacegroup_designed} · both readings on the relaxed cell</div>
            <div className="row" style={{ gap: 8, marginTop: 8 }}>
              <Link to="/studies/mp20#accepted" className="btn btn-sm">All {accepted.length} accepted</Link>
              <a className="btn btn-sm btn-ghost" href={research.studyFileUrl('mp20', pick.file)} download>CIF ↓</a>
            </div>
          </div>
        </div>
      )}
      {cal && points.length > 0 && (
        <div className="card card-tight">
          <div className="micro" style={{ marginBottom: 4 }}>requested gap in, delivered gap out · {points.length} accepted relaxed cells, {bands.length} requests</div>
          <ResponseCurve points={points} bands={bands} fit={cal.linearity} width={420} height={230} compact />
          <div className="small muted">Fitted response {cal.linearity.intercept.toFixed(2)} + {cal.linearity.slope.toFixed(2)}·x · MAE {cal.accuracy.mae_relaxed_cells.toFixed(2)} eV · stability not assessed.</div>
        </div>
      )}
    </div>
  );
}
