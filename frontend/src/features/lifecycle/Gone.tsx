import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router';
import type { ApiError } from '@/api/client';
import { invalidate } from '@/api/hooks';
import { goalOfRun, saveGoal } from '@/lib/goalStore';

const KEPT = 'On the shared site a finished search is kept for one hour after it was last opened, and a restart of the server clears every search.';

/** A search the server no longer has: why, and the way back to its goal (kept in this browser when the search ran or was opened here). */
export function RunGone({ projectId, runId, error }: { projectId: string; runId: string; error: ApiError }) {
  const navigate = useNavigate();
  const goal = goalOfRun(runId);
  useEffect(() => { invalidate('runs'); }, []);                       // the list of this tab's searches is stale too
  const again = () => { if (goal) saveGoal(projectId, goal); navigate(`/p/${projectId}/goal`); };
  return (
    <section className="card" role="alert" data-testid="run-gone" style={{ maxWidth: 760 }}>
      <h2 style={{ marginTop: 0 }}>{error.code === 'gone' ? 'This search has expired' : 'This search is not on the server'}</h2>
      <p className="muted">{KEPT} {goal ? 'Its goal is kept in this browser: run it again to get candidates for it.'
        : 'Its goal was not kept in this browser: the goal page opens with the goal last edited in this tab, or with the demo’s default.'}</p>
      <p className="small faint">{error.message}</p>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-primary" onClick={again}>{goal ? 'Re-run this goal' : 'Set a goal'}</button>
        <Link to={`/p/${projectId}/runs`} className="btn">Searches of this tab</Link>
      </div>
    </section>
  );
}

/** A generation job the server no longer has. */
export function JobGone({ error }: { error: ApiError }) {
  return (
    <section className="card" role="alert" data-testid="job-gone" style={{ maxWidth: 760 }}>
      <h2 style={{ marginTop: 0 }}>{error.code === 'gone' ? 'This generation job has expired' : 'This generation job is not on the server'}</h2>
      <p className="muted">On the shared site a finished job is kept for one hour after it was last opened, and a restart of the server clears every job. Generating again takes seconds to a few minutes.</p>
      <p className="small faint">{error.message}</p>
      <Link to="/play" className="btn btn-primary">Generate again</Link>
    </section>
  );
}
