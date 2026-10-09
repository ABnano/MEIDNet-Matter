import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ApiError } from '@/api/client';
import { api } from '@/api/endpoints';
import type { Goal, Readiness as ReadinessT } from '@/api/types';
import { ErrorNote, Spinner } from '@/components/ui';
import { useProject } from '@/features/project/useProject';
import { AmbiguityPanel, IndicatorCard, TargetPosition, Verdict } from '@/features/readiness/ReadinessReport';
import { invalidate } from '@/api/hooks';
import { loadGoal, rememberRunGoal } from '@/lib/goalStore';

export default function Readiness() {
  const { projectId = 'perov5-demo' } = useParams();
  const navigate = useNavigate();
  const { data: project, error: perr, loading } = useProject(projectId);
  const [goal, setGoal] = useState<Goal | null>(null);
  const [report, setReport] = useState<ReadinessT | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => { if (project) setGoal(loadGoal(project.project_id, project.default_goal, project.models.map((m) => m.model_id))); }, [project]);
  useEffect(() => {
    if (!goal) return;
    const ctrl = new AbortController();
    setReport(null); setError(null);
    api.readiness(goal, ctrl.signal).then(setReport).catch((e: Error) => { if (e.name !== 'AbortError') setError(e); });
    return () => ctrl.abort();
  }, [goal]);

  if (loading || !project) return perr ? <ErrorNote error={perr} /> : <Spinner label="Loading the project" />;
  if (error) {
    const e = error as ApiError;
    return <><div className="page-head"><h1>Design readiness</h1></div><ErrorNote error={error} />{e.status === 422 && <button type="button" className="btn" onClick={() => navigate(`/p/${projectId}/goal`)}>Adjust the goal</button>}</>;
  }
  if (!report || !goal) return <><div className="page-head"><h1>Design readiness</h1><p>Measuring whether the data and the model support this target…</p></div><Spinner label="Computing" /></>;

  const start = async () => {
    setStarting(true);
    try {
      const run = await api.startRun(goal, report.exploratory_required);
      rememberRunGoal(run.run_id, goal);
      invalidate('runs');
      navigate(`/p/${projectId}/runs/${run.run_id}`);
    } catch (e) { setError(e as Error); setStarting(false); }
  };
  const order = ['fidelity', 'alignment', 'recoverability', 'target_support', 'ambiguity', 'family_support'] as const;
  return (
    <>
      <div className="page-head"><h1>Design readiness</h1><p>Can this dataset and model support this target? Six indicators, measured before any search runs.</p></div>
      <Verdict report={report} onSearch={start} onAdjust={() => navigate(`/p/${projectId}/goal`)} starting={starting} />
      <div className="ind-grid" style={{ marginBottom: 24 }}>{order.map((k) => <IndicatorCard key={k} ind={report.indicators[k]} report={report} />)}</div>
      <div className="stack" style={{ gap: 24 }}>
        <TargetPosition report={report} project={project} />
        <AmbiguityPanel report={report} />
        <FamilySupport report={report} />
      </div>
    </>
  );
}

function FamilySupport({ report }: { report: ReadinessT }) {
  const f = report.indicators.family_support;
  if (!f.groups) return null;
  return (
    <section className="card">
      <h2>Chemical-family support</h2>
      <div className="cards-3">
        {Object.entries(f.groups).map(([g, grp]) => (
          <div key={g}>
            <b>Site {g}</b> <span className="small muted">{grp.present.length} of {grp.allowed.length} allowed elements occur in the data</span>
            <div className="row" style={{ gap: 4, marginTop: 6 }}>
              {grp.allowed.map((el) => <span key={el} className="chip small" style={grp.present.includes(el) ? undefined : { borderStyle: 'dashed', color: 'var(--faint)' }} title={grp.present.includes(el) ? `${grp.n_materials[el]} materials` : 'not in the training data'}>{el}</span>)}
            </div>
            {grp.excluded_by_user.length > 0 && <div className="small muted" style={{ marginTop: 4 }}>excluded by you: {grp.excluded_by_user.join(', ')}</div>}
          </div>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 12 }}>{f.sentences.join(' ')}</p>
    </section>
  );
}
