import { Link, useParams } from 'react-router';
import { api } from '@/api/endpoints';
import { useResource } from '@/api/hooks';
import { ErrorNote, Spinner } from '@/components/ui';

export default function Runs() {
  const { projectId = 'perov5-demo' } = useParams();
  const { data, error, loading, reload } = useResource('runs', () => api.runs());
  if (loading) return <Spinner label="Loading runs" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  return (
    <>
      <div className="page-head"><h1>Runs</h1><p>The searches of this tab. A run keeps its candidates, funnel, manifest and exports.</p></div>
      {!data?.length ? <div className="card"><p>No search of this tab is on the server. On the shared site a finished search is kept for one hour after it was last opened, and a restart of the server clears every search.</p><Link to={`/p/${projectId}/goal`} className="btn btn-primary">Define a goal</Link></div> : (
        <table className="table card" style={{ padding: 0 }}>
          <thead><tr><th>Run</th><th>Request</th><th>Status</th><th className="num">Candidates</th><th>Readiness</th><th>Started</th></tr></thead>
          <tbody>{data.map((r) => (
            <tr key={r.run_id}><td><Link to={`/p/${projectId}/runs/${r.run_id}`} className="mono">{r.run_id}</Link></td><td className="mono small">{r.summary}</td><td>{r.status}{r.mode === 'exploratory' ? ' · exploratory' : ''}</td><td className="num">{r.n_candidates}</td><td>{r.verdict}</td><td className="small">{r.started ? new Date(r.started).toLocaleString() : '—'}</td></tr>
          ))}</tbody>
        </table>
      )}
    </>
  );
}
